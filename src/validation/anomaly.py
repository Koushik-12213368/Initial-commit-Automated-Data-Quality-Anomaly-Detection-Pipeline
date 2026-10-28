"""Statistical anomaly detection via Z-score and IQR fences."""

from __future__ import annotations

from typing import Any

import pandas as pd


def run_anomaly_detection(
    df: pd.DataFrame,
    config: dict[str, Any],
) -> pd.DataFrame:
    """
    Flag outliers using both Z-score and IQR methods.

    A row may receive both ANOMALY_ZSCORE and ANOMALY_IQR for the same field
    when it fails both tests — useful for dashboard drill-down.
    """
    rows: list[dict[str, Any]] = []
    anomaly_cfg = config.get("anomaly", {})
    z_thresh = float(anomaly_cfg.get("zscore_threshold", 3.0))
    iqr_k = float(anomaly_cfg.get("iqr_multiplier", 1.5))
    min_rows = int(anomaly_cfg.get("min_rows_for_stats", 10))
    metrics = config.get("dataset", {}).get("anomaly_metrics", [])
    row_id_col = "_row_id" if "_row_id" in df.columns else None

    if len(df) < min_rows:
        return pd.DataFrame(
            rows,
            columns=["row_index", "error_code", "field", "raw_value", "message"],
        )

    for field in metrics:
        if field not in df.columns:
            continue
        numeric = pd.to_numeric(df[field], errors="coerce")
        valid = numeric.dropna()
        if len(valid) < min_rows:
            continue

        mean = float(valid.mean())
        std = float(valid.std(ddof=1))
        q1 = float(valid.quantile(0.25))
        q3 = float(valid.quantile(0.75))
        iqr = q3 - q1
        lower = q1 - iqr_k * iqr
        upper = q3 + iqr_k * iqr

        for i, val in numeric.items():
            if pd.isna(val):
                continue
            rid = int(df.at[i, "_row_id"]) if row_id_col else int(i)
            v = float(val)

            if std > 0:
                z = (v - mean) / std
                if abs(z) >= z_thresh:
                    rows.append(
                        {
                            "row_index": rid,
                            "error_code": "ANOMALY_ZSCORE",
                            "field": field,
                            "raw_value": str(v),
                            "message": (
                                f"'{field}'={v} has |Z|={abs(z):.2f} "
                                f"(threshold={z_thresh}, mean={mean:.2f}, std={std:.2f})."
                            ),
                        }
                    )

            if iqr > 0 and (v < lower or v > upper):
                rows.append(
                    {
                        "row_index": rid,
                        "error_code": "ANOMALY_IQR",
                        "field": field,
                        "raw_value": str(v),
                        "message": (
                            f"'{field}'={v} outside IQR fence "
                            f"[{lower:.2f}, {upper:.2f}] (k={iqr_k})."
                        ),
                    }
                )

    return pd.DataFrame(
        rows,
        columns=["row_index", "error_code", "field", "raw_value", "message"],
    )


def metric_summary(df: pd.DataFrame, metrics: list[str]) -> pd.DataFrame:
    """Return descriptive stats used in the Excel summary report."""
    records = []
    for field in metrics:
        if field not in df.columns:
            continue
        numeric = pd.to_numeric(df[field], errors="coerce").dropna()
        if numeric.empty:
            continue
        records.append(
            {
                "metric": field,
                "count": int(numeric.count()),
                "mean": float(numeric.mean()),
                "std": float(numeric.std(ddof=1)) if len(numeric) > 1 else 0.0,
                "min": float(numeric.min()),
                "q1": float(numeric.quantile(0.25)),
                "median": float(numeric.median()),
                "q3": float(numeric.quantile(0.75)),
                "max": float(numeric.max()),
            }
        )
    return pd.DataFrame(records)
