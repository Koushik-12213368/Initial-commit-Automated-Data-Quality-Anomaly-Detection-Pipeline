"""Error codes and recommended remediation steps for operational teams."""

from __future__ import annotations

from typing import Any

ERROR_CATALOG: dict[str, dict[str, Any]] = {
    "STD_DATE_PARSE": {
        "description": "Date / datetime value could not be parsed to ISO-8601.",
        "severity": "HIGH",
        "remediation": (
            "Confirm source system date format. Re-export with ISO-8601 "
            "(YYYY-MM-DD) or provide the correct format string in rules.yaml."
        ),
    },
    "STD_CATEGORY_UNKNOWN": {
        "description": "Category value not in the allowed mapping dictionary.",
        "severity": "MEDIUM",
        "remediation": (
            "Map the raw value in config/rules.yaml under standardization.category_maps, "
            "or correct the upstream feed to use a known category."
        ),
    },
    "STD_ID_WHITESPACE": {
        "description": "Identifier had leading/trailing whitespace (auto-trimmed).",
        "severity": "LOW",
        "remediation": (
            "Inform source system owners to trim identifiers at extract time. "
            "Record was auto-corrected; re-validate after upstream fix."
        ),
    },
    "MISS_KEY_FIELD": {
        "description": "Required key field is null or empty.",
        "severity": "CRITICAL",
        "remediation": (
            "Reject or quarantine the row. Request a re-extract from the source "
            "system with the missing key populated (transaction_id / user_id / activity_date)."
        ),
    },
    "RANGE_BELOW_MIN": {
        "description": "Numeric value is below the configured minimum.",
        "severity": "HIGH",
        "remediation": (
            "Verify unit of measure and sign conventions. Correct negative tenure/hours "
            "or out-of-bound scores at source, then re-run the pipeline."
        ),
    },
    "RANGE_ABOVE_MAX": {
        "description": "Numeric value exceeds the configured maximum.",
        "severity": "HIGH",
        "remediation": (
            "Check for unit mismatches (e.g., seconds vs minutes) or data-entry errors. "
            "Adjust rules.yaml only if the business limit has intentionally changed."
        ),
    },
    "ANOMALY_ZSCORE": {
        "description": "Metric is a statistical outlier by Z-score.",
        "severity": "MEDIUM",
        "remediation": (
            "Investigate the user/session for bot activity, clock skew, or bulk imports. "
            "Confirm with ops before excluding from management reports."
        ),
    },
    "ANOMALY_IQR": {
        "description": "Metric is outside the IQR fence (Q1 − k·IQR / Q3 + k·IQR).",
        "severity": "MEDIUM",
        "remediation": (
            "Review distribution shift vs prior days. If legitimate (campaign spike), "
            "document and whitelist; otherwise escalate to data owners."
        ),
    },
    "RECON_COUNT_LOW": {
        "description": "Record count is below the expected daily minimum.",
        "severity": "CRITICAL",
        "remediation": (
            "Check extract job completion, file truncation, and filter predicates. "
            "Do not publish management reports until volume is reconciled."
        ),
    },
    "RECON_COUNT_HIGH": {
        "description": "Record count exceeds the expected daily maximum.",
        "severity": "HIGH",
        "remediation": (
            "Look for duplicate loads, overlapping date windows, or unintended joins. "
            "Compare against prior-day file and source row counts."
        ),
    },
    "RECON_DOD_VARIANCE": {
        "description": "Day-over-day record count variance exceeds tolerance.",
        "severity": "HIGH",
        "remediation": (
            "Compare extract parameters with yesterday. Validate holiday/weekend "
            "effects and confirm no partial reloads were appended."
        ),
    },
    "DUP_TRANSACTION_ID": {
        "description": "Duplicate transaction_id detected in the dump.",
        "severity": "HIGH",
        "remediation": (
            "Keep the latest record by created_at (or business rule), quarantine "
            "duplicates, and fix upstream uniqueness constraints."
        ),
    },
}


def get_remediation(error_code: str) -> dict[str, Any]:
    """Return catalog entry for an error code, with a safe default."""
    return ERROR_CATALOG.get(
        error_code,
        {
            "description": "Unclassified data quality issue.",
            "severity": "MEDIUM",
            "remediation": "Review the flagged field and escalate to the data steward.",
        },
    )
