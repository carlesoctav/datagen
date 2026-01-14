#!/usr/bin/env python3
"""
Run GPT evaluation on carlesoctav/gpt-eval dataset.
Reads models from endpoints.json and uses GPT as judge.
"""

import argparse
import asyncio
import json
from pathlib import Path

import litellm
from datasets import Dataset, load_dataset
from tqdm import tqdm

litellm.suppress_debug_info = True

# GPT Judge config
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


def load_endpoints(config_path: str = "endpoints.json") -> list[dict]:
    """Load endpoint configuration from JSON file."""
    path = Path(config_path)
    if not path.exists():
        print(f"Error: {config_path} not found!")
        raise SystemExit(1)
    with open(path) as f:
        return json.load(f)


async def generate_response(
    prompt: str, model: str, endpoint: str, max_tokens: int = 2048
) -> str:
    """Generate response from a model endpoint."""
    try:
        response = await litellm.acompletion(
            model=f"openai/{model}",
            messages=[{"role": "user", "content": prompt}],
            api_base=endpoint,
            api_key="dummy",
            max_tokens=max_tokens,
            temperature=0.0,
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"ERROR: {str(e)}"


async def judge_pair(prompt: str, response_a: str, response_b: str) -> tuple[str, str]:
    """Use GPT to judge which response is better. Returns (winner, explanation)."""
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
            return "A", result
        elif "Winner: B" in result:
            return "B", result
        elif "Winner: Tie" in result:
            return "TIE", result
        else:
            return "TIE", result
    except Exception as e:
        return "ERROR", str(e)


def count_tags(response: str) -> dict:
    """Count reasoning/answer tags in a response."""
    return {
        "has_reasoning_open": "<reasoning>" in response,
        "has_reasoning_close": "</reasoning>" in response,
        "has_answer_open": "<answer>" in response,
        "has_answer_close": "</answer>" in response,
    }


def is_complete(tags: dict) -> bool:
    """Check if response has all four tags."""
    return all(tags.values())


async def run_evaluation(args, endpoint_a: dict, endpoint_b: dict):
    """Main evaluation loop."""
    print("=" * 60)
    print("  GPT Evaluation Runner")
    print("=" * 60)

    name_a = endpoint_a["name"]
    name_b = endpoint_b["name"]

    # Load dataset
    print(f"\nLoading dataset: {args.dataset}")
    ds = load_dataset(args.dataset, split="train")
    print(f"Total prompts: {len(ds)}")

    # Filter by source if specified
    if args.source:
        ds = ds.filter(lambda x: x["source"] == args.source)
        print(f"Filtered to source '{args.source}': {len(ds)} prompts")

    # Limit if specified
    if args.limit > 0:
        ds = ds.select(range(min(args.limit, len(ds))))
        print(f"Limited to: {len(ds)} prompts")

    print(f"\nModel A: {name_a} ({endpoint_a['model']})")
    print(f"Model B: {name_b} ({endpoint_b['model']})")

    results = []
    wins_a, wins_b, ties, errors = 0, 0, 0, 0

    # Tag stats per model
    tag_stats_a = {
        "reasoning_open": 0,
        "reasoning_close": 0,
        "answer_open": 0,
        "answer_close": 0,
        "complete": 0,
    }
    tag_stats_b = {
        "reasoning_open": 0,
        "reasoning_close": 0,
        "answer_open": 0,
        "answer_close": 0,
        "complete": 0,
    }

    for i, item in enumerate(tqdm(ds, desc="Evaluating")):
        prompt = item["prompt"]

        # Generate responses from both models
        response_a, response_b = await asyncio.gather(
            generate_response(prompt, endpoint_a["model"], endpoint_a["endpoint"]),
            generate_response(prompt, endpoint_b["model"], endpoint_b["endpoint"]),
        )

        # Count tags
        tags_a = count_tags(response_a)
        tags_b = count_tags(response_b)

        if tags_a["has_reasoning_open"]:
            tag_stats_a["reasoning_open"] += 1
        if tags_a["has_reasoning_close"]:
            tag_stats_a["reasoning_close"] += 1
        if tags_a["has_answer_open"]:
            tag_stats_a["answer_open"] += 1
        if tags_a["has_answer_close"]:
            tag_stats_a["answer_close"] += 1
        if is_complete(tags_a):
            tag_stats_a["complete"] += 1

        if tags_b["has_reasoning_open"]:
            tag_stats_b["reasoning_open"] += 1
        if tags_b["has_reasoning_close"]:
            tag_stats_b["reasoning_close"] += 1
        if tags_b["has_answer_open"]:
            tag_stats_b["answer_open"] += 1
        if tags_b["has_answer_close"]:
            tag_stats_b["answer_close"] += 1
        if is_complete(tags_b):
            tag_stats_b["complete"] += 1

        # Judge
        winner, explanation = await judge_pair(prompt, response_a, response_b)

        if winner == "A":
            wins_a += 1
            winner_name = name_a
        elif winner == "B":
            wins_b += 1
            winner_name = name_b
        elif winner == "ERROR":
            errors += 1
            winner_name = "error"
        else:
            ties += 1
            winner_name = "tie"

        results.append(
            {
                "original_id": item["original_id"],
                "source": item["source"],
                "prompt": prompt,
                f"response_{name_a}": response_a,
                f"response_{name_b}": response_b,
                "winner": winner_name,
                "explanation": explanation,
            }
        )

        if args.verbose and i < 3:
            print(f"\n[{i + 1}] Winner: {winner_name}")
            print(f"    Prompt: {prompt[:80]}...")

    # Summary
    total = len(results)
    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)
    print(f"\n{name_a}: {wins_a} wins ({wins_a / total * 100:.1f}%)")
    print(f"{name_b}: {wins_b} wins ({wins_b / total * 100:.1f}%)")
    print(f"Ties: {ties} ({ties / total * 100:.1f}%)")
    if errors:
        print(f"Errors: {errors}")

    # Win rate excluding ties
    if wins_a + wins_b > 0:
        print(f"\nWin rate (excl. ties):")
        print(f"  {name_a}: {wins_a / (wins_a + wins_b) * 100:.1f}%")
        print(f"  {name_b}: {wins_b / (wins_a + wins_b) * 100:.1f}%")

    # Tag stats
    print("\n" + "=" * 60)
    print("TAG STATS")
    print("=" * 60)
    print(f"\n{name_a}:")
    print(
        f"  <reasoning>:  {tag_stats_a['reasoning_open']:3d} ({tag_stats_a['reasoning_open'] / total * 100:.1f}%)"
    )
    print(
        f"  </reasoning>: {tag_stats_a['reasoning_close']:3d} ({tag_stats_a['reasoning_close'] / total * 100:.1f}%)"
    )
    print(
        f"  <answer>:     {tag_stats_a['answer_open']:3d} ({tag_stats_a['answer_open'] / total * 100:.1f}%)"
    )
    print(
        f"  </answer>:    {tag_stats_a['answer_close']:3d} ({tag_stats_a['answer_close'] / total * 100:.1f}%)"
    )
    print(
        f"  Complete:     {tag_stats_a['complete']:3d} ({tag_stats_a['complete'] / total * 100:.1f}%)"
    )

    print(f"\n{name_b}:")
    print(
        f"  <reasoning>:  {tag_stats_b['reasoning_open']:3d} ({tag_stats_b['reasoning_open'] / total * 100:.1f}%)"
    )
    print(
        f"  </reasoning>: {tag_stats_b['reasoning_close']:3d} ({tag_stats_b['reasoning_close'] / total * 100:.1f}%)"
    )
    print(
        f"  <answer>:     {tag_stats_b['answer_open']:3d} ({tag_stats_b['answer_open'] / total * 100:.1f}%)"
    )
    print(
        f"  </answer>:    {tag_stats_b['answer_close']:3d} ({tag_stats_b['answer_close'] / total * 100:.1f}%)"
    )
    print(
        f"  Complete:     {tag_stats_b['complete']:3d} ({tag_stats_b['complete'] / total * 100:.1f}%)"
    )

    # Save locally
    output_dir = Path(args.output_dir)
    output_dir.mkdir(exist_ok=True)

    output_file = output_dir / f"{name_a}_vs_{name_b}.jsonl"
    with open(output_file, "w") as f:
        for r in results:
            f.write(json.dumps(r) + "\n")
    print(f"\nSaved to: {output_file}")

    # Save stats
    stats = {
        "name_a": name_a,
        "name_b": name_b,
        "total": total,
        "wins_a": wins_a,
        "wins_b": wins_b,
        "ties": ties,
        "errors": errors,
        "win_rate_a": wins_a / total if total else 0,
        "win_rate_b": wins_b / total if total else 0,
        "tag_stats_a": tag_stats_a,
        "tag_stats_b": tag_stats_b,
    }
    stats_file = output_dir / f"{name_a}_vs_{name_b}_stats.json"
    with open(stats_file, "w") as f:
        json.dump(stats, f, indent=2)
    print(f"Stats saved to: {stats_file}")

    # Upload if requested
    if args.upload:
        print(f"\nUploading to {args.upload}...")
        result_ds = Dataset.from_list(results)
        result_ds.push_to_hub(args.upload, private=False)
        print(f"Uploaded: https://huggingface.co/datasets/{args.upload}")

    return results


def main():
    parser = argparse.ArgumentParser(
        description="Run GPT evaluation on gpt-eval dataset"
    )

    # Dataset args
    parser.add_argument(
        "--dataset",
        type=str,
        default="carlesoctav/gpt-eval",
        help="HuggingFace dataset to evaluate",
    )
    parser.add_argument(
        "--source",
        type=str,
        choices=["instruct", "reasoning", "wildchat"],
        help="Filter by source (optional)",
    )
    parser.add_argument("--limit", type=int, default=0, help="Limit number of prompts")

    # Output
    parser.add_argument(
        "--output_dir", type=str, default="eval_results", help="Output directory"
    )
    parser.add_argument("--upload", type=str, help="HuggingFace repo to upload results")
    parser.add_argument("--verbose", action="store_true", help="Print detailed output")

    args = parser.parse_args()

    # Load endpoints from config
    endpoints = load_endpoints()

    if len(endpoints) < 2:
        print("Error: Need at least 2 endpoints in endpoints.json")
        raise SystemExit(1)

    # Show available endpoints
    print("Available endpoints:")
    for i, ep in enumerate(endpoints):
        print(f"  [{i}] {ep['name']}: {ep['model']}")

    # Use first two endpoints
    endpoint_a = endpoints[0]
    endpoint_b = endpoints[1]

    print(f"\nComparing: {endpoint_a['name']} vs {endpoint_b['name']}")

    asyncio.run(run_evaluation(args, endpoint_a, endpoint_b))


if __name__ == "__main__":
    main()
