#!/usr/bin/env python3
"""
Sample from multiple datasets and run GPT pairwise evaluation.
Uploads results to HuggingFace.
"""

import argparse
import asyncio
import json
import random
from pathlib import Path

from datasets import Dataset, load_dataset
from tqdm import tqdm

import litellm

litellm.suppress_debug_info = True

JUDGE_MODEL = "github_copilot/gpt-5-mini"

COPILOT_HEADERS = {
    "Editor-Version": "vscode/1.85.0",
    "Editor-Plugin-Version": "copilot/1.0.0",
}

JUDGE_PROMPT = """You are an expert evaluator comparing two AI assistant responses.

**User Prompt:**
{prompt}

**Response A:**
{response_a}

**Response B:**
{response_b}

**Task:**
Compare the two responses and decide which one is better overall.
Consider: correctness, helpfulness, clarity, completeness, and reasoning quality.

**Output Format:**
First provide a brief explanation (1-2 sentences), then output your choice.
You MUST end your response with exactly one of these lines:
- "Winner: A" if Response A is better
- "Winner: B" if Response B is better
- "Winner: Tie" if they are equally good

Your evaluation:"""


async def judge_pair(prompt: str, response_a: str, response_b: str) -> str:
    """Use GPT to judge which response is better."""
    try:
        response = await litellm.acompletion(
            model=JUDGE_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": JUDGE_PROMPT.format(
                        prompt=prompt, response_a=response_a, response_b=response_b
                    ),
                }
            ],
            temperature=1.0,
            max_tokens=256,
            extra_headers=COPILOT_HEADERS,
        )
        result = response.choices[0].message.content
        if "Winner: A" in result:
            return "A"
        elif "Winner: B" in result:
            return "B"
        elif "Winner: Tie" in result:
            return "TIE"
        else:
            # Try to infer
            text_lower = result.lower()
            if "response a" in text_lower and "better" in text_lower:
                return "A"
            elif "response b" in text_lower and "better" in text_lower:
                return "B"
            return "TIE"
    except Exception as e:
        print(f"Error: {e}")
        return "ERROR"


async def evaluate_pair(
    name_a: str,
    name_b: str,
    samples_a: list[dict],
    samples_b: list[dict],
    verbose: bool = False,
) -> list[dict]:
    """Evaluate pairs of responses."""
    results = []

    for i, (a, b) in enumerate(tqdm(zip(samples_a, samples_b), total=len(samples_a))):
        # Randomize order to avoid position bias
        if random.random() < 0.5:
            first, second = a, b
            first_name, second_name = name_a, name_b
            order = "AB"
        else:
            first, second = b, a
            first_name, second_name = name_b, name_a
            order = "BA"

        winner = await judge_pair(
            first["prompt"], first["generated"], second["generated"]
        )

        # Map back to original names
        if order == "AB":
            actual_winner = (
                name_a if winner == "A" else (name_b if winner == "B" else "TIE")
            )
        else:
            actual_winner = (
                name_b if winner == "A" else (name_a if winner == "B" else "TIE")
            )

        results.append(
            {
                "prompt": first["prompt"],
                f"response_{name_a}": a["generated"],
                f"response_{name_b}": b["generated"],
                "winner": actual_winner,
                "order": order,
                "raw_judgment": winner,
            }
        )

        if verbose and i < 3:
            print(f"\n--- Sample {i + 1} ---")
            print(f"Prompt: {first['prompt'][:100]}...")
            print(f"Winner: {actual_winner}")

    return results


def sample_dataset(name: str, n: int = 100, seed: int = 42) -> list[dict]:
    """Sample n items from a dataset."""
    ds = load_dataset(name, split="train")
    random.seed(seed)
    indices = random.sample(range(len(ds)), min(n, len(ds)))
    return [ds[i] for i in indices]


def compute_stats(results: list[dict], name_a: str, name_b: str) -> dict:
    """Compute win rates."""
    wins_a = sum(1 for r in results if r["winner"] == name_a)
    wins_b = sum(1 for r in results if r["winner"] == name_b)
    ties = sum(1 for r in results if r["winner"] == "TIE")
    errors = sum(1 for r in results if r["winner"] == "ERROR")
    total = len(results)

    return {
        "total": total,
        name_a: {"wins": wins_a, "rate": wins_a / total if total else 0},
        name_b: {"wins": wins_b, "rate": wins_b / total if total else 0},
        "ties": {"count": ties, "rate": ties / total if total else 0},
        "errors": errors,
    }


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--samples", type=int, default=100)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", type=str, default="gpt_eval_results")
    parser.add_argument("--upload", type=str, help="HuggingFace repo to upload to")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    datasets = {
        "instruct": "carlesoctav/27b-generated-Dolci-Instruct-SFT-No-Tools-instruct-only",
        "reasoning": "carlesoctav/27b-generated-Dolci-Instruct-SFT-No-Tools-reasoning-only",
        "wildchat": "carlesoctav/27b-carlesoctav-Dolci-Instruct-SFT-No-Tools-wildchat-only",
    }

    # Sample from each dataset
    print("Sampling from datasets...")
    samples = {}
    for short_name, full_name in datasets.items():
        print(f"  Loading {short_name}...")
        samples[short_name] = sample_dataset(full_name, args.samples, args.seed)
        print(f"  Got {len(samples[short_name])} samples")

    # Run pairwise comparisons
    comparisons = [
        ("instruct", "reasoning"),
        ("instruct", "wildchat"),
        ("reasoning", "wildchat"),
    ]

    all_results = {}
    all_stats = {}

    for name_a, name_b in comparisons:
        print(f"\n=== Comparing {name_a} vs {name_b} ===")
        results = await evaluate_pair(
            name_a, name_b, samples[name_a], samples[name_b], args.verbose
        )
        all_results[f"{name_a}_vs_{name_b}"] = results

        stats = compute_stats(results, name_a, name_b)
        all_stats[f"{name_a}_vs_{name_b}"] = stats

        print(f"  {name_a}: {stats[name_a]['wins']} wins ({stats[name_a]['rate']:.1%})")
        print(f"  {name_b}: {stats[name_b]['wins']} wins ({stats[name_b]['rate']:.1%})")
        print(f"  Ties: {stats['ties']['count']} ({stats['ties']['rate']:.1%})")

    # Save results
    output_dir = Path(args.output)
    output_dir.mkdir(exist_ok=True)

    # Save stats
    with open(output_dir / "stats.json", "w") as f:
        json.dump(all_stats, f, indent=2)
    print(f"\nSaved stats to {output_dir}/stats.json")

    # Save detailed results
    for comp_name, results in all_results.items():
        with open(output_dir / f"{comp_name}.jsonl", "w") as f:
            for r in results:
                f.write(json.dumps(r) + "\n")
        print(f"Saved {output_dir}/{comp_name}.jsonl")

    # Upload to HuggingFace
    if args.upload:
        print(f"\nUploading to {args.upload}...")
        from huggingface_hub import HfApi

        api = HfApi()

        # Create dataset from all results
        all_rows = []
        for comp_name, results in all_results.items():
            for r in results:
                row = {"comparison": comp_name, **r}
                all_rows.append(row)

        ds = Dataset.from_list(all_rows)
        ds.push_to_hub(args.upload, private=False)
        print(f"Uploaded to https://huggingface.co/datasets/{args.upload}")

    print("\n=== Summary ===")
    for comp_name, stats in all_stats.items():
        names = comp_name.split("_vs_")
        print(f"{comp_name}:")
        print(f"  {names[0]}: {stats[names[0]]['rate']:.1%}")
        print(f"  {names[1]}: {stats[names[1]]['rate']:.1%}")


if __name__ == "__main__":
    asyncio.run(main())
