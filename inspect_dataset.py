from datasets import load_dataset
import warnings

# Suppress warnings
warnings.filterwarnings("ignore")

try:
    ds = load_dataset("carlesoctav/gpt-eval", split="train")
    print(f"Dataset columns: {ds.column_names}")
    print(f"First item keys: {ds[0].keys()}")
    if "source" in ds.column_names:
        print(f"Unique sources: {set(ds['source'])}")
    elif "subset" in ds.column_names:
        print(f"Unique subsets: {set(ds['subset'])}")
    else:
        print("Could not find source/subset column. Showing first item:")
        print(ds[0])

except Exception as e:
    print(f"Error loading dataset: {e}")
