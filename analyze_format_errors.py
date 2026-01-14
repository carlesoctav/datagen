import json
import numpy as np


def analyze_failures():
    path = "comparison_temp0_full/model2.jsonl"  # mm-01 responses

    print(f"Analyzing {path}...")
    with open(path, "r") as f:
        lines = f.readlines()

    valid_lengths = []
    invalid_rows = []

    for i, line in enumerate(lines):
        data = json.loads(line)
        response = data["response"]
        length = len(response)

        # Check validity (Strict <reasoning>...</reasoning><answer>...</answer>)
        has_tags = "</reasoning>" in response and "</answer>" in response

        if has_tags:
            valid_lengths.append(length)
        else:
            # Analyze why it's invalid
            reason = "Unknown"
            if (
                len(response) > 4096
            ):  # Heuristic: extremely long likely means token limit/loop
                reason = "Likely Loop/Cutoff (Length > 4096)"
            elif response.strip().endswith((".", "!", "?", "}", "]", '"')):
                reason = "Likely Structural Error (Ends naturally but missing tags)"
            else:
                reason = "Likely Cutoff (Ends abruptly)"

            invalid_rows.append(
                {
                    "row": i + 1,
                    "length": length,
                    "reason": reason,
                    "snippet": response[-100:].replace("\n", "\\n"),  # Last 100 chars
                }
            )

    # Stats
    avg_valid = np.mean(valid_lengths) if valid_lengths else 0
    print(
        f"\nValid Responses: {len(valid_lengths)} (Avg Length: {avg_valid:.0f} chars)"
    )
    print(f"Invalid Responses: {len(invalid_rows)}")

    print("\n--- Breakdown of Invalid Responses ---")
    loop_count = 0
    struct_count = 0
    cutoff_count = 0

    for item in invalid_rows:
        print(f"Row {item['row']:<3} | Len: {item['length']:<5} | {item['reason']}")
        print(f'          End: "...{item["snippet"]}"')

        if "Loop" in item["reason"]:
            loop_count += 1
        elif "Structural" in item["reason"]:
            struct_count += 1
        else:
            cutoff_count += 1

    print("-" * 60)
    print(f"SUMMARY:")
    print(f"Likely Loops (Max Tokens):      {loop_count}")
    print(f"Likely Structural Forgetting:   {struct_count}")
    print(f"Ambiguous Cutoffs:              {cutoff_count}")


if __name__ == "__main__":
    analyze_failures()
