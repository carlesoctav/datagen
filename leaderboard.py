import json
import os
import glob


def generate_leaderboard():
    print("Generating Global Win Rate Leaderboard for 'mm-01'...\n")

    results = []

    # Find all results.json files
    files = glob.glob("comparison_*/results.json")

    for filepath in files:
        try:
            with open(filepath, "r") as f:
                data = json.load(f)
                comparisons = data.get("comparisons", [])

            if not comparisons:
                continue

            # Determine which model is mm-01
            # We look at the first comparison to identify names
            first = comparisons[0]
            # Check keys usually present in my scripts, or infer from directory name if needed
            # But strict parsing from stats.json is safer if available
            stats_path = filepath.replace("results.json", "stats.json")

            if os.path.exists(stats_path):
                with open(stats_path, "r") as f:
                    stats = json.load(f)
                    model_1 = stats.get("model_1", "Model 1")
                    model_2 = stats.get("model_2", "Model 2")
                    w1 = stats.get("wins_1", 0)
                    w2 = stats.get("wins_2", 0)
                    ties = stats.get("ties", 0)
                    total = stats.get("total", 0)
            else:
                # Fallback manual count if stats.json missing
                # Try to guess mm-01 index
                # This is tricky without metadata, but let's try to detect "mm-01" in the folder name or assume standard
                continue

            # Identify Opponent and mm-01's score
            if "mm-01" in model_1 or "mm-01" in model_2:
                if "mm-01" in model_1:
                    mm_wins = w1
                    opp_wins = w2
                    opponent = model_2
                else:
                    mm_wins = w2
                    opp_wins = w1
                    opponent = model_1

                # Normalize Opponent Name
                if "/" in opponent:
                    opponent = opponent.split("/")[-1]
                if "gemma-3-1b-it" in opponent:
                    opponent = "Gemma-3-1b-it"

                wr_raw = (mm_wins / total) * 100
                wr_excl_ties = (
                    (mm_wins / (mm_wins + opp_wins)) * 100
                    if (mm_wins + opp_wins) > 0
                    else 0
                )

                results.append(
                    {
                        "run": filepath.split("/")[0],
                        "opponent": opponent,
                        "mm_wins": mm_wins,
                        "opp_wins": opp_wins,
                        "ties": ties,
                        "wr_raw": wr_raw,
                        "wr_excl": wr_excl_ties,
                    }
                )

        except Exception as e:
            # print(f"Skipping {filepath}: {e}")
            pass

    # Sort by mm-01 Win Rate (Descending)
    results.sort(key=lambda x: x["wr_excl"], reverse=True)

    # Print Table
    print(
        f"{'Opponent':<25} | {'Run Directory':<30} | {'WR (Excl Ties)':<15} | {'Win-Loss-Tie':<15}"
    )
    print("-" * 90)

    for r in results:
        record = f"{r['mm_wins']}-{r['opp_wins']}-{r['ties']}"
        print(
            f"{r['opponent']:<25} | {r['run']:<30} | {r['wr_excl']:>5.1f}%          | {record:<15}"
        )


if __name__ == "__main__":
    generate_leaderboard()
