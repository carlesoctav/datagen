import json


def check_identical_failures():
    path = "comparison_notebook_vm/results.json"
    with open(path, "r") as f:
        data = json.load(f)

    count = 0
    print("Finding 'Bad Ties' (Both wrong in the same way)...\n")

    for i, comp in enumerate(data["comparisons"]):
        if comp["winner"] == -1:  # Tie
            # Look for cases where the explanation implies both are bad
            if (
                "incorrect" in comp["explanation"].lower()
                or "error" in comp["explanation"].lower()
            ):
                print(f"=== TIE EXAMPLE {count + 1} (Row {i + 1}) ===")
                print(f"PROMPT: {comp['prompt'][:100]}...")
                print("-" * 40)
                print("MODEL 1 (mm-01):")
                # print snippet of reasoning
                print(
                    comp["response_1"].split("</reasoning>")[0][-300:]
                    + "</reasoning>..."
                )
                print("-" * 40)
                print("MODEL 2 (random-test):")
                print(
                    comp["response_2"].split("</reasoning>")[0][-300:]
                    + "</reasoning>..."
                )
                print("-" * 40)
                print(f"JUDGE EXPLANATION:\n{comp['explanation']}")
                print("\n" + "=" * 80 + "\n")

                count += 1
                if count >= 3:
                    break


if __name__ == "__main__":
    check_identical_failures()
