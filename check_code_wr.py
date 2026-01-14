import json
import re
from datasets import load_dataset


def check_code_winrate():
    results_path = "tunix_vs_mm_01/results.json"

    print(f"Loading results from {results_path}...")
    try:
        with open(results_path, "r") as f:
            data = json.load(f)
            comparisons = data["comparisons"]
    except Exception as e:
        print(f"Error loading results: {e}")
        return

    # Regex to detect code-related prompts
    code_keywords = re.compile(
        r"(write a program|implement|def |class |```python|python code|function|algorithm|code that|program that)",
        re.IGNORECASE,
    )

    total_code = 0
    mm_wins = 0
    opp_wins = 0
    ties = 0

    code_examples = []

    for i, comp in enumerate(comparisons):
        prompt = comp["prompt"]

        if code_keywords.search(prompt):
            total_code += 1
            winner = comp["winner"]

            if winner == 0:
                mm_wins += 1
            elif winner == 1:
                opp_wins += 1
            else:
                ties += 1

            # Store for inspection
            code_examples.append(
                {
                    "row": i + 1,
                    "prompt": prompt[:80],
                    "winner": comp["winner_name"],
                    "explanation": comp["explanation"][:100],
                }
            )

    print(f"\n{'=' * 60}")
    print(f"CODE/PYTHON TASK WIN RATE: mm-01 vs 27b-test")
    print(f"{'=' * 60}")
    print(f"Total Code Tasks Detected: {total_code}")
    print(f"mm-01 Wins:     {mm_wins} ({mm_wins / total_code * 100:.1f}%)")
    print(f"27b-test Wins:  {opp_wins} ({opp_wins / total_code * 100:.1f}%)")
    print(f"Ties:           {ties} ({ties / total_code * 100:.1f}%)")

    if (mm_wins + opp_wins) > 0:
        wr_excl = mm_wins / (mm_wins + opp_wins) * 100
        print(f"\nWin Rate (Excl. Ties): mm-01 = {wr_excl:.1f}%")

    print(f"\n{'=' * 60}")
    print("SAMPLE CODE TASKS:")
    print(f"{'=' * 60}")
    for ex in code_examples[:5]:
        print(f"Row {ex['row']}: {ex['prompt']}...")
        print(f"  Winner: {ex['winner']}")
        print(f"  Reason: {ex['explanation']}...")
        print()


if __name__ == "__main__":
    check_code_winrate()
