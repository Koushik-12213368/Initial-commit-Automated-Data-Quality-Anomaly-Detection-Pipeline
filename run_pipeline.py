#!/usr/bin/env python3
"""CLI entry point for the Automated Data Quality & Anomaly Detection Pipeline."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Ensure project root is on sys.path when invoked as a script
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.pipeline import run_pipeline


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Screen raw daily transactional dumps for data-quality issues."
    )
    p.add_argument(
        "-i",
        "--input",
        default="data/sample_daily_activity.csv",
        help="Path to CSV/XLSX daily dump (default: sample data).",
    )
    p.add_argument(
        "-c",
        "--config",
        default="config/rules.yaml",
        help="Path to rules YAML.",
    )
    p.add_argument(
        "-e",
        "--expected",
        default="data/expected_counts.json",
        help="JSON file with expected record-count band.",
    )
    p.add_argument(
        "--prior-count",
        type=int,
        default=None,
        help="Prior-day record count for day-over-day variance check.",
    )
    p.add_argument(
        "-o",
        "--output-dir",
        default="outputs",
        help="Directory for Excel/CSV artifacts.",
    )
    p.add_argument(
        "--db",
        default="sqlite:///outputs/dq_pipeline.db",
        help="Database URL (sqlite:///... or postgresql://...).",
    )
    p.add_argument(
        "--run-id",
        default=None,
        help="Optional run identifier (auto-generated if omitted).",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = run_pipeline(
        input_path=args.input,
        config_path=args.config,
        expected_path=args.expected,
        prior_count=args.prior_count,
        output_dir=args.output_dir,
        db_url=args.db,
        run_id=args.run_id,
    )

    print("=" * 60)
    print("Data Quality Pipeline — Run Complete")
    print("=" * 60)
    print(f"Run ID:            {result['run_id']}")
    print(f"Input rows:        {result['input_row_count']}")
    print(f"Exceptions:        {result['exception_count']}")
    print(f"Reconciliation:    {result['recon_summary'].get('status')}")
    print(f"Artifacts:")
    for name, path in result["artifacts"].items():
        print(f"  - {name}: {path}")
    print(f"Database:          {result['db_url']}")

    if not result["exceptions"].empty:
        print("\nTop error codes:")
        counts = result["exceptions"]["error_code"].value_counts().head(10)
        for code, n in counts.items():
            print(f"  {code:24s} {n}")

    summary_path = Path(args.output_dir) / f"{result['run_id']}_run_summary.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        k: v
        for k, v in result.items()
        if k not in {"exceptions", "cleaned"}
    }
    summary_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"\nJSON summary:      {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
