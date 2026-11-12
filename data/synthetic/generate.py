"""Regenerates the committed synthetic statements and their golden answers.

    cd backend && uv run python ../data/synthetic/generate.py [--end-date 2026-11-10] [--seed N]

Everything here is fabricated by localledger.demo.generator. No real records.
"""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from localledger.demo.generator import generate

HERE = Path(__file__).resolve().parent


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--end-date", type=date.fromisoformat, default=date(2026, 11, 10))
    parser.add_argument("--seed", type=int, default=20260101)
    args = parser.parse_args()
    dataset = generate(args.end_date, args.seed)
    for name, content in dataset.files.items():
        (HERE / name).write_text(content)
    (HERE / "golden_answers.json").write_text(
        json.dumps({"seed": args.seed, **dataset.golden}, indent=2, sort_keys=True) + "\n"
    )
    print(f"Wrote {len(dataset.records)} synthetic transactions ending {args.end_date}.")


if __name__ == "__main__":
    main()
