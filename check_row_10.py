import json


def check_row(file_path, row_idx):
    print(f"Checking Row {row_idx} in {file_path}...")
    try:
        with open(file_path, "r") as f:
            lines = f.readlines()
            if row_idx <= len(lines):
                data = json.loads(lines[row_idx - 1])
                print(f"Prompt: {data['prompt'][:100]}...")
                print("-" * 40)
                print(f"Response ({len(data['response'])} chars):")
                print(data["response"])
            else:
                print("Row index out of bounds")
    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    check_row("comparison_temp0_full/model2.jsonl", 10)
