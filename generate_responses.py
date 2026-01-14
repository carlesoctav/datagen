#!/usr/bin/env python3
"""
Generate responses from a single model endpoint for a HuggingFace dataset.
Output: JSONL file with prompt and response pairs.
"""

import argparse
import asyncio
import json
from pathlib import Path

import litellm
from datasets import load_dataset
from tqdm import tqdm

litellm.suppress_debug_info = True

MAX_TOKENS = 1024
TEMPERATURE = 0.7


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


async def process_batch(
    endpoint: str, model: str, prompts: list[str], batch_size: int = 10
) -> list[str]:
    """Process prompts in batches."""
    results = []
    for i in range(0, len(prompts), batch_size):
        batch = prompts[i : i + batch_size]
        tasks = [call_model(endpoint, model, p) for p in batch]
        batch_results = await asyncio.gather(*tasks)
        results.extend(batch_results)
    return results


async def main_async(args):
    """Main async function."""
    print(f"Loading dataset: {args.dataset_name}")
    print(f"Prompt column: {args.prompt_column}")

    # Load dataset
    ds = load_dataset(args.dataset_name, split=args.split)

    if args.limit > 0:
        ds = ds.select(range(min(args.limit, len(ds))))

    print(f"Generating responses for {len(ds)} prompts...")
    print(f"Model: {args.model}")
    print(f"Endpoint: {args.endpoint}")

    # Collect prompts
    prompts = [item[args.prompt_column] for item in ds]

    # Generate responses with progress bar
    results = []
    batch_size = args.batch_size

    for i in tqdm(range(0, len(prompts), batch_size), desc="Generating"):
        batch = prompts[i : i + batch_size]
        tasks = [call_model(args.endpoint, args.model, p) for p in batch]
        batch_results = await asyncio.gather(*tasks)

        for prompt, response in zip(batch, batch_results):
            results.append({"prompt": prompt, "response": response})

    # Save output
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w") as f:
        for item in results:
            f.write(json.dumps(item) + "\n")

    print(f"\nSaved {len(results)} responses to: {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Generate responses from a single model for a dataset"
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
        help="Dataset split (default: train)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Limit number of prompts (0 = no limit)",
    )
    parser.add_argument(
        "--model",
        type=str,
        required=True,
        help="Model name",
    )
    parser.add_argument(
        "--endpoint",
        type=str,
        required=True,
        help="API endpoint URL",
    )
    parser.add_argument(
        "--output",
        type=str,
        required=True,
        help="Output JSONL file path",
    )
    parser.add_argument(
        "--batch_size",
        type=int,
        default=10,
        help="Batch size for concurrent requests (default: 10)",
    )

    args = parser.parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
