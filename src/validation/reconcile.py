"""Record-count reconciliation and day-over-day variance checks."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd


def reconcile_counts(
    current_count: int,
    config: dict[str, Any],
    expected_path: str | Path | None = None,
    prior_count: int | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """
    Compare dump volume against expected band and optional prior-day count.

    Returns (exceptions_df, reconciliation_summary_dict).
    """
    recon_cfg = dict(config.get("reconciliation", {}))
    rows: list[dict[str, Any]] = []

    if expected_path:
        path = Path(expected_path)
        if path.exists():
            with path.open(encoding="utf-8") as fh:
                expected = json.load(fh)
            if expected.get("expected_count_min") is not None:
                recon_cfg["expected_count_min"] = expected["expected_count_min"]
            if expected.get("expected_count_max") is not None:
                recon_cfg["expected_count_max"] = expected["expected_count_max"]

    min_c = recon_cfg.get("expected_count_min")
    max_c = recon_cfg.get("expected_count_max")
    tolerance_pct = float(recon_cfg.get("prior_day_tolerance_pct", 25.0))

    summary: dict[str, Any] = {
        "current_count": current_count,
        "expected_count_min": min_c,
        "expected_count_max": max_c,
        "prior_count": prior_count,
        "prior_day_tolerance_pct": tolerance_pct,
        "dod_variance_pct": None,
        "status": "PASS",
    }

    if min_c is not None and current_count < int(min_c):
        summary["status"] = "FAIL"
        rows.append(
            {
                "row_index": -1,
                "error_code": "RECON_COUNT_LOW",
                "field": "_record_count",
                "raw_value": str(current_count),
                "message": (
                    f"Record count {current_count} is below expected minimum {min_c}."
                ),
            }
        )

    if max_c is not None and current_count > int(max_c):
        summary["status"] = "FAIL"
        rows.append(
            {
                "row_index": -1,
                "error_code": "RECON_COUNT_HIGH",
                "field": "_record_count",
                "raw_value": str(current_count),
                "message": (
                    f"Record count {current_count} exceeds expected maximum {max_c}."
                ),
            }
        )

    if prior_count is not None and prior_count > 0:
        variance_pct = abs(current_count - prior_count) / prior_count * 100.0
        summary["dod_variance_pct"] = round(variance_pct, 2)
        if variance_pct > tolerance_pct:
            summary["status"] = "FAIL"
            rows.append(
                {
                    "row_index": -1,
                    "error_code": "RECON_DOD_VARIANCE",
                    "field": "_record_count",
                    "raw_value": str(current_count),
                    "message": (
                        f"Day-over-day variance {variance_pct:.1f}% "
                        f"(current={current_count}, prior={prior_count}) "
                        f"exceeds tolerance {tolerance_pct}%."
                    ),
                }
            )

    exceptions = pd.DataFrame(
        rows,
        columns=["row_index", "error_code", "field", "raw_value", "message"],
    )
    return exceptions, summary
