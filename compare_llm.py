#!/usr/bin/env python3
"""
Compare multiple LLM endpoints side by side.
Reads endpoint configuration from endpoints.json and takes user input interactively.
"""

import asyncio
import json
import time
import warnings
from pathlib import Path

# Suppress pydantic warnings
warnings.filterwarnings("ignore", category=UserWarning, module="pydantic")

import litellm

# Suppress litellm logging
litellm.suppress_debug_info = True

MAX_TOKENS = 2048
TEMPERATURE = 0

# ANSI color codes
COLORS = [
    "\033[96m",  # Cyan
    "\033[93m",  # Yellow
    "\033[92m",  # Green
    "\033[95m",  # Magenta
    "\033[94m",  # Blue
    "\033[91m",  # Red
]
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"


def load_endpoints(config_path: str = "endpoints.json") -> list[dict]:
    """Load endpoint configuration from JSON file."""
    path = Path(config_path)
    if not path.exists():
        print(f"Error: {config_path} not found!")
        print("Please create endpoints.json with format:")
        print('[{"name": "model1", "endpoint": "http://...", "model": "model-name"}]')
        raise SystemExit(1)

    with open(path) as f:
        return json.load(f)


async def call_model(name: str, endpoint: str, model: str, prompt: str) -> dict:
    """Call a single model endpoint and return the result with timing."""
    start_time = time.perf_counter()

    try:
        response = await litellm.acompletion(
            model=f"openai/{model}",
            messages=[{"role": "user", "content": prompt}],
            api_base=endpoint,
            api_key="dummy",
            max_tokens=MAX_TOKENS,
            temperature=TEMPERATURE,
        )

        elapsed = time.perf_counter() - start_time
        content = response.choices[0].message.content

        return {
            "name": name,
            "success": True,
            "content": content,
            "elapsed": elapsed,
        }
    except Exception as e:
        elapsed = time.perf_counter() - start_time
        return {
            "name": name,
            "success": False,
            "content": f"Error: {str(e)}",
            "elapsed": elapsed,
        }


async def compare_all(endpoints: list[dict], prompt: str) -> None:
    """Call all endpoints in parallel and display results."""
    tasks = [
        call_model(ep["name"], ep["endpoint"], ep["model"], prompt) for ep in endpoints
    ]

    results = await asyncio.gather(*tasks)

    # Display results
    print("\n" + "=" * 80)
    for i, result in enumerate(results):
        color = COLORS[i % len(COLORS)]
        status = "✅" if result["success"] else "❌"

        # Header with color
        print(
            f"\n{color}{BOLD}{status} [{result['name']}]{RESET} {DIM}({result['elapsed']:.2f}s){RESET}"
        )
        print(f"{color}{'-' * 40}{RESET}")

        # Content with color
        print(f"{color}{result['content']}{RESET}")

        print(f"{color}{'-' * 40}{RESET}")
    print("=" * 80 + "\n")


def main():
    """Main interactive loop."""
    print("=" * 60)
    print("  LLM Comparison Tool")
    print("=" * 60)

    endpoints = load_endpoints()

    print(f"\nLoaded {len(endpoints)} endpoints:")
    for ep in endpoints:
        print(f"  • {ep['name']}: {ep['model']}")

    print("\nCommands:")
    print("  • Type prompt + Enter for single line")
    print(
        '  • Type """ or \\ then Enter for multiline (preserves spaces), end with ###'
    )
    print("  • Type 'exit' to quit\n")

    while True:
        try:
            lines = []
            first_line = input("You: ")

            # Check commands (strip only for command detection)
            if not first_line.strip():
                continue

            if first_line.strip().lower() in ("exit", "quit", "q"):
                print("Goodbye!")
                break

            # Multiline mode: type '"""' or '\' to start, '###' to end
            if first_line.rstrip().endswith("\\") or first_line.lstrip().startswith(
                '"""'
            ):
                if first_line.rstrip().endswith("\\"):
                    lines.append(first_line.rstrip()[:-1])  # Remove trailing backslash
                elif first_line.lstrip().startswith('"""'):
                    # Include content after """ on the same line
                    rest = first_line.lstrip()[3:]  # Remove """
                    if rest.strip():
                        lines.append(rest)
                print(
                    "  (Multiline mode: paste your text, end with '###' on a new line)"
                )
                while True:
                    line = input("... ")
                    if line.rstrip() == "###":
                        break
                    lines.append(line)
            else:
                lines.append(first_line)

            prompt = "\n".join(lines)
            asyncio.run(compare_all(endpoints, prompt))

        except (KeyboardInterrupt, EOFError):
            print("\nGoodbye!")
            break


if __name__ == "__main__":
    main()
