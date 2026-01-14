import json
from datasets import load_dataset
from collections import defaultdict
import warnings

# Suppress warnings
warnings.filterwarnings("ignore")


def calculate_stats_by_source():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--results-dir",
        type=str,
        default="comparison_temp0_full",
        help="Directory containing results.json",
    )
    args = parser.parse_args()

    # 1. Load the results
    results_path = f"{args.results_dir}/results.json"
    print(f"Loading results from {results_path}...")
    try:
        with open(results_path, "r") as f:
            data = json.load(f)
            comparisons = data["comparisons"]
    except FileNotFoundError:
        print(f"Error: File {results_path} not found.")
        return

    # 2. Load the dataset to get sources
    print("Loading dataset carlesoctav/gpt-eval...")
    ds = load_dataset("carlesoctav/gpt-eval", split="train")

    # Create a prompt -> source map
    # Using dictionary for O(1) lookup. Assuming prompts are unique enough or exact matches.
    prompt_to_source = {item["prompt"]: item["source"] for item in ds}

    # 3. Tally results
    stats = defaultdict(lambda: {"wins_1": 0, "wins_2": 0, "ties": 0, "total": 0})

    missing_source_count = 0

    for comp in comparisons:
        prompt = comp["prompt"]
        winner = comp["winner"]  # 0 for model 1, 1 for model 2, -1 for tie

        source = prompt_to_source.get(prompt, "unknown")
        if source == "unknown":
            missing_source_count += 1

        stats[source]["total"] += 1
        if winner == 0:
            stats[source]["wins_1"] += 1
        elif winner == 1:
            stats[source]["wins_2"] += 1
        else:
            stats[source]["ties"] += 1

    # 4. Print Results
    print("\n" + "=" * 80)
    print(
        f"{'Source':<15} | {'Total':<6} | {'Model 1 (100)':<15} | {'Model 2 (mm-01)':<15} | {'Ties':<10}"
    )
    print("-" * 80)

    sources = sorted(stats.keys())

    # Calculate aggregates
    total_stats = {"wins_1": 0, "wins_2": 0, "ties": 0, "total": 0}

    for source in sources:
        s = stats[source]
        total = s["total"]
        w1 = s["wins_1"]
        w2 = s["wins_2"]
        t = s["ties"]

        # Accumulate total
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
    # Print Grand Total
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

    if missing_source_count > 0:
        print(
            f"\nWarning: {missing_source_count} prompts could not be matched to a source in the dataset."
        )


if __name__ == "__main__":
    calculate_stats_by_source()
