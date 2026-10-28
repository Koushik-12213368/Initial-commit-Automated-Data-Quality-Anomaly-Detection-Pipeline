"""Missing key-field and duplicate-ID checks."""

from __future__ import annotations

from typing import Any

import pandas as pd


def check_missing_keys(
    df: pd.DataFrame,
    config: dict[str, Any],
) -> pd.DataFrame:
    """Flag null/blank values on configured key fields."""
    rows: list[dict[str, Any]] = []
    key_fields = config.get("dataset", {}).get("key_fields", [])
    row_id_col = "_row_id" if "_row_id" in df.columns else None

    for field in key_fields:
        if field not in df.columns:
            rows.append(
                {
                    "row_index": -1,
                    "error_code": "MISS_KEY_FIELD",
                    "field": field,
                    "raw_value": "",
                    "message": f"Required key column '{field}' is missing from the file.",
                }
            )
            continue

        series = df[field]
        blank = series.isna() | (series.astype(str).str.strip() == "") | (
            series.astype(str).str.lower().isin(["nan", "none", "<na>"])
        )
        for i in df.index[blank]:
            rid = int(df.at[i, "_row_id"]) if row_id_col else int(i)
            rows.append(
                {
                    "row_index": rid,
                    "error_code": "MISS_KEY_FIELD",
                    "field": field,
                    "raw_value": "",
                    "message": f"Required key field '{field}' is missing or blank.",
                }
            )

    return pd.DataFrame(
        rows,
        columns=["row_index", "error_code", "field", "raw_value", "message"],
    )


def check_duplicate_ids(
    df: pd.DataFrame,
    id_column: str = "transaction_id",
) -> pd.DataFrame:
    """Flag duplicate transaction identifiers."""
    rows: list[dict[str, Any]] = []
    if id_column not in df.columns:
        return pd.DataFrame(
            rows,
            columns=["row_index", "error_code", "field", "raw_value", "message"],
        )

    row_id_col = "_row_id" if "_row_id" in df.columns else None
    dup_mask = df[id_column].notna() & df[id_column].astype(str).str.strip().ne("") & df.duplicated(
        subset=[id_column], keep=False
    )
    for i in df.index[dup_mask]:
        rid = int(df.at[i, "_row_id"]) if row_id_col else int(i)
        val = df.at[i, id_column]
        rows.append(
            {
                "row_index": rid,
                "error_code": "DUP_TRANSACTION_ID",
                "field": id_column,
                "raw_value": str(val),
                "message": f"Duplicate {id_column}='{val}' in the daily dump.",
            }
        )

    return pd.DataFrame(
        rows,
        columns=["row_index", "error_code", "field", "raw_value", "message"],
    )
