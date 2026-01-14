import json
from datasets import load_dataset
import warnings

# Suppress warnings
warnings.filterwarnings("ignore")


def print_wildchat_example():
    # 1. Load results
    results_path = "comparison_temp1_full/results.json"
    with open(results_path, "r") as f:
        data = json.load(f)
        comparisons = data["comparisons"]

    # 2. Load dataset for source mapping
    ds = load_dataset("carlesoctav/gpt-eval", split="train")
    prompt_to_source = {item["prompt"]: item["source"] for item in ds}

    # 3. Find a Wildchat example where Model 1 (Gemma) won
    for comp in comparisons:
        prompt = comp["prompt"]
        source = prompt_to_source.get(prompt, "unknown")

        if source == "wildchat" and comp["winner"] == 0:  # Model 1 wins
            print("=" * 80)
            print(f"PROMPT (Source: {source})")
            print("=" * 80)
            print(prompt)
            print("\n" + "=" * 80)
            print("MODEL 1 (google/gemma-3-1b-it) [WINNER]")
            print("=" * 80)
            print(comp["response_1"])
            print("\n" + "=" * 80)
            print("MODEL 2 (carlesoctav/mm-01)")
            print("=" * 80)
            print(comp["response_2"])
            print("\n" + "=" * 80)
            print("JUDGE EXPLANATION")
            print("=" * 80)
            print(comp["explanation"])
            break


if __name__ == "__main__":
    print_wildchat_example()
