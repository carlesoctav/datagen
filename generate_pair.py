import argparse
import asyncio
from pathlib import Path
from typing import Any, Awaitable, Callable

from transformers import AutoTokenizer

from datatrove.data import Document
from datatrove.executor.local import LocalPipelineExecutor
from datatrove.pipeline.filters.base_filter import BaseFilter
from datatrove.pipeline.filters.language_filter import LanguageFilter
from datatrove.pipeline.readers import HuggingFaceDatasetReader
from datatrove.pipeline.inference.run_inference import InferenceConfig, InferenceRunner
from datatrove.pipeline.inference.types import InferenceResult
from datatrove.pipeline.writers import JsonlWriter
import httpx


# Default Configuration
DEFAULT_MODEL_1 = "google/gemma-3-27b-it"
DEFAULT_MODEL_2 = "google/gemma-3-1b-it"
DEFAULT_ENDPOINT_1 = "http://localhost:8000"
DEFAULT_ENDPOINT_2 = "http://localhost:8001"
DEFAULT_LOGS_DIR = Path(__file__).parent / "logs"
CHAT_TEMPLATE_PATH = Path(__file__).parent / "gemma_think.jinja"
MAX_PROMPT_TOKENS = 1024
MAX_GEN_TOKENS = 1024


def dataset_adapter(self, data: dict, path: str, id_in_file: int | str) -> dict:
    """
    Adapter to extract user messages from the dataset.
    Takes the first user message as the prompt for generation.
    """

    dataset_source = data.get("dataset_source", "") or data.get("source", "")
    original_id = data.get("original_id", "")

    return {
        "text": data["prompt"],
        "id": str(id_in_file),
        "metadata": {
            "dataset_source": dataset_source,
            "original_id": original_id,
        },
    }


class SingleTurnFilter(BaseFilter):
    """Filter to keep only single-turn conversations (1 user + 1 assistant)."""

    name = "Single Turn"

    def filter(self, doc: Document) -> bool | tuple[bool, str]:
        num_messages = doc.metadata.get("num_messages", 0)
        if num_messages != 2:
            return False, f"multi_turn_{num_messages}_messages"
        return True


class PromptLengthFilter(BaseFilter):
    """Filter documents based on tokenized prompt length using chat template."""

    name = "Prompt Length"

    def __init__(self, tokenizer, max_tokens: int, exclusion_writer=None):
        super().__init__(exclusion_writer)
        self.tokenizer = tokenizer
        self.max_tokens = max_tokens

    def filter(self, doc: Document) -> bool | tuple[bool, str]:
        chat_messages = [{"role": "user", "content": doc.text}]
        token_ids = self.tokenizer.apply_chat_template(
            chat_messages, add_generation_prompt=True, tokenize=True
        )
        if len(token_ids) >= self.max_tokens:
            return False, f"too_long_{len(token_ids)}_tokens"
        return True


# Global config for model 2 - will be set from main()
MODEL_2_CONFIG = {
    "endpoint_url": None,
    "model_name": None,
}


async def call_model_2(prompt_text: str) -> dict:
    """
    Make a direct API call to Model 2 endpoint.
    Returns the generated text and finish reason.
    """
    endpoint_url = MODEL_2_CONFIG["endpoint_url"]
    model_name = MODEL_2_CONFIG["model_name"]

    payload = {
        "model": model_name,
        "messages": [{"role": "user", "content": prompt_text}],
        "max_tokens": MAX_GEN_TOKENS,
        "temperature": 0.0,  # Greedy sampling
    }

    async with httpx.AsyncClient(timeout=300.0) as client:
        response = await client.post(
            f"{endpoint_url}/chat/completions",
            json=payload,
        )
        response.raise_for_status()
        result = response.json()

        choice = result.get("choices", [{}])[0]
        message = choice.get("message", {})

        return {
            "text": message.get("content", ""),
            "finish_reason": choice.get("finish_reason", ""),
        }


async def pair_generation_rollout(
    document: Document,
    generate: Callable[[dict[str, Any]], Awaitable[InferenceResult]],
) -> dict:
    """
    Rollout function that sends the prompt to BOTH LLM endpoints.

    - Model 1 (chosen): Uses the primary InferenceRunner's generate function
    - Model 2 (rejected): Makes a direct API call to the secondary endpoint

    Returns both responses for the preference pair dataset.
    """
    payload = {
        "messages": [{"role": "user", "content": document.text}],
        "max_tokens": MAX_GEN_TOKENS,
        "temperature": 0.0,  # Greedy sampling
    }

    # Execute both model calls concurrently
    model_1_task = generate(payload)
    model_2_task = call_model_2(document.text)

    result_1, result_2 = await asyncio.gather(model_1_task, model_2_task)

    return {
        "prompt": document.text,
        "chosen": result_1.text,
        "chosen_stop_reason": result_1.finish_reason,
        "rejected": result_2["text"],
        "rejected_stop_reason": result_2["finish_reason"],
        "dataset_source": document.metadata.get("dataset_source", ""),
        "original_id": document.metadata.get("original_id", ""),
        "doc_id": document.id,
    }


def output_adapter(self, doc) -> dict:
    """Extract prompt, chosen, rejected responses and metadata."""
    rollout = doc.metadata.get("rollout_results", [{}])[0]
    return {
        "doc_id": doc.id,
        "original_id": rollout.get("original_id", ""),
        "prompt": rollout.get("prompt", ""),
        "chosen": rollout.get("chosen", ""),
        "chosen_stop_reason": rollout.get("chosen_stop_reason", ""),
        "rejected": rollout.get("rejected", ""),
        "rejected_stop_reason": rollout.get("rejected_stop_reason", ""),
        "dataset_source": rollout.get("dataset_source", ""),
    }


def main():
    parser = argparse.ArgumentParser(
        description="Generate preference pair dataset using two LLM endpoints"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Output directory for generated data",
    )
    parser.add_argument(
        "--dataset",
        type=str,
        required=True,
        help="HuggingFace dataset name",
    )
    # Model 1 (Chosen) configuration
    parser.add_argument(
        "--model-1",
        type=str,
        default=DEFAULT_MODEL_1,
        help=f"Model 1 name for 'chosen' responses (default: {DEFAULT_MODEL_1})",
    )
    parser.add_argument(
        "--endpoint-1",
        type=str,
        default=DEFAULT_ENDPOINT_1,
        help=f"Endpoint URL for Model 1 (default: {DEFAULT_ENDPOINT_1})",
    )
    # Model 2 (Rejected) configuration
    parser.add_argument(
        "--model-2",
        type=str,
        default=DEFAULT_MODEL_2,
        help=f"Model 2 name for 'rejected' responses (default: {DEFAULT_MODEL_2})",
    )
    parser.add_argument(
        "--endpoint-2",
        type=str,
        default=DEFAULT_ENDPOINT_2,
        help=f"Endpoint URL for Model 2 (default: {DEFAULT_ENDPOINT_2})",
    )
    parser.add_argument(
        "--skip",
        type=int,
        default=0,
        help="Skip first N documents from dataset (for resuming)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=-1,
        help="Limit to N documents (-1 for unlimited)",
    )
    parser.add_argument(
        "--force", action="store_true", help="Force overwrite existing output files"
    )
    parser.add_argument(
        "--append", action="store_true", help="Append to existing output (for resuming)"
    )
    parser.add_argument(
        "--lang-filter", action="store_true", help="Filter for English only prompts"
    )
    parser.add_argument(
        "--lang-threshold",
        type=float,
        default=0.65,
        help="Language detection threshold (default: 0.65)",
    )
    parser.add_argument(
        "--shuffle",
        default=False,
        action="store_true",
        help="Shuffle dataset files (disables deterministic resuming with --skip)",
    )
    parser.add_argument(
        "--max-concurrent",
        type=int,
        default=100,
        help="Max concurrent generations (default: 100, lower since we hit 2 endpoints)",
    )
    args = parser.parse_args()

    output_dir = args.output_dir
    dataset_name = args.dataset
    model_1_name = args.model_1
    model_2_name = args.model_2
    endpoint_1_url = args.endpoint_1
    endpoint_2_url = args.endpoint_2

    # Set global config for Model 2 (used by call_model_2)
    MODEL_2_CONFIG["endpoint_url"] = endpoint_2_url
    MODEL_2_CONFIG["model_name"] = model_2_name

    # Load tokenizer with custom chat template for filtering
    tokenizer = AutoTokenizer.from_pretrained(model_1_name)
    tokenizer.chat_template = CHAT_TEMPLATE_PATH.read_text()

    # Guard check: prevent overwriting existing output
    if (
        not args.force
        and not args.append
        and output_dir.exists()
        and any(output_dir.iterdir())
    ):
        existing_files = list(output_dir.glob("*.jsonl*"))
        if existing_files:
            print("=" * 60)
            print("ERROR: Output directory already contains data!")
            print(f"  Path: {output_dir}")
            print(f"  Files: {[f.name for f in existing_files]}")
            print("")
            print("To prevent data loss, this script will NOT overwrite.")
            print("Options:")
            print("  1. Delete/move existing files manually")
            print("  2. Use --output-dir to specify a new path")
            print("  3. Use --force to overwrite (DANGEROUS)")
            print("  4. Use --append --skip N to resume from where you left off")
            print("=" * 60)
            raise SystemExit(1)

    output_dir.mkdir(parents=True, exist_ok=True)
    DEFAULT_LOGS_DIR.mkdir(parents=True, exist_ok=True)

    # Sanitize names for filename
    dataset_name_clean = dataset_name.replace("/", "_")
    model_1_clean = model_1_name.replace("/", "_")
    model_2_clean = model_2_name.replace("/", "_")
    output_filename = (
        f"{dataset_name_clean}_pair_{model_1_clean}_vs_{model_2_clean}.jsonl"
    )

    # Reader for HuggingFace dataset with shuffle
    reader = HuggingFaceDatasetReader(
        dataset=dataset_name,
        dataset_options={"split": "train"},
        streaming=False,
        skip=args.skip,
        limit=args.limit,
        adapter=dataset_adapter,
        doc_progress=True,
        shuffle_files=False,
    )

    # Filter for single-turn conversations
    single_turn_filter = SingleTurnFilter()

    # Filter for prompt length
    prompt_filter = PromptLengthFilter(
        tokenizer=tokenizer,
        max_tokens=MAX_PROMPT_TOKENS,
    )

    # Optional: Filter for English only
    lang_filter = None
    if args.lang_filter:
        lang_filter = LanguageFilter(
            languages=["en"],
            language_threshold=args.lang_threshold,
        )
        print(f"Language filter: English only (threshold: {args.lang_threshold})")

    # Inference configuration for Model 1 (chosen) - use chat endpoint
    config = InferenceConfig(
        server_type="endpoint",
        endpoint_url=endpoint_1_url,
        model_name_or_path=model_1_name,
        model_max_context=MAX_PROMPT_TOKENS,
        use_chat=True,  # Use /v1/chat/completions
        default_generation_params={
            "temperature": 0.0,  # Greedy
        },
        rollouts_per_document=1,
        max_concurrent_generations=args.max_concurrent,
        metric_interval=60,
    )

    # Writer with custom adapter to output preference pairs
    writer = JsonlWriter(
        output_folder=str(output_dir),
        adapter=output_adapter,
    )

    # Build pipeline
    pipeline = [
        reader,
        prompt_filter,
    ]

    # Add language filter if enabled
    if lang_filter:
        pipeline.append(lang_filter)

    # Add inference runner (handles Model 1, while rollout fn handles Model 2)
    pipeline.append(
        InferenceRunner(
            rollout_fn=pair_generation_rollout,
            config=config,
            output_writer=writer,
        )
    )

    # Execute
    executor = LocalPipelineExecutor(
        pipeline=pipeline,
        logging_dir=str(DEFAULT_LOGS_DIR),
        tasks=1,  # Single task for endpoint-based inference
    )

    print(f"Starting PAIR generation pipeline...")
    print(f"Dataset: {dataset_name}")
    print("-" * 50)
    print(f"Model 1 (chosen):  {model_1_name}")
    print(f"Endpoint 1:        {endpoint_1_url}")
    print("-" * 50)
    print(f"Model 2 (rejected): {model_2_name}")
    print(f"Endpoint 2:        {endpoint_2_url}")
    print("-" * 50)
    print(f"Output: {output_dir / output_filename}")
    print(f"Max concurrent: {args.max_concurrent}")
    if args.skip > 0:
        print(f"Skipping first {args.skip} documents (resuming)")
    if args.limit > 0:
        print(f"Limiting to {args.limit} documents")
    if args.shuffle:
        print("WARNING: Shuffle enabled - --skip will not resume deterministically")
    print("-" * 50)

    executor.run()

    print("-" * 50)
    print(f"Pair generation complete! Output saved to: {output_dir / output_filename}")


if __name__ == "__main__":
    main()
