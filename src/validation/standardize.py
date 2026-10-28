"""Field standardization: ISO-8601 dates, category maps, trimmed IDs."""

from __future__ import annotations

from typing import Any

import pandas as pd


def _empty_exception() -> dict[str, Any]:
    return {
        "row_index": [],
        "error_code": [],
        "field": [],
        "raw_value": [],
        "message": [],
    }


def _parse_datetimes(series: pd.Series) -> pd.Series:
    """Parse mixed date/datetime strings robustly; leave unparseable as NaT."""
    try:
        parsed = pd.to_datetime(series, errors="coerce", utc=False, format="mixed")
    except TypeError:
        parsed = pd.to_datetime(series, errors="coerce", utc=False)

    still_bad = series.notna() & (series.astype(str).str.strip() != "") & parsed.isna()
    if still_bad.any():
        retry = pd.to_datetime(series[still_bad], errors="coerce", utc=False, dayfirst=True)
        parsed = parsed.copy()
        parsed.loc[still_bad] = retry
    return parsed


def standardize_dataframe(
    df: pd.DataFrame,
    config: dict[str, Any],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Apply standardization rules and return (cleaned_df, exceptions_df).

    Exceptions capture parse failures and unknown categories; whitespace
    trims are logged as LOW severity but values are corrected in place.
    """
    out = df.copy()
    out["_row_id"] = range(len(out))
    exc = _empty_exception()

    ds = config.get("dataset", {})
    std = config.get("standardization", {})
    date_fmt = std.get("date_format_out", "%Y-%m-%d")
    datetime_fmt = std.get("datetime_format_out", "%Y-%m-%dT%H:%M:%S")
    category_maps: dict[str, dict[str, str]] = std.get("category_maps", {})

    # --- Trim string identifiers ---
    for col in ds.get("id_fields", []):
        if col not in out.columns:
            continue
        series = out[col].astype("string")
        trimmed = series.str.strip()
        dirty = series.notna() & (series != trimmed) & (series.str.len() > 0)
        for idx in out.loc[dirty, "_row_id"]:
            raw = series.loc[out["_row_id"] == idx].iloc[0]
            exc["row_index"].append(int(idx))
            exc["error_code"].append("STD_ID_WHITESPACE")
            exc["field"].append(col)
            exc["raw_value"].append(repr(raw))
            exc["message"].append(f"Trimmed whitespace on identifier '{col}'.")
        out[col] = trimmed

    # --- Dates → ISO-8601 ---
    for col in ds.get("date_fields", []):
        if col not in out.columns:
            continue
        original = out[col]
        parsed = _parse_datetimes(original)
        failed = original.notna() & (original.astype(str).str.strip() != "") & parsed.isna()
        for idx in out.loc[failed, "_row_id"]:
            raw = original.loc[out["_row_id"] == idx].iloc[0]
            exc["row_index"].append(int(idx))
            exc["error_code"].append("STD_DATE_PARSE")
            exc["field"].append(col)
            exc["raw_value"].append(str(raw))
            exc["message"].append(f"Could not parse date in '{col}' to ISO-8601.")

        # Prefer date-only format when column name suggests a date (not datetime)
        if col.endswith("_at") or "time" in col.lower():
            out[col] = parsed.dt.strftime(datetime_fmt)
        else:
            out[col] = parsed.dt.strftime(date_fmt)
        out.loc[parsed.isna(), col] = pd.NA

    # --- Category uppercase mappings ---
    for col in ds.get("category_fields", []):
        if col not in out.columns:
            continue
        mapping = {str(k).strip().lower(): v for k, v in category_maps.get(col, {}).items()}
        raw_series = out[col].astype("string").str.strip()
        lower = raw_series.str.lower()
        mapped = lower.map(mapping)

        # Values already equal to a canonical target (case-insensitive) are OK
        canonical = {v.upper(): v for v in mapping.values()}
        already_ok = lower.map(lambda x: canonical.get(str(x).upper()) if pd.notna(x) else pd.NA)

        final = mapped.fillna(already_ok)
        unknown = raw_series.notna() & (raw_series != "") & final.isna()
        for idx in out.loc[unknown, "_row_id"]:
            raw = raw_series.loc[out["_row_id"] == idx].iloc[0]
            exc["row_index"].append(int(idx))
            exc["error_code"].append("STD_CATEGORY_UNKNOWN")
            exc["field"].append(col)
            exc["raw_value"].append(str(raw))
            exc["message"].append(f"Unknown category '{raw}' in '{col}'.")

        # Fallback: uppercase unknown values so reports stay consistent
        out[col] = final.fillna(raw_series.str.upper())

    exceptions = pd.DataFrame(exc)
    return out, exceptions
