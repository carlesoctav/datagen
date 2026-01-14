import json
from datasets import load_dataset
from collections import defaultdict
import re


def filter_and_analyze():
    results_path = "comparison_temp0_full/results.json"

    print(f"Loading results from {results_path}...")
    try:
        with open(results_path, "r") as f:
            data = json.load(f)
            comparisons = data["comparisons"]
    except FileNotFoundError:
        print(f"Error: File {results_path} not found.")
        return

    # Load dataset for source mapping
    print("Loading dataset carlesoctav/gpt-eval...")
    ds = load_dataset("carlesoctav/gpt-eval", split="train")
    prompt_to_source = {item["prompt"]: item["source"] for item in ds}

    # Regex to check for basic tag presence
    # We define a "loop/failure" as missing the closing reasoning or answer tags
    def is_valid_format(text):
        if not text:
            return False
        return "</reasoning>" in text and "</answer>" in text

    # Filter comparisons
    valid_comparisons = []
    excluded_count = 0

    print("\nFiltering out rows where Model 2 (mm-01) failed formatting/looped...")

    for comp in comparisons:
        # Check Model 2 (mm-01) for loops/format errors
        if is_valid_format(comp["response_2"]):
            valid_comparisons.append(comp)
        else:
            excluded_count += 1

    print(f"Excluded {excluded_count} rows due to loops/formatting errors.")
    print(f"Remaining valid comparisons: {len(valid_comparisons)}")

    # Calculate Stats
    stats = defaultdict(lambda: {"wins_1": 0, "wins_2": 0, "ties": 0, "total": 0})

    for comp in valid_comparisons:
        prompt = comp["prompt"]
        winner = comp["winner"]  # 0 for model 1, 1 for model 2, -1 for tie
        source = prompt_to_source.get(prompt, "unknown")

        stats[source]["total"] += 1
        if winner == 0:
            stats[source]["wins_1"] += 1
        elif winner == 1:
            stats[source]["wins_2"] += 1
        else:
            stats[source]["ties"] += 1

    # Print Results
    print("\n" + "=" * 80)
    print(f"RESULTS (Excluding {excluded_count} Looped/Failed Responses)")
    print("=" * 80)
    print(
        f"{'Source':<15} | {'Total':<6} | {'Model 1 (100)':<15} | {'Model 2 (mm-01)':<15} | {'Ties':<10}"
    )
    print("-" * 80)

    sources = sorted(stats.keys())
    total_stats = {"wins_1": 0, "wins_2": 0, "ties": 0, "total": 0}

    for source in sources:
        s = stats[source]
        total = s["total"]
        w1 = s["wins_1"]
        w2 = s["wins_2"]
        t = s["ties"]

        total_stats["wins_1"] += w1
        total_stats["wins_2"] += w2
        total_stats["ties"] += t
        total_stats["total"] += total

        w1_pct = (w1 / total * 100) if total > 0 else 0
        w2_pct = (w2 / total * 100) if total > 0 else 0
        t_pct = (t / total * 100) if total > 0 else 0

        print(
            f"{source:<15} | {total:<6} | {w1:<3} ({w1_pct:>5.1f}%)    | {w2:<3} ({w2_pct:>5.1f}%)    | {t:<3} ({t_pct:>5.1f}%)"
        )

    print("-" * 80)

    # Grand Total
    ts = total_stats
    tt = ts["total"]
    tw1 = ts["wins_1"]
    tw2 = ts["wins_2"]
    tties = ts["ties"]

    tw1_pct = (tw1 / tt * 100) if tt > 0 else 0
    tw2_pct = (tw2 / tt * 100) if tt > 0 else 0
    tt_pct = (tties / tt * 100) if tt > 0 else 0

    print(
        f"{'TOTAL':<15} | {tt:<6} | {tw1:<3} ({tw1_pct:>5.1f}%)    | {tw2:<3} ({tw2_pct:>5.1f}%)    | {tties:<3} ({tt_pct:>5.1f}%)"
    )
    print("=" * 80)


if __name__ == "__main__":
    filter_and_analyze()
