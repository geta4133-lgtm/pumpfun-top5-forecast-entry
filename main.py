import json
import math
import os


MICRO = 1_000_000
P_STAY = 0.30
P_NEIGHBOUR = 0.10
SIZE_SD = 0.35


def size_of(lamports) -> float:
    return math.log10(float(int(lamports))) - 9.0


def above(x: float, mean: float, sd: float) -> float:
    if x == float("-inf"):
        return 1.0
    if x == float("inf"):
        return 0.0
    return 0.5 * math.erfc((x - mean) / (sd * math.sqrt(2.0)))


def main() -> None:
    input_dir = os.environ.get("MAKEFUN_INPUT_DIR", "/input")
    output_dir = os.environ.get("MAKEFUN_OUTPUT_DIR", "/output")
    os.makedirs(output_dir, exist_ok=True)

    task_path = os.path.join(input_dir, "task.json")
    with open(task_path, "r", encoding="utf-8") as f:
        task = json.load(f)

    places = int(task["places"])
    output_name = task.get("output", "forecast.json")
    edges = [float(e) for e in task["size"]["edges"]]

    history_path = os.path.join(input_dir, "history.ndjson")
    marks = []
    with open(history_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            m = json.loads(line)
            if m.get("ok") is True and isinstance(m.get("rows"), list):
                marks.append(m)

    if not marks:
        raise ValueError("the history holds no ok mark")

    chart = sorted(marks[-1]["rows"], key=lambda r: (int(r["rank"]), str(r["mint"])))
    if len(chart) < places:
        raise ValueError(
            f"the last mark ranks {len(chart)} coins, fewer than the {places} places"
        )

    # Track recent log10(cap) across last up to 3 marks for bounded drift estimation
    prev_sizes = {}
    if len(marks) >= 2:
        prev_chart = marks[-2]["rows"]
        for row in prev_chart:
            try:
                prev_sizes[str(row["mint"])] = size_of(row["market_cap_lamports"])
            except (ValueError, KeyError):
                pass

    probabilities = []
    sizes = []

    for place in range(1, places + 1):
        curr_row = chart[place - 1]
        curr_mint = str(curr_row["mint"])
        probabilities.append({"mint": curr_mint, "place": place, "p": P_STAY})
        if place > 1:
            probabilities.append(
                {"mint": str(chart[place - 2]["mint"]), "place": place, "p": P_NEIGHBOUR}
            )
        if place < len(chart):
            probabilities.append(
                {"mint": str(chart[place]["mint"]), "place": place, "p": P_NEIGHBOUR}
            )

        curr_size = size_of(curr_row["market_cap_lamports"])
        drift = 0.0
        if curr_mint in prev_sizes:
            raw_drift = curr_size - prev_sizes[curr_mint]
            drift = max(-0.08, min(0.08, 0.25 * raw_drift))
        mean = curr_size + drift

        for bin_idx in range(len(edges) + 1):
            lo = float("-inf") if bin_idx == 0 else edges[bin_idx - 1]
            hi = float("inf") if bin_idx == len(edges) else edges[bin_idx]
            u = math.floor((above(lo, mean, SIZE_SD) - above(hi, mean, SIZE_SD)) * MICRO)
            if u > 0:
                sizes.append({"place": place, "bin": bin_idx, "p": u / MICRO})

    top5 = [str(r["mint"]) for r in chart[:places]]
    forecast = {
        "probabilities": probabilities,
        "top5": top5,
        "sizes": sizes,
    }

    out_path = os.path.join(output_dir, output_name)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(json.dumps(forecast) + "\n")


if __name__ == "__main__":
    main()
