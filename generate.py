"""
Dataset generation script using datatrove with an external LLM endpoint.

Reads from allenai/Dolci-Think-SFT-7B dataset, processes single-turn conversations
(len(messages) < 2), and generates responses via localhost:8000 endpoint.

Server uses custom gemma_think.jinja chat template for reasoning format.
Filters prompts to fit within 2048 token context.
"""

from pathlib import Path
from typing import Any, Awaitable, Callable

from transformers import AutoTokenizer

from datatrove.data import Document
from datatrove.executor.local import LocalPipelineExecutor
from datatrove.pipeline.filters.base_filter import BaseFilter
from datatrove.pipeline.readers import HuggingFaceDatasetReader
from datatrove.pipeline.inference.run_inference import InferenceConfig, InferenceRunner
from datatrove.pipeline.inference.types import InferenceResult
from datatrove.pipeline.writers import JsonlWriter


# Configuration
DATASET_NAME = "allenai/Dolci-Think-SFT-7B"
MODEL_NAME = "google/gemma-3-4b-it"
ENDPOINT_URL = "http://localhost:8000"
OUTPUT_DIR = Path(__file__).parent / "output"
LOGS_DIR = Path(__file__).parent / "logs"
CHAT_TEMPLATE_PATH = Path(__file__).parent / "gemma_think.jinja"
MAX_PROMPT_TOKENS = 2048
MAX_GEN_TOKENS = 2048

# Load tokenizer with custom chat template for filtering
TOKENIZER = AutoTokenizer.from_pretrained(MODEL_NAME)
TOKENIZER.chat_template = CHAT_TEMPLATE_PATH.read_text()


def dataset_adapter(self, data: dict, path: str, id_in_file: int | str) -> dict:
    """
    Adapter to extract user messages from the dataset.

    Takes the first user message as the prompt for generation.
    """
    messages = data.get("messages", [])

    if not messages:
        return {"text": ""}  # Empty text will be skipped by reader

    # Find the first user message as prompt
    first_message = messages[0]
    if first_message.get("role") != "user":
        return {"text": ""}

    prompt = first_message.get("content", "")
    if not prompt:
        return {"text": ""}

    return {
        "text": prompt,
        "id": str(id_in_file),
    }


class PromptLengthFilter(BaseFilter):
    """Filter documents based on tokenized prompt length using chat template."""

    name = "📏 Prompt Length"

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

    Uses chat endpoint - server applies custom chat template.
    """
    payload = {
        "messages": [{"role": "user", "content": document.text}],
        "max_tokens": MAX_GEN_TOKENS,
        "temperature": 0.0,  # Greedy sampling
    }

    result: InferenceResult = await generate(payload)

    return {
        "prompt": document.text,
        "generated": result.text,
        "stop_reason": result.finish_reason,
    }


def output_adapter(self, doc) -> dict:
    """Extract prompt, generated response, and stop reason."""
    rollout = doc.metadata.get("rollout_results", [{}])[0]
    return {
        "prompt": rollout.get("prompt", ""),
        "generated": rollout.get("generated", ""),
        "stop_reason": rollout.get("stop_reason", ""),
    }


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    # Sanitize names for filename
    dataset_name_clean = DATASET_NAME.replace("/", "_")
    model_name_clean = MODEL_NAME.replace("/", "_")
    output_filename = f"{dataset_name_clean}_{model_name_clean}_v2.jsonl"

    # Reader for HuggingFace dataset
    reader = HuggingFaceDatasetReader(
        dataset=DATASET_NAME,
        dataset_options={"split": "train"},
        streaming=True,
        adapter=dataset_adapter,
        doc_progress=True,
    )

    # Filter for prompt length
    prompt_filter = PromptLengthFilter(
        tokenizer=TOKENIZER,
        max_tokens=MAX_PROMPT_TOKENS,
    )

    # Inference configuration - use chat endpoint
    config = InferenceConfig(
        server_type="endpoint",
        endpoint_url=ENDPOINT_URL,
        model_name_or_path=MODEL_NAME,
        model_max_context=MAX_PROMPT_TOKENS,
        use_chat=True,  # Use /v1/chat/completions
        default_generation_params={
            "temperature": 0.0,  # Greedy
        },
        rollouts_per_document=1,
        max_concurrent_generations=170,  # Adjust based on your endpoint capacity
        metric_interval=60,
    )

    # Writer with custom adapter to output only prompt, answer, finish_reason
    writer = JsonlWriter(
        output_folder=str(OUTPUT_DIR),
        output_filename=output_filename,
        adapter=output_adapter,
    )

    # Build pipeline
    pipeline = [
        reader,
        prompt_filter,
        InferenceRunner(
            rollout_fn=generation_rollout,
            config=config,
            output_writer=writer,
        ),
    ]

    # Execute
    executor = LocalPipelineExecutor(
        pipeline=pipeline,
        logging_dir=str(LOGS_DIR),
        tasks=1,  # Single task for endpoint-based inference
    )

    print(f"Starting generation pipeline...")
    print(f"Dataset: {DATASET_NAME}")
    print(f"Endpoint: {ENDPOINT_URL}")
    print(f"Output: {OUTPUT_DIR / output_filename}")
    print("-" * 50)

    executor.run()

    print("-" * 50)
    print(f"Generation complete! Output saved to: {OUTPUT_DIR / output_filename}")


if __name__ == "__main__":
    main()
