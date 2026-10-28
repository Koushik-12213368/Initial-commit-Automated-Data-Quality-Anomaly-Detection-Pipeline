"""Range and boundary checks for numeric metrics."""

from __future__ import annotations

from typing import Any

import pandas as pd


def run_range_checks(
    df: pd.DataFrame,
    config: dict[str, Any],
) -> pd.DataFrame:
    """Flag values outside configured [min, max] bounds."""
    rows: list[dict[str, Any]] = []
    ranges: dict[str, dict[str, Any]] = config.get("dataset", {}).get("numeric_range", {})
    row_id_col = "_row_id" if "_row_id" in df.columns else None

    for field, bounds in ranges.items():
        if field not in df.columns:
            continue
        numeric = pd.to_numeric(df[field], errors="coerce")
        min_v = bounds.get("min")
        max_v = bounds.get("max")

        if min_v is not None:
            below = numeric.notna() & (numeric < float(min_v))
            for i, val in numeric[below].items():
                rid = int(df.at[i, "_row_id"]) if row_id_col else int(i)
                rows.append(
                    {
                        "row_index": rid,
                        "error_code": "RANGE_BELOW_MIN",
                        "field": field,
                        "raw_value": str(val),
                        "message": f"'{field}'={val} is below minimum {min_v}.",
                    }
                )

        if max_v is not None:
            above = numeric.notna() & (numeric > float(max_v))
            for i, val in numeric[above].items():
                rid = int(df.at[i, "_row_id"]) if row_id_col else int(i)
                rows.append(
                    {
                        "row_index": rid,
                        "error_code": "RANGE_ABOVE_MAX",
                        "field": field,
                        "raw_value": str(val),
                        "message": f"'{field}'={val} exceeds maximum {max_v}.",
                    }
                )

    return pd.DataFrame(
        rows,
        columns=["row_index", "error_code", "field", "raw_value", "message"],
    )
