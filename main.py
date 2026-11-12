#!/usr/bin/env python3
"""
pumpfun-top5-forecast-01 entry: predicts top 5 new Solana coins by market cap 24h out.

Reads /input/task.json and /input/history.ndjson, writes /output/forecast.json.
"""

import json
import math
import os
from pathlib import Path

INPUT_DIR = os.environ.get("MAKEFUN_INPUT_DIR", "/input")
OUTPUT_DIR = os.environ.get("MAKEFUN_OUTPUT_DIR", "/output")


def log10_cap(lamports):
    """log10 of cap in SOL: log10(lamports) - 9."""
    return math.log10(int(lamports)) - 9


def erfc(x):
    """erfc approximation."""
    z = abs(x)
    t = 1.0 / (1.0 + 0.5 * z)
    r = t * math.exp(-z * z - 1.26551223 + t * (1.00002368 + t * (
        0.37409196 + t * (0.09678418 + t * (-0.18628806 + t * (
            0.27886807 + t * (-1.13520398 + t * (
                1.48851587 + t * (-0.82215223 + t * 0.17087277
            ))
        ))
    )))))
    return r if x >= 0 else 2 - r


def above(x, mean, sd):
    """P(X >= x) for X ~ N(mean, sd)."""
    if x == -float('inf'):
        return 1.0
    if x == float('inf'):
        return 0.0
    return 0.5 * erfc((x - mean) / (sd * math.sqrt(2)))


def main():
    # Load task
    with open(os.path.join(INPUT_DIR, "task.json")) as f:
        task = json.load(f)
    
    places = task["places"]
    output_file = task["output"]
    edges = task["size"]["edges"]
    
    # Load history
    with open(os.path.join(INPUT_DIR, "history.ndjson")) as f:
        lines = [line.strip() for line in f if line.strip()]
    
    marks = []
    for line in lines:
        mark = json.loads(line)
        if mark.get("ok") and isinstance(mark.get("rows"), list):
            marks.append(mark)
    
    if not marks:
        raise ValueError("No valid marks in history")
    
    # Get last mark's chart (sorted by rank)
    chart = sorted(marks[-1]["rows"], key=lambda r: r["rank"])
    
    if len(chart) < places:
        raise ValueError(f"Last mark has {len(chart)} coins, fewer than {places} places")
    
    # Forecasting strategy: persistence + momentum
    # Place k: 35% on coin at #k (stay), 10% on #k-1 and #k+1 (neighbours)
    # For size: normal distribution around log10(cap) of coin at #k, sd 0.35
    
    P_STAY = 0.30
    P_NEIGHBOUR = 0.10
    SIZE_SD = 0.35
    MICRO = 1_000_000
    
    probabilities = []
    sizes = []
    
    for place in range(1, places + 1):
        idx = place - 1  # 0-indexed
        
        # Stay probability
        probabilities.append({
            "mint": chart[idx]["mint"],
            "place": place,
            "p": P_STAY
        })
        
        # Neighbour probabilities
        if place > 1:
            probabilities.append({
                "mint": chart[idx - 1]["mint"],
                "place": place,
                "p": P_NEIGHBOUR
            })
        if place < places:
            probabilities.append({
                "mint": chart[idx + 1]["mint"],
                "place": place,
                "p": P_NEIGHBOUR
            })
        
        # Size distribution
        mean = log10_cap(chart[idx]["market_cap_lamports"])
        for bin_idx in range(len(edges) + 1):
            lo = -float('inf') if bin_idx == 0 else edges[bin_idx - 1]
            hi = float('inf') if bin_idx == len(edges) else edges[bin_idx]
            
            p = above(lo, mean, SIZE_SD) - above(hi, mean, SIZE_SD)
            u = int(p * MICRO)
            
            if u > 0:
                sizes.append({
                    "place": place,
                    "bin": bin_idx,
                    "p": u / MICRO
                })
    
    # Top 5 in order
    top5 = [chart[i]["mint"] for i in range(places)]
    
    forecast = {
        "probabilities": probabilities,
        "top5": top5,
        "sizes": sizes
    }
    
    # Write output
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(os.path.join(OUTPUT_DIR, output_file), "w") as f:
        json.dump(forecast, f)
        f.write("\n")


if __name__ == "__main__":
    main()
