import json
import difflib


def check_similarity():
    path = "comparison_notebook_vm/results.json"
    print(f"Loading {path}...")

    with open(path, "r") as f:
        data = json.load(f)
        comparisons = data["comparisons"]

    exact_matches = 0
    total = len(comparisons)

    # Track "Judge Hallucinations" (Picking a winner when text is identical)
    judge_fail_wins_1 = 0
    judge_fail_wins_2 = 0

    print("\nChecking for identical responses...")

    for i, comp in enumerate(comparisons):
        r1 = comp["response_1"].strip()
        r2 = comp["response_2"].strip()

        if r1 == r2:
            exact_matches += 1
            winner = comp["winner"]

            if winner != -1:  # If not a tie
                if winner == 0:
                    judge_fail_wins_1 += 1
                else:
                    judge_fail_wins_2 += 1

                if exact_matches <= 3:  # Print first few failures
                    print(f"\n[CRITICAL JUDGE FAIL] Row {i + 1}")
                    print(
                        f"Both models produced IDENTICAL output, but Judge picked Model {winner + 1}!"
                    )
                    print(f"Winner Name: {comp['winner_name']}")
                    print(f"Explanation: {comp['explanation']}")

    print("\n" + "=" * 60)
    print("SIMILARITY STATS")
    print("=" * 60)
    print(f"Total Comparisons: {total}")
    print(f"Exact Text Matches: {exact_matches} ({exact_matches / total * 100:.1f}%)")

    if exact_matches > 0:
        print(f"\nOf the {exact_matches} identical responses:")
        print(
            f"- Correctly labeled as Tie: {exact_matches - judge_fail_wins_1 - judge_fail_wins_2}"
        )
        print(f"- Judge arbitrarily picked Model 1: {judge_fail_wins_1}")
        print(f"- Judge arbitrarily picked Model 2: {judge_fail_wins_2}")

    # Check for near-duplicates (high similarity but not exact)
    print("\nChecking for near-duplicates (diff < 5 chars)...")
    near_matches = 0
    for comp in comparisons:
        r1 = comp["response_1"].strip()
        r2 = comp["response_2"].strip()
        if r1 != r2 and abs(len(r1) - len(r2)) < 5:
            # Simple length heuristic first for speed
            if r1 == r2:
                continue  # already counted
            near_matches += 1

    print(
        f"Responses with length diff < 5 chars (potential near-dupes): {near_matches}"
    )


if __name__ == "__main__":
    check_similarity()
