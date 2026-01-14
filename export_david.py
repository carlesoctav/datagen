import json
from datasets import load_dataset
import warnings

# Suppress warnings
warnings.filterwarnings("ignore")


def write_all_david_examples():
    results_path = "comparison_david_vm/results.json"

    # Load results
    try:
        with open(results_path, "r") as f:
            data = json.load(f)
            comparisons = data["comparisons"]
    except Exception as e:
        print(f"Error loading results: {e}")
        return

    # Load dataset for source mapping
    print("Loading dataset...")
    try:
        ds = load_dataset("carlesoctav/gpt-eval", split="train")
        prompt_to_source = {item["prompt"]: item["source"] for item in ds}
    except Exception as e:
        print(f"Error loading dataset: {e}")
        return

    sources = ["wildchat", "instruct", "reasoning"]

    for target_source in sources:
        output_file = f"{target_source}_david.md"
        print(f"Writing {target_source} examples to {output_file}...")

        with open(output_file, "w") as f:
            f.write(
                f"# {target_source.capitalize()} Comparison: mm-01 (Model 1) vs ggwp (Model 2)\n\n"
            )

            count = 0
            for i, comp in enumerate(comparisons):
                prompt = comp["prompt"]
                source = prompt_to_source.get(prompt, "unknown")

                if source == target_source:
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
                    f.write(
                        f"MODEL 1 (mm-01) {'[WINNER]' if winner_idx == 0 else ''}\n"
                    )
                    f.write(
                        "================================================================================\n"
                    )
                    f.write(f"{comp['response_1']}\n\n")

                    f.write(
                        "================================================================================\n"
                    )
                    f.write(f"MODEL 2 (ggwp) {'[WINNER]' if winner_idx == 1 else ''}\n")
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

    print("Done!")


if __name__ == "__main__":
    write_all_david_examples()
