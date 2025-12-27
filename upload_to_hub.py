#!/usr/bin/env python3
"""Upload dataset to Hugging Face Hub."""

import argparse
from pathlib import Path

from huggingface_hub import HfApi, create_repo


def main():
    parser = argparse.ArgumentParser(description="Upload dataset to Hugging Face Hub")
    parser.add_argument(
        "--path", type=str, required=True, help="Path to file or directory to upload"
    )
    parser.add_argument(
        "--hub",
        type=str,
        required=True,
        help="Hub repository (e.g., username/repo-name)",
    )
    parser.add_argument(
        "--private", action="store_true", help="Make repository private"
    )
    args = parser.parse_args()

    path = Path(args.path)
    if not path.exists():
        raise FileNotFoundError(f"Path not found: {path}")

    api = HfApi()

    # Create repo if it doesn't exist
    try:
        create_repo(args.hub, repo_type="dataset", private=args.private, exist_ok=True)
        print(f"Repository created/verified: {args.hub}")
    except Exception as e:
        print(f"Note: {e}")

    # Upload
    if path.is_file():
        print(f"Uploading file: {path}")
        api.upload_file(
            path_or_fileobj=str(path),
            path_in_repo=path.name,
            repo_id=args.hub,
            repo_type="dataset",
        )
    else:
        print(f"Uploading directory: {path}")
        api.upload_folder(
            folder_path=str(path),
            repo_id=args.hub,
            repo_type="dataset",
        )

    print(f"✓ Uploaded to https://huggingface.co/datasets/{args.hub}")


if __name__ == "__main__":
    main()
