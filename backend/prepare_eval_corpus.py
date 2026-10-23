"""Prepare or explicitly reset the isolated evaluation Chroma collection."""

import argparse
import sys

from backend.evaluation_corpus import prepare_corpus, reset_corpus


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reset", action="store_true", help="Reset only the evaluation collection before loading")
    parser.add_argument("--reset-only", action="store_true", help="Delete only the evaluation collection")
    args = parser.parse_args()
    try:
        print((reset_corpus() if args.reset_only else prepare_corpus(reset=args.reset)))
        return 0
    except (ValueError, RuntimeError) as exc:
        print(f"EVALUATION CORPUS ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
