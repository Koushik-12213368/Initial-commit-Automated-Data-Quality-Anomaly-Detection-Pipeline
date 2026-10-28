"""Orchestrate load → validate → reconcile → report → persist."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from src.db.store import DatabaseStore
from src.reporting.discrepancy_report import enrich_exceptions, write_reports
from src.validation.anomaly import run_anomaly_detection
from src.validation.missing_fields import check_duplicate_ids, check_missing_keys
from src.validation.range_checks import run_range_checks
from src.validation.reconcile import reconcile_counts
from src.validation.standardize import standardize_dataframe


def load_config(config_path: str | Path) -> dict[str, Any]:
    path = Path(config_path)
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def load_input(path: str | Path) -> pd.DataFrame:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Input file not found: {path}")
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(path, dtype=str, keep_default_na=True)
    if suffix in {".xlsx", ".xls"}:
        return pd.read_excel(path, dtype=str)
    raise ValueError(f"Unsupported input format: {suffix}")


def run_pipeline(
    input_path: str | Path,
    config_path: str | Path = "config/rules.yaml",
    expected_path: str | Path | None = "data/expected_counts.json",
    prior_count: int | None = None,
    output_dir: str | Path | None = None,
    db_url: str = "sqlite:///outputs/dq_pipeline.db",
    run_id: str | None = None,
) -> dict[str, Any]:
    """
    Execute the full data-quality pipeline.

    Returns a result dict with run metadata, paths, and exception counts.
    """
    started = datetime.now(timezone.utc)
    run_id = run_id or started.strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:8]
    config = load_config(config_path)
    raw = load_input(input_path)
    input_count = len(raw)

    cleaned, std_exc = standardize_dataframe(raw, config)
    missing_exc = check_missing_keys(cleaned, config)
    dup_exc = check_duplicate_ids(cleaned, id_column="transaction_id")
    range_exc = run_range_checks(cleaned, config)
    anomaly_exc = run_anomaly_detection(cleaned, config)
    recon_exc, recon_summary = reconcile_counts(
        current_count=input_count,
        config=config,
        expected_path=expected_path,
        prior_count=prior_count,
    )

    exceptions = pd.concat(
        [std_exc, missing_exc, dup_exc, range_exc, anomaly_exc, recon_exc],
        ignore_index=True,
    )
    enriched = enrich_exceptions(exceptions)

    artifacts = write_reports(
        cleaned=cleaned,
        exceptions=enriched,
        recon_summary=recon_summary,
        config=config,
        run_id=run_id,
        output_dir=output_dir,
    )

    finished = datetime.now(timezone.utc)
    store = DatabaseStore(db_url=db_url)
    store.save_run(
        run_id=run_id,
        source_file=str(input_path),
        started_at=started,
        finished_at=finished,
        input_row_count=input_count,
        exception_count=len(enriched),
        recon_summary=recon_summary,
        artifacts=artifacts,
        exceptions=enriched,
    )

    return {
        "run_id": run_id,
        "input_path": str(input_path),
        "input_row_count": input_count,
        "exception_count": len(enriched),
        "recon_summary": recon_summary,
        "artifacts": {k: str(v) for k, v in artifacts.items()},
        "exceptions": enriched,
        "cleaned": cleaned,
        "started_at": started.isoformat(),
        "finished_at": finished.isoformat(),
        "db_url": db_url,
    }
