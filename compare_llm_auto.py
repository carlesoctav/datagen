#!/usr/bin/env python3
"""
Automatic LLM comparison and evaluation tool.
Reads prompts from a HuggingFace dataset, sends to multiple endpoints,
evaluates responses using GPT-4o-mini, and counts format compliance.
"""

import argparse
import asyncio
import json
import re
import warnings
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

warnings.filterwarnings("ignore", category=UserWarning, module="pydantic")

import litellm
from datasets import load_dataset
from tqdm import tqdm

# Suppress litellm logging
litellm.suppress_debug_info = True

MAX_TOKENS = 1024
TEMPERATURE = 0.0
JUDGE_MODEL = "github_copilot/gpt-5-mini"  # GitHub Copilot model

# Extra headers for GitHub Copilot
COPILOT_HEADERS = {
    "Editor-Version": "vscode/1.85.0",
    "Editor-Plugin-Version": "copilot/1.0.0",
}


@dataclass
class EvalResult:
    """Result of evaluating a single prompt across all models."""

    prompt: str
    responses: dict[str, str] = field(default_factory=dict)
    scores: dict[str, float] = field(default_factory=dict)
    format_correct: dict[str, bool] = field(default_factory=dict)
    judge_reasoning: dict[str, str] = field(default_factory=dict)


def load_endpoints(config_path: str = "endpoints.json") -> list[dict]:
    """Load endpoint configuration from JSON file."""
    path = Path(config_path)
    if not path.exists():
        print(f"Error: {config_path} not found!")
        raise SystemExit(1)

    with open(path) as f:
        return json.load(f)


def check_format(response: str) -> bool:
    """Check if response contains proper <reasoning> and <answer> tags."""
    has_reasoning_open = "<reasoning>" in response.lower()
    has_reasoning_close = "</reasoning>" in response.lower()
    has_answer_open = "<answer>" in response.lower()
    has_answer_close = "</answer>" in response.lower()

    return all(
        [has_reasoning_open, has_reasoning_close, has_answer_open, has_answer_close]
    )


async def call_model(endpoint: str, model: str, prompt: str) -> str:
    """Call a single model endpoint and return the response."""
    try:
        response = await litellm.acompletion(
            model=f"openai/{model}",
            messages=[{"role": "user", "content": prompt}],
            api_base=endpoint,
            api_key="dummy",
            max_tokens=MAX_TOKENS,
            temperature=TEMPERATURE,
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"Error: {str(e)}"


async def judge_responses(
    prompt: str, responses: dict[str, str]
) -> dict[str, tuple[float, str]]:
    """Use GPT-4o-mini to judge and score responses."""
    results = {}

    for model_name, response in responses.items():
        judge_prompt = f"""You are an expert evaluator. Rate the following response to a given prompt.

**Prompt:**
{prompt}

**Response from {model_name}:**
{response}

**Evaluation Criteria:**
1. Correctness: Is the answer factually correct?
2. Reasoning: Is the reasoning clear and logical?
3. Completeness: Does it fully address the prompt?
4. Format: Is it well-structured?

**Instructions:**
- Provide a brief evaluation (2-3 sentences)
- Give a score between 0.0 and 1.0 (0 = completely wrong, 1 = perfect)

**Output Format:**
Evaluation: <your brief evaluation>
Score: <number between 0.0 and 1.0>
"""

        try:
            judge_response = await litellm.acompletion(
                model=JUDGE_MODEL,
                messages=[{"role": "user", "content": judge_prompt}],
                max_tokens=256,
                temperature=1.0,  # gpt-5 only supports temperature=1
                extra_headers=COPILOT_HEADERS,
            )

            judge_text = judge_response.choices[0].message.content

            # Extract score
            score_match = re.search(r"Score:\s*([\d.]+)", judge_text)
            if score_match:
                score = float(score_match.group(1))
                score = max(0.0, min(1.0, score))  # Clamp to [0, 1]
            else:
                score = 0.5  # Default if parsing fails

            # Extract evaluation
            eval_match = re.search(
                r"Evaluation:\s*(.+?)(?=Score:|$)", judge_text, re.DOTALL
            )
            evaluation = eval_match.group(1).strip() if eval_match else judge_text

            results[model_name] = (score, evaluation)

        except Exception as e:
            results[model_name] = (0.0, f"Judge error: {str(e)}")

    return results


async def evaluate_prompt(endpoints: list[dict], prompt: str) -> EvalResult:
    """Evaluate a single prompt across all models."""
    result = EvalResult(prompt=prompt)

    # Get responses from all models in parallel
    tasks = [call_model(ep["endpoint"], ep["model"], prompt) for ep in endpoints]
    responses = await asyncio.gather(*tasks)

    for ep, response in zip(endpoints, responses):
        name = ep["name"]
        result.responses[name] = response
        result.format_correct[name] = check_format(response)

    # Judge responses
    judge_results = await judge_responses(prompt, result.responses)

    for name, (score, reasoning) in judge_results.items():
        result.scores[name] = score
        result.judge_reasoning[name] = reasoning

    return result


def print_summary(results: list[EvalResult], endpoints: list[dict]):
    """Print summary statistics."""
    model_names = [ep["name"] for ep in endpoints]

    print("\n" + "=" * 80)
    print("EVALUATION SUMMARY")
    print("=" * 80)

    # Calculate averages
    avg_scores = {name: [] for name in model_names}
    format_counts = {name: 0 for name in model_names}

    for result in results:
        for name in model_names:
            if name in result.scores:
                avg_scores[name].append(result.scores[name])
            if name in result.format_correct and result.format_correct[name]:
                format_counts[name] += 1

    total = len(results)

    print(f"\nTotal prompts evaluated: {total}\n")
    print(f"{'Model':<25} {'Avg Score':<12} {'Format Correct':<15} {'Format %':<10}")
    print("-" * 62)

    for name in model_names:
        scores = avg_scores[name]
        avg = sum(scores) / len(scores) if scores else 0.0
        fmt_count = format_counts[name]
        fmt_pct = (fmt_count / total * 100) if total > 0 else 0.0

        print(
            f"{name:<25} {avg:.3f}        {fmt_count}/{total}            {fmt_pct:.1f}%"
        )

    print("=" * 80)


def save_results(results: list[EvalResult], output_path: str):
    """Save detailed results to JSON."""
    output = []
    for result in results:
        output.append(
            {
                "prompt": result.prompt,
                "responses": result.responses,
                "scores": result.scores,
                "format_correct": result.format_correct,
                "judge_reasoning": result.judge_reasoning,
            }
        )

    with open(output_path, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\nDetailed results saved to: {output_path}")


async def main_async(args):
    """Main async function."""
    endpoints = load_endpoints(args.endpoints)

    print("=" * 60)
    print("  LLM Auto Evaluation Tool")
    print("=" * 60)

    print(f"\nLoaded {len(endpoints)} endpoints:")
    for ep in endpoints:
        print(f"  • {ep['name']}: {ep['model']}")

    print(f"\nLoading dataset: {args.dataset_name}")
    print(f"Prompt column: {args.prompt_column}")

    # Load dataset
    if args.split:
        ds = load_dataset(args.dataset_name, split=args.split)
    else:
        ds = load_dataset(args.dataset_name, split="train")

    # Apply limit
    if args.limit > 0:
        ds = ds.select(range(min(args.limit, len(ds))))

    print(f"Evaluating {len(ds)} prompts...\n")

    results = []

    for i, item in enumerate(tqdm(ds, desc="Evaluating")):
        prompt = item[args.prompt_column]
        result = await evaluate_prompt(endpoints, prompt)
        results.append(result)

        # Print progress every N items
        if args.verbose and (i + 1) % 10 == 0:
            print(f"\n--- Sample {i + 1} ---")
            print(f"Prompt: {prompt[:100]}...")
            for name, score in result.scores.items():
                fmt = "✅" if result.format_correct.get(name, False) else "❌"
                print(f"  {name}: {score:.2f} {fmt}")

    # Print summary
    print_summary(results, endpoints)

    # Save results
    if args.output:
        save_results(results, args.output)


def main():
    parser = argparse.ArgumentParser(
        description="Automatic LLM comparison and evaluation using GPT-4o-mini as judge"
    )
    parser.add_argument(
        "--dataset_name",
        type=str,
        required=True,
        help="HuggingFace dataset name",
    )
    parser.add_argument(
        "--prompt_column",
        type=str,
        required=True,
        help="Column name containing the prompts",
    )
    parser.add_argument(
        "--split",
        type=str,
        default="train",
        help="Dataset split to use (default: train)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=100,
        help="Limit number of prompts to evaluate (default: 100)",
    )
    parser.add_argument(
        "--endpoints",
        type=str,
        default="endpoints.json",
        help="Path to endpoints.json config file",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="eval_results.json",
        help="Output file for detailed results (default: eval_results.json)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print detailed progress",
    )

    args = parser.parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
