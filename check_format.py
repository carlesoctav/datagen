import json
import re


def check_format(file_path, model_name):
    print(f"Checking format for {model_name} in {file_path}...")
    try:
        with open(file_path, "r") as f:
            lines = f.readlines()
    except FileNotFoundError:
        print(f"File not found: {file_path}")
        return

    total = 0
    valid = 0
    errors = []

    # Regex to check for <reasoning>... </reasoning> ... <answer> ... </answer>
    # Using dotall to match newlines
    pattern = re.compile(
        r"<reasoning>.*?</reasoning>\s*<answer>.*?</answer>", re.DOTALL
    )

    for i, line in enumerate(lines):
        try:
            data = json.loads(line)
            response = data.get("response", "")
            total += 1

            # Check for tags existence first
            has_reasoning_start = "<reasoning>" in response
            has_reasoning_end = "</reasoning>" in response
            has_answer_start = "<answer>" in response
            has_answer_end = "</answer>" in response

            if (
                has_reasoning_start
                and has_reasoning_end
                and has_answer_start
                and has_answer_end
            ):
                # Check order and structure
                if pattern.search(response):
                    valid += 1
                else:
                    errors.append(
                        f"Row {i + 1}: Tags present but structure incorrect (e.g. text outside tags or wrong order)"
                    )
            else:
                missing = []
                if not has_reasoning_start:
                    missing.append("<reasoning>")
                if not has_reasoning_end:
                    missing.append("</reasoning>")
                if not has_answer_start:
                    missing.append("<answer>")
                if not has_answer_end:
                    missing.append("</answer>")
                errors.append(f"Row {i + 1}: Missing tags {missing}")

        except json.JSONDecodeError:
            print(f"Error decoding JSON at line {i + 1}")

    print(f"Total: {total}")
    print(f"Valid Format: {valid} ({valid / total * 100:.1f}%)")
    print(f"Invalid Format: {total - valid}")
    if errors:
        print("\nFirst 5 errors:")
        for e in errors[:5]:
            print(e)
    print("-" * 40)


if __name__ == "__main__":
    # Check mm-01 from the single_multi comparison (Model 1)
    check_format(
        "comparison_single_multi_full/model1.jsonl", "mm-01 (from single_multi)"
    )

    # Check mm-01 from the temp0 comparison (Model 2)
    check_format("comparison_temp0_full/model2.jsonl", "mm-01 (from temp0)")
