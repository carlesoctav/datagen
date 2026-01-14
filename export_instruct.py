import json
from datasets import load_dataset
import warnings

# Suppress warnings
warnings.filterwarnings("ignore")


def write_all_instruct_examples():
    output_file = "instruct.md"

    # 1. Load results
    results_path = "comparison_temp1_full/results.json"
    try:
        with open(results_path, "r") as f:
            data = json.load(f)
            comparisons = data["comparisons"]
    except Exception as e:
        print(f"Error loading results: {e}")
        return

    # 2. Load dataset for source mapping
    print("Loading dataset...")
    try:
        ds = load_dataset("carlesoctav/gpt-eval", split="train")
        prompt_to_source = {item["prompt"]: item["source"] for item in ds}
    except Exception as e:
        print(f"Error loading dataset: {e}")
        return

    print(f"Writing Instruct examples to {output_file}...")

    with open(output_file, "w") as f:
        f.write("# Instruct Comparison: Gemma-3-1b-it (Model 1) vs mm-01 (Model 2)\n\n")

        count = 0
        for i, comp in enumerate(comparisons):
            prompt = comp["prompt"]
            source = prompt_to_source.get(prompt, "unknown")

            # Filter for Instruct source only
            if source == "instruct":
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
                    f"MODEL 1 (google/gemma-3-1b-it) {'[WINNER]' if winner_idx == 0 else ''}\n"
                )
                f.write(
                    "================================================================================\n"
                )
                f.write(f"{comp['response_1']}\n\n")

                f.write(
                    "================================================================================\n"
                )
                f.write(
                    f"MODEL 2 (carlesoctav/mm-01) {'[WINNER]' if winner_idx == 1 else ''}\n"
                )
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
    write_all_instruct_examples()
