import json
import re


def check_python_formatting():
    path = "comparison_temp0_full/model2.jsonl"  # mm-01

    print(f"Checking Python code block formatting in {path}...")
    try:
        with open(path, "r") as f:
            lines = f.readlines()
    except FileNotFoundError:
        print(f"File not found: {path}")
        return

    total_code_tasks = 0
    correct_format = 0

    # Regex to detect prompts asking for Python code
    python_prompt_regex = re.compile(r"python|def |import |class ", re.IGNORECASE)

    # Regex to detect correct ```python block
    python_block_regex = re.compile(r"```python", re.IGNORECASE)

    for i, line in enumerate(lines):
        data = json.loads(line)
        prompt = data["prompt"]
        response = data["response"]

        # Heuristic: Does the prompt ask for code?
        if python_prompt_regex.search(prompt):
            total_code_tasks += 1

            if python_block_regex.search(response):
                correct_format += 1
            else:
                # Print a few misses to see if it's a false negative or actual failure
                if total_code_tasks <= 5:
                    print(f"\n[MISS] Row {i + 1}")
                    print(f"Prompt snippet: {prompt[:100]}...")
                    print(
                        f"Response snippet: {response[-200:].replace(chr(10), ' ')}..."
                    )

    print("\n" + "=" * 40)
    print("PYTHON FORMATTING STATS")
    print("=" * 40)
    print(f"Prompts likely requesting Python/Code: {total_code_tasks}")
    print(f"Responses containing ```python:       {correct_format}")
    print(
        f"Compliance Rate:                       {correct_format / total_code_tasks * 100:.1f}%"
    )


if __name__ == "__main__":
    check_python_formatting()
