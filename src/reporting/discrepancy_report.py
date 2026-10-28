"""Automated discrepancy / exception reporting (Excel + CSV)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from src.remediation.catalog import get_remediation
from src.validation.anomaly import metric_summary


def enrich_exceptions(exceptions: pd.DataFrame) -> pd.DataFrame:
    """Attach severity, description, and remediation from the error catalog."""
    if exceptions.empty:
        return pd.DataFrame(
            columns=[
                "row_index",
                "error_code",
                "field",
                "raw_value",
                "message",
                "severity",
                "description",
                "remediation",
            ]
        )

    out = exceptions.copy()
    severities, descriptions, remediations = [], [], []
    for code in out["error_code"]:
        entry = get_remediation(str(code))
        severities.append(entry["severity"])
        descriptions.append(entry["description"])
        remediations.append(entry["remediation"])
    out["severity"] = severities
    out["description"] = descriptions
    out["remediation"] = remediations

    severity_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
    out["_sev"] = out["severity"].map(lambda s: severity_order.get(s, 9))
    out = out.sort_values(["_sev", "error_code", "row_index"]).drop(columns=["_sev"])
    return out.reset_index(drop=True)


def _summary_by_code(exceptions: pd.DataFrame) -> pd.DataFrame:
    if exceptions.empty:
        return pd.DataFrame(
            columns=["error_code", "severity", "count", "description", "remediation"]
        )
    grouped = (
        exceptions.groupby(["error_code", "severity", "description", "remediation"], dropna=False)
        .size()
        .reset_index(name="count")
        .sort_values("count", ascending=False)
    )
    return grouped[["error_code", "severity", "count", "description", "remediation"]]


def write_reports(
    cleaned: pd.DataFrame,
    exceptions: pd.DataFrame,
    recon_summary: dict[str, Any],
    config: dict[str, Any],
    run_id: str,
    output_dir: str | Path | None = None,
) -> dict[str, Path]:
    """
    Write Excel summary, exceptions CSV, and clean records CSV.

    Returns a dict of artifact name → path.
    """
    reporting = config.get("reporting", {})
    out_dir = Path(output_dir or reporting.get("output_dir", "outputs"))
    out_dir.mkdir(parents=True, exist_ok=True)

    excel_name = reporting.get("excel_summary", "discrepancy_summary.xlsx")
    exc_name = reporting.get("exception_csv", "exceptions.csv")
    clean_name = reporting.get("clean_csv", "clean_records.csv")

    excel_path = out_dir / f"{run_id}_{excel_name}"
    exc_path = out_dir / f"{run_id}_{exc_name}"
    clean_path = out_dir / f"{run_id}_{clean_name}"

    enriched = enrich_exceptions(exceptions)
    by_code = _summary_by_code(enriched)
    metrics = config.get("dataset", {}).get("anomaly_metrics", [])
    stats = metric_summary(cleaned, metrics)

    overview = pd.DataFrame(
        [
            {"metric": "run_id", "value": run_id},
            {"metric": "input_row_count", "value": recon_summary.get("current_count")},
            {
                "metric": "expected_count_min",
                "value": recon_summary.get("expected_count_min"),
            },
            {
                "metric": "expected_count_max",
                "value": recon_summary.get("expected_count_max"),
            },
            {"metric": "prior_count", "value": recon_summary.get("prior_count")},
            {
                "metric": "dod_variance_pct",
                "value": recon_summary.get("dod_variance_pct"),
            },
            {"metric": "reconciliation_status", "value": recon_summary.get("status")},
            {"metric": "total_exceptions", "value": len(enriched)},
            {
                "metric": "critical_exceptions",
                "value": int((enriched["severity"] == "CRITICAL").sum())
                if not enriched.empty
                else 0,
            },
            {
                "metric": "high_exceptions",
                "value": int((enriched["severity"] == "HIGH").sum())
                if not enriched.empty
                else 0,
            },
            {
                "metric": "unique_rows_flagged",
                "value": int(enriched.loc[enriched["row_index"] >= 0, "row_index"].nunique())
                if not enriched.empty
                else 0,
            },
        ]
    )

    # Rows clean enough for downstream (no CRITICAL / HIGH on that row)
    if enriched.empty:
        publishable = cleaned.copy()
    else:
        bad_rows = set(
            enriched.loc[
                (enriched["severity"].isin(["CRITICAL", "HIGH"]))
                & (enriched["row_index"] >= 0),
                "row_index",
            ]
        )
        if "_row_id" in cleaned.columns:
            publishable = cleaned[~cleaned["_row_id"].isin(bad_rows)].copy()
        else:
            publishable = cleaned[~cleaned.index.isin(bad_rows)].copy()

    drop_cols = [c for c in ["_row_id"] if c in publishable.columns]
    publishable = publishable.drop(columns=drop_cols)

    with pd.ExcelWriter(excel_path, engine="openpyxl") as writer:
        overview.to_excel(writer, sheet_name="Overview", index=False)
        by_code.to_excel(writer, sheet_name="By_Error_Code", index=False)
        enriched.to_excel(writer, sheet_name="All_Exceptions", index=False)
        stats.to_excel(writer, sheet_name="Metric_Stats", index=False)
        recon_df = pd.DataFrame([recon_summary])
        recon_df.to_excel(writer, sheet_name="Reconciliation", index=False)

    enriched.to_csv(exc_path, index=False)
    publishable.to_csv(clean_path, index=False)

    return {
        "excel_summary": excel_path,
        "exceptions_csv": exc_path,
        "clean_csv": clean_path,
    }
