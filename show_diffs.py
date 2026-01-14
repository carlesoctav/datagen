import json


def show_diffs():
    path = "comparison_notebook_vm/results.json"
    with open(path, "r") as f:
        data = json.load(f)
        comparisons = data["comparisons"]

    count = 0
    print("Showing 3 examples where mm-01 won but answers might look similar...\n")

    for i, comp in enumerate(comparisons):
        if comp["winner"] == 0:  # mm-01 won
            print(f"=== EXAMPLE {count + 1} (Row {i + 1}) ===")
            print(f"PROMPT: {comp['prompt'][:100]}...")
            print("-" * 40)
            print("MODEL 1 (mm-01) [WINNER]:")
            print(comp["response_1"][:300] + "...")
            print("-" * 40)
            print("MODEL 2 (random-test):")
            print(comp["response_2"][:300] + "...")
            print("-" * 40)
            print(f"JUDGE EXPLANATION:\n{comp['explanation']}")
            print("\n" + "=" * 80 + "\n")

            count += 1
            if count >= 3:
                break


if __name__ == "__main__":
    show_diffs()
