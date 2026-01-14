import argparse
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


# Default Configuration
DEFAULT_MODEL = "google/gemma-3-1b-it"
DEFAULT_ENDPOINT = "http://localhost:8000"
DEFAULT_LOGS_DIR = Path(__file__).parent / "logs"
CHAT_TEMPLATE_PATH = Path(__file__).parent / "gemma_think.jinja"
MAX_PROMPT_TOKENS = 1024
MAX_GEN_TOKENS = 1024


def dataset_adapter(self, data: dict, path: str, id_in_file: int | str) -> dict:
    """
    Adapter to extract prompt and existing 'generated' column (which becomes 'chosen').
    The 'generated' column from the dataset is preserved as 'chosen'.
    """
    dataset_source = data.get("dataset_source", "") or data.get("source", "")
    original_id = data.get("original_id", "")

    # Get the existing generated column - this becomes "chosen"
    chosen = data.get("generated", "")
    chosen_stop_reason = data.get("stop_reason", "")

    return {
        "text": data["prompt"],
        "id": str(id_in_file),
        "metadata": {
            "dataset_source": dataset_source,
            "original_id": original_id,
            "chosen": chosen,
            "chosen_stop_reason": chosen_stop_reason,
        },
    }


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


async def generation_rollout(
    document: Document,
    generate: Callable[[dict[str, Any]], Awaitable[InferenceResult]],
) -> dict:
    """
    Rollout function that sends the prompt to the LLM endpoint.
    Generates the 'rejected' response while preserving the 'chosen' from metadata.
    """
    payload = {
        "messages": [{"role": "user", "content": document.text}],
        "max_tokens": MAX_GEN_TOKENS,
        "temperature": 0.0,  # Greedy sampling
    }

    result: InferenceResult = await generate(payload)

    return {
        "prompt": document.text,
        "chosen": document.metadata.get("chosen", ""),
        "chosen_stop_reason": document.metadata.get("chosen_stop_reason", ""),
        "rejected": result.text,
        "rejected_stop_reason": result.finish_reason,
        "dataset_source": document.metadata.get("dataset_source", ""),
        "original_id": document.metadata.get("original_id", ""),
        "doc_id": document.id,
    }


def output_adapter(self, doc) -> dict:
    """Extract prompt, chosen (from dataset), rejected (newly generated), and metadata."""
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
        description="Generate rejected responses for preference dataset (keeps existing 'generated' as 'chosen')"
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
        help="HuggingFace dataset name (must have 'prompt' and 'generated' columns)",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=DEFAULT_MODEL,
        help=f"Model name for rejected generation (default: {DEFAULT_MODEL})",
    )
    parser.add_argument(
        "--endpoint",
        type=str,
        default=DEFAULT_ENDPOINT,
        help=f"Endpoint URL (default: {DEFAULT_ENDPOINT})",
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
        "--max-concurrent",
        type=int,
        default=170,
        help="Max concurrent generations (default: 170)",
    )
    args = parser.parse_args()

    output_dir = args.output_dir
    dataset_name = args.dataset
    model_name = args.model
    endpoint_url = args.endpoint

    # Load tokenizer with custom chat template for filtering
    tokenizer = AutoTokenizer.from_pretrained(model_name)
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
    model_name_clean = model_name.replace("/", "_")
    output_filename = f"chosen-4b-rejected-{model_name_clean}.jsonl"

    # Reader for HuggingFace dataset
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

    # Inference configuration - use chat endpoint
    config = InferenceConfig(
        server_type="endpoint",
        endpoint_url=endpoint_url,
        model_name_or_path=model_name,
        model_max_context=MAX_PROMPT_TOKENS,
        use_chat=True,  # Use /v1/chat/completions
        default_generation_params={
            "temperature": 0.0,  # Greedy
        },
        rollouts_per_document=1,
        max_concurrent_generations=args.max_concurrent,
        metric_interval=60,
    )

    # Writer with custom adapter
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

    # Add inference runner
    pipeline.append(
        InferenceRunner(
            rollout_fn=generation_rollout,
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

    print(f"Starting REJECTED generation pipeline...")
    print(f"Dataset: {dataset_name}")
    print(f"  - 'generated' column will be kept as 'chosen'")
    print(f"  - New generation will be 'rejected'")
    print(f"Model (for rejected): {model_name}")
    print(f"Endpoint: {endpoint_url}")
    print(f"Output: {output_dir / output_filename}")
    print(f"Max concurrent: {args.max_concurrent}")
    if args.skip > 0:
        print(f"Skipping first {args.skip} documents (resuming)")
    if args.limit > 0:
        print(f"Limiting to {args.limit} documents")
    print("-" * 50)

    executor.run()

    print("-" * 50)
    print(
        f"Rejected generation complete! Output saved to: {output_dir / output_filename}"
    )


if __name__ == "__main__":
    main()
