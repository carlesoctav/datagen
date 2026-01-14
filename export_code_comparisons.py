import json
import re
from datasets import load_dataset


def export_code_comparisons():
    results_path = "tunix_vs_mm_01/results.json"
    output_file = "code_comparisons_tunix.md"

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

    count = 0
    print(f"Writing code comparisons to {output_file}...")

    with open(output_file, "w") as f:
        f.write("# Code Task Comparisons: mm-01 (Model 1) vs 27b-test (Model 2)\n\n")

        for i, comp in enumerate(comparisons):
            prompt = comp["prompt"]

            if code_keywords.search(prompt):
                count += 1
                winner_idx = comp["winner"]
                winner_name = comp["winner_name"]

                f.write(f"#{count} [ID: {i}]\n")
                f.write(
                    "================================================================================\n"
                )
                f.write(f"PROMPT\n")
                f.write(
                    "================================================================================\n"
                )
                f.write(f"{prompt}\n\n")

                f.write(
                    "================================================================================\n"
                )
                f.write(f"MODEL 1 (mm-01) {'[WINNER]' if winner_idx == 0 else ''}\n")
                f.write(
                    "================================================================================\n"
                )
                f.write(f"{comp['response_1']}\n\n")

                f.write(
                    "================================================================================\n"
                )
                f.write(f"MODEL 2 (27b-test) {'[WINNER]' if winner_idx == 1 else ''}\n")
                f.write(
                    "================================================================================\n"
                )
                f.write(f"{comp['response_2']}\n\n")

                f.write(
                    "================================================================================\n"
                )
                f.write(f"JUDGE EXPLANATION (Winner: {winner_name})\n")
                f.write(
                    "================================================================================\n"
                )
                f.write(f"{comp['explanation']}\n\n")
                f.write("\n\n")

    print(f"Done! Wrote {count} examples to {output_file}")


if __name__ == "__main__":
    export_code_comparisons()
