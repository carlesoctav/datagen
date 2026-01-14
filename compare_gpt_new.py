#!/usr/bin/env python3
"""
Pairwise comparison of two model outputs using GPT as judge (Alpaca Eval style).
Generates responses from two models (without client-side system prompts),
then compares them head-to-head using ThreadPoolExecutor.
"""

import argparse
import asyncio
import json
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import litellm
from datasets import load_dataset
from tqdm import tqdm

litellm.suppress_debug_info = True
warnings.filterwarnings("ignore", message=".*Pydantic.*")

JUDGE_MODEL = "github_copilot/gpt-5-mini"

COPILOT_HEADERS = {
    "Editor-Version": "vscode/1.85.0",
    "Editor-Plugin-Version": "copilot/1.0.0",
}

JUDGE_PROMPT_TEMPLATE = """You are an expert evaluator comparing two AI assistant responses.

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


async def generate_response(
    model: str, base_url: str, prompt: str, idx: int
) -> tuple[int, dict]:
    """Generate a response from a model."""
    try:
        # No system prompt provided, relying on server default
        messages = [{"role": "user", "content": prompt}]

        response = await litellm.acompletion(
            model=f"openai/{model}",
            api_base=base_url,
            api_key="dummy",
            messages=messages,
            temperature=0,
        )
        return idx, {"prompt": prompt, "response": response.choices[0].message.content}
    except Exception as e:
        return idx, {"prompt": prompt, "response": f"Error: {str(e)}"}


async def generate_all_responses(
    model: str,
    base_url: str,
    prompts: list[str],
    desc: str,
    max_concurrent: int = 16,
) -> list[dict]:
    """Generate responses for all prompts from a model in parallel."""
    semaphore = asyncio.Semaphore(max_concurrent)

    async def limited_generate(idx: int, prompt: str):
        async with semaphore:
            return await generate_response(model, base_url, prompt, idx)

    tasks = [limited_generate(i, p) for i, p in enumerate(prompts)]
    results = [None] * len(prompts)

    for coro in tqdm(asyncio.as_completed(tasks), total=len(tasks), desc=desc):
        idx, result = await coro
        results[idx] = result

    return results


def judge_pair_sync(
    idx: int, prompt: str, response_a: str, response_b: str
) -> tuple[int, int, str]:
    """
    Synchronous version of judge_pair for ThreadPoolExecutor.
    Returns: (idx, winner, explanation)
        winner: 0 if A wins, 1 if B wins, -1 if tie
    """
    judge_prompt = JUDGE_PROMPT_TEMPLATE.format(
        prompt=prompt, response_a=response_a, response_b=response_b
    )

    try:
        response = litellm.completion(
            model=JUDGE_MODEL,
            messages=[{"role": "user", "content": judge_prompt}],
            max_tokens=256,
            temperature=1.0,
            extra_headers=COPILOT_HEADERS,
        )

        judge_text = response.choices[0].message.content

        # Parse winner
        if "Winner: A" in judge_text:
            return idx, 0, judge_text
        elif "Winner: B" in judge_text:
            return idx, 1, judge_text
        elif "Winner: Tie" in judge_text:
            return idx, -1, judge_text
        else:
            text_lower = judge_text.lower()
            if "response a" in text_lower and "better" in text_lower:
                return idx, 0, judge_text
            elif "response b" in text_lower and "better" in text_lower:
                return idx, 1, judge_text
            else:
                return idx, -1, f"Could not parse: {judge_text}"

    except Exception as e:
        return idx, -1, f"Error: {str(e)}"


def load_prompts(dataset_name: str) -> list[str]:
    """Load prompts from HuggingFace dataset."""
    ds = load_dataset(dataset_name, split="train")
    return [item["prompt"] for item in ds]


def save_jsonl(data: list[dict], path: Path):
    """Save data to JSONL file."""
    with open(path, "w") as f:
        for item in data:
            f.write(json.dumps(item) + "\n")


async def main_async(args):
    """Main async function."""
    print("=" * 60)
    print("  Pairwise Comparison (Server-Side Prompting)")
    print("=" * 60)

    # Create output directory
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load prompts
    print(f"\nLoading prompts: {args.dataset}")
    prompts = load_prompts(args.dataset)

    if args.limit > 0:
        prompts = prompts[: args.limit]

    n = len(prompts)
    print(f"Total prompts: {n}")

    # Generate responses from both models (No system prompts passed)
    print(f"\nGenerating responses from {args.model_1}...")
    responses_1 = await generate_all_responses(
        args.model_1, args.base_url_1, prompts, f"Model 1 ({args.model_1})"
    )

    print(f"\nGenerating responses from {args.model_2}...")
    responses_2 = await generate_all_responses(
        args.model_2, args.base_url_2, prompts, f"Model 2 ({args.model_2})"
    )

    # Save model responses
    model1_path = output_dir / "model1.jsonl"
    model2_path = output_dir / "model2.jsonl"
    save_jsonl(responses_1, model1_path)
    save_jsonl(responses_2, model2_path)
    print(f"\nSaved model 1 responses to: {model1_path}")
    print(f"Saved model 2 responses to: {model2_path}")

    # Parallel judging with ThreadPoolExecutor
    print(f"\nJudging with {JUDGE_MODEL} (parallel, {args.workers} workers)...")

    results = [None] * n
    wins_1 = 0
    wins_2 = 0
    ties = 0

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(
                judge_pair_sync,
                i,
                prompts[i],
                responses_1[i]["response"],
                responses_2[i]["response"],
            ): i
            for i in range(n)
        }

        for future in tqdm(as_completed(futures), total=n, desc="Judging"):
            idx, winner, explanation = future.result()

            if winner == 0:
                wins_1 += 1
                winner_name = args.model_1
            elif winner == 1:
                wins_2 += 1
                winner_name = args.model_2
            else:
                ties += 1
                winner_name = "tie"

            results[idx] = {
                "prompt": prompts[idx],
                "response_1": responses_1[idx]["response"],
                "response_2": responses_2[idx]["response"],
                "winner": winner,
                "winner_name": winner_name,
                "explanation": explanation,
            }

            if args.verbose:
                print(f"\n[{idx + 1}] Winner: {winner_name}")
                print(f"    {explanation[:100]}...")

    # Print summary
    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)
    print(f"\n{args.model_1}: {wins_1} wins ({wins_1 / n * 100:.1f}%)")
    print(f"{args.model_2}: {wins_2} wins ({wins_2 / n * 100:.1f}%)")
    print(f"Ties: {ties} ({ties / n * 100:.1f}%)")
    print()

    # Win rate (excluding ties)
    wr_1 = 0.0
    wr_2 = 0.0
    if wins_1 + wins_2 > 0:
        wr_1 = wins_1 / (wins_1 + wins_2) * 100
        wr_2 = wins_2 / (wins_1 + wins_2) * 100
        print(f"Win rate (excl. ties):")
        print(f"  {args.model_1}: {wr_1:.1f}%")
        print(f"  {args.model_2}: {wr_2:.1f}%")

    print("=" * 60)

    # Save results
    results_path = output_dir / "results.json"
    with open(results_path, "w") as f:
        json.dump({"comparisons": results}, f, indent=2)
    print(f"\nResults saved to: {results_path}")

    # Save stats
    stats = {
        "total": n,
        "wins_1": wins_1,
        "wins_2": wins_2,
        "ties": ties,
        "model_1": args.model_1,
        "model_2": args.model_2,
        "base_url_1": args.base_url_1,
        "base_url_2": args.base_url_2,
        "win_rate_1": wins_1 / n * 100 if n > 0 else 0,
        "win_rate_2": wins_2 / n * 100 if n > 0 else 0,
        "win_rate_excl_ties_1": wr_1,
        "win_rate_excl_ties_2": wr_2,
    }
    stats_path = output_dir / "stats.json"
    with open(stats_path, "w") as f:
        json.dump(stats, f, indent=2)
    print(f"Stats saved to: {stats_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Pairwise comparison of two models (Server-Side Prompting)"
    )
    parser.add_argument(
        "--dataset",
        type=str,
        default="carlesoctav/gpt-eval",
        help="HuggingFace dataset with prompts",
    )
    parser.add_argument(
        "--model_1",
        type=str,
        required=True,
        help="First model name",
    )
    parser.add_argument(
        "--base_url_1",
        type=str,
        required=True,
        help="Base URL for first model",
    )
    parser.add_argument(
        "--model_2",
        type=str,
        required=True,
        help="Second model name",
    )
    parser.add_argument(
        "--base_url_2",
        type=str,
        required=True,
        help="Base URL for second model",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Limit number of prompts (0 = no limit)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="comparison_output",
        help="Output directory for results",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=8,
        help="Number of parallel workers for judging",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print each comparison result",
    )

    args = parser.parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
