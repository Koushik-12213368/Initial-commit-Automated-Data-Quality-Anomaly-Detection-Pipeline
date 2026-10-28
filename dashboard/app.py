"""
Data Quality Exception Dashboard (web UI).

Launch from project root:
    streamlit run dashboard/app.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.db.store import DatabaseStore
from src.pipeline import run_pipeline
from src.remediation.catalog import ERROR_CATALOG

st.set_page_config(
    page_title="Data Quality Dashboard",
    page_icon="▣",
    layout="wide",
    initial_sidebar_state="expanded",
)

DB_PATH = ROOT / "outputs" / "dq_pipeline.db"
DB_URL = f"sqlite:///{DB_PATH.as_posix()}"

SEVERITY_COLORS = {
    "CRITICAL": "#E11D48",
    "HIGH": "#EA580C",
    "MEDIUM": "#CA8A04",
    "LOW": "#059669",
}
SEVERITY_ORDER = ["CRITICAL", "HIGH", "MEDIUM", "LOW"]

CUSTOM_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500&display=swap');

html, body, [class*="css"] {
  font-family: 'DM Sans', sans-serif;
}
.stApp {
  background:
    radial-gradient(1200px 500px at 10% -10%, #dbeafe 0%, transparent 55%),
    radial-gradient(900px 400px at 100% 0%, #ecfccb 0%, transparent 50%),
    #f8fafc;
}
[data-testid="stSidebar"] {
  background: #0f172a;
  border-right: 1px solid #1e293b;
}
[data-testid="stSidebar"] * { color: #e2e8f0 !important; }
[data-testid="stSidebar"] .stCaption, [data-testid="stSidebar"] label {
  color: #94a3b8 !important;
}
[data-testid="stSidebar"] .stButton > button {
  background: #1d4ed8;
  color: #fff !important;
  border: none;
  font-weight: 600;
}
[data-testid="stSidebar"] .stButton > button:hover {
  background: #2563eb;
  color: #fff !important;
}
.hero {
  background: linear-gradient(135deg, #0f172a 0%, #1e3a5f 55%, #0f766e 100%);
  color: #f8fafc;
  padding: 1.4rem 1.6rem;
  border-radius: 16px;
  margin-bottom: 1.2rem;
  box-shadow: 0 12px 40px rgba(15, 23, 42, 0.18);
}
.hero h1 {
  margin: 0;
  font-size: 1.75rem;
  font-weight: 700;
  letter-spacing: -0.02em;
}
.hero p {
  margin: 0.35rem 0 0;
  opacity: 0.85;
  font-size: 0.98rem;
}
.kpi-card {
  background: #ffffff;
  border: 1px solid #e2e8f0;
  border-radius: 14px;
  padding: 1rem 1.1rem;
  box-shadow: 0 4px 16px rgba(15, 23, 42, 0.04);
  height: 100%;
}
.kpi-label {
  font-size: 0.78rem;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: #64748b;
  font-weight: 600;
  margin-bottom: 0.35rem;
}
.kpi-value {
  font-size: 1.7rem;
  font-weight: 700;
  color: #0f172a;
  font-family: 'IBM Plex Mono', monospace;
  line-height: 1.1;
}
.kpi-sub {
  margin-top: 0.3rem;
  font-size: 0.8rem;
  color: #64748b;
}
.badge {
  display: inline-block;
  padding: 0.15rem 0.55rem;
  border-radius: 999px;
  font-size: 0.75rem;
  font-weight: 700;
  letter-spacing: 0.04em;
}
.badge-pass { background: #d1fae5; color: #065f46; }
.badge-fail { background: #fee2e2; color: #991b1b; }
.section-title {
  font-size: 1.15rem;
  font-weight: 700;
  color: #0f172a;
  margin: 0.4rem 0 0.8rem;
}
.panel {
  background: #ffffff;
  border: 1px solid #e2e8f0;
  border-radius: 14px;
  padding: 1rem 1.1rem 0.4rem;
  margin-bottom: 1rem;
  box-shadow: 0 4px 16px rgba(15, 23, 42, 0.04);
}
div[data-testid="stTabs"] button[data-baseweb="tab"] {
  font-weight: 600;
}
</style>
"""


def inject_css() -> None:
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


@st.cache_resource
def get_store() -> DatabaseStore:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return DatabaseStore(db_url=DB_URL)


def load_runs(store: DatabaseStore) -> pd.DataFrame:
    return store.list_runs(limit=100)


def health_score(exceptions: pd.DataFrame, input_rows: int, recon_status: str) -> int:
    """0–100 score for the run (higher = healthier)."""
    if input_rows <= 0:
        return 0
    score = 100
    if recon_status != "PASS":
        score -= 25
    if exceptions.empty:
        return max(score, 0)
    weights = {"CRITICAL": 12, "HIGH": 6, "MEDIUM": 2, "LOW": 0.5}
    unique_bad = exceptions.loc[exceptions["row_index"] >= 0, "row_index"].nunique()
    penalty = min(40, unique_bad / input_rows * 100)
    for sev, w in weights.items():
        penalty += min(20, int((exceptions["severity"] == sev).sum()) * w * 0.15)
    return int(max(0, min(100, score - penalty)))


def render_hero(run_id: str | None, score: int | None, recon: str | None) -> None:
    status_html = ""
    if recon:
        cls = "badge-pass" if recon == "PASS" else "badge-fail"
        status_html = f'<span class="badge {cls}">{recon}</span>'
    score_txt = f" · Health score <strong>{score}</strong>/100" if score is not None else ""
    run_txt = f"Run <code>{run_id}</code>{score_txt} {status_html}" if run_id else "No run selected yet"
    st.markdown(
        f"""
        <div class="hero">
          <h1>Data Quality Dashboard</h1>
          <p>Screen daily transactional dumps before they hit management reports. {run_txt}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_kpis(run_meta: pd.Series, exceptions: pd.DataFrame, score: int) -> None:
    crit = int((exceptions["severity"] == "CRITICAL").sum()) if not exceptions.empty else 0
    high = int((exceptions["severity"] == "HIGH").sum()) if not exceptions.empty else 0
    flagged = (
        int(exceptions.loc[exceptions["row_index"] >= 0, "row_index"].nunique())
        if not exceptions.empty
        else 0
    )
    recon = run_meta["recon_status"]
    cards = [
        ("Input rows", f"{int(run_meta['input_row_count']):,}", "Records in daily dump"),
        ("Exceptions", f"{int(run_meta['exception_count']):,}", f"{flagged} unique rows flagged"),
        ("Critical", str(crit), "Must fix before publish"),
        ("High", str(high), "Quarantine / investigate"),
        ("Health score", f"{score}", "Composite DQ index"),
        ("Reconciliation", str(recon), "Volume vs expected band"),
    ]
    cols = st.columns(6)
    for col, (label, value, sub) in zip(cols, cards):
        col.markdown(
            f"""
            <div class="kpi-card">
              <div class="kpi-label">{label}</div>
              <div class="kpi-value">{value}</div>
              <div class="kpi-sub">{sub}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def chart_layout(fig: go.Figure) -> go.Figure:
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="DM Sans", color="#334155"),
        margin=dict(l=20, r=20, t=50, b=40),
        title_font=dict(size=15, color="#0f172a"),
    )
    return fig


def overview_charts(exceptions: pd.DataFrame) -> None:
    st.markdown('<div class="section-title">Overview</div>', unsafe_allow_html=True)
    if exceptions.empty:
        st.success("No exceptions for this run — dump looks clean.")
        return

    c1, c2, c3 = st.columns([1.1, 1.1, 1])

    by_sev = (
        exceptions["severity"]
        .value_counts()
        .reindex([s for s in SEVERITY_ORDER if s in exceptions["severity"].values])
        .reset_index()
    )
    by_sev.columns = ["severity", "count"]
    fig_sev = px.pie(
        by_sev,
        names="severity",
        values="count",
        color="severity",
        color_discrete_map=SEVERITY_COLORS,
        hole=0.55,
        title="Severity mix",
    )
    fig_sev.update_traces(textposition="inside", textinfo="percent+label")
    c1.plotly_chart(chart_layout(fig_sev), use_container_width=True)

    by_code = (
        exceptions.groupby("error_code")
        .size()
        .reset_index(name="count")
        .sort_values("count", ascending=True)
        .tail(12)
    )
    fig_code = px.bar(
        by_code,
        x="count",
        y="error_code",
        orientation="h",
        title="Top error codes",
        color_discrete_sequence=["#1d4ed8"],
    )
    c2.plotly_chart(chart_layout(fig_code), use_container_width=True)

    by_field = (
        exceptions.groupby("field")
        .size()
        .reset_index(name="count")
        .sort_values("count", ascending=False)
        .head(10)
    )
    fig_field = px.bar(
        by_field,
        x="field",
        y="count",
        title="Exceptions by field",
        color_discrete_sequence=["#0f766e"],
    )
    fig_field.update_layout(xaxis_tickangle=-30)
    c3.plotly_chart(chart_layout(fig_field), use_container_width=True)


def severity_field_heatmap(exceptions: pd.DataFrame) -> None:
    if exceptions.empty:
        return
    pivot = (
        exceptions.groupby(["field", "severity"])
        .size()
        .unstack(fill_value=0)
        .reindex(columns=[c for c in SEVERITY_ORDER if c in exceptions["severity"].unique()], fill_value=0)
    )
    if pivot.empty:
        return
    fig = px.imshow(
        pivot,
        text_auto=True,
        aspect="auto",
        color_continuous_scale="YlOrRd",
        title="Field × severity heatmap",
    )
    st.plotly_chart(chart_layout(fig), use_container_width=True)


def drilldown_table(exceptions: pd.DataFrame) -> None:
    st.markdown('<div class="section-title">Exception drill-down</div>', unsafe_allow_html=True)
    if exceptions.empty:
        st.info("Nothing to drill into for this run.")
        return

    f1, f2, f3, f4 = st.columns([1, 1.2, 1, 1.4])
    severities = ["All"] + [s for s in SEVERITY_ORDER if s in exceptions["severity"].values]
    codes = ["All"] + sorted(exceptions["error_code"].dropna().unique().tolist())
    fields = ["All"] + sorted(exceptions["field"].dropna().unique().tolist())
    sev = f1.selectbox("Severity", severities)
    code = f2.selectbox("Error code", codes)
    field = f3.selectbox("Field", fields)
    search = f4.text_input("Search message / value", placeholder="e.g. score_pct, TXN-1001")

    view = exceptions.copy()
    if sev != "All":
        view = view[view["severity"] == sev]
    if code != "All":
        view = view[view["error_code"] == code]
    if field != "All":
        view = view[view["field"] == field]
    if search.strip():
        q = search.strip().lower()
        mask = (
            view["message"].astype(str).str.lower().str.contains(q, na=False)
            | view["raw_value"].astype(str).str.lower().str.contains(q, na=False)
            | view["error_code"].astype(str).str.lower().str.contains(q, na=False)
        )
        view = view[mask]

    st.caption(f"Showing {len(view):,} of {len(exceptions):,} exceptions")

    display_cols = [
        "row_index",
        "error_code",
        "severity",
        "field",
        "raw_value",
        "message",
        "remediation",
    ]
    st.dataframe(
        view[display_cols],
        use_container_width=True,
        hide_index=True,
        height=440,
        column_config={
            "row_index": st.column_config.NumberColumn("Row", width="small"),
            "error_code": st.column_config.TextColumn("Error code", width="medium"),
            "severity": st.column_config.TextColumn("Severity", width="small"),
            "field": st.column_config.TextColumn("Field", width="medium"),
            "raw_value": st.column_config.TextColumn("Value", width="small"),
            "message": st.column_config.TextColumn("Message", width="large"),
            "remediation": st.column_config.TextColumn("Recommended fix", width="large"),
        },
    )

    d1, d2 = st.columns(2)
    d1.download_button(
        "Download filtered CSV",
        data=view.to_csv(index=False).encode("utf-8"),
        file_name="filtered_exceptions.csv",
        mime="text/csv",
        use_container_width=True,
    )
    if not view.empty and "error_code" in view.columns:
        top = view.iloc[0]
        d2.info(f"**{top['error_code']}** — {top.get('description', top.get('message', ''))}")


def run_history(runs: pd.DataFrame) -> None:
    st.markdown('<div class="section-title">Run history</div>', unsafe_allow_html=True)
    if runs.empty:
        st.info("No historical runs yet.")
        return
    hist = runs.copy()
    hist["started_at"] = pd.to_datetime(hist["started_at"], errors="coerce")
    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=hist["started_at"],
            y=hist["exception_count"],
            name="Exceptions",
            marker_color="#1d4ed8",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=hist["started_at"],
            y=hist["input_row_count"],
            name="Input rows",
            mode="lines+markers",
            yaxis="y2",
            line=dict(color="#0f766e", width=2),
        )
    )
    fig.update_layout(
        yaxis=dict(title="Exceptions"),
        yaxis2=dict(title="Input rows", overlaying="y", side="right"),
        legend=dict(orientation="h", y=1.12),
        title="Exceptions vs volume over runs",
    )
    st.plotly_chart(chart_layout(fig), use_container_width=True)
    st.dataframe(
        hist[
            [
                "run_id",
                "source_file",
                "started_at",
                "input_row_count",
                "exception_count",
                "recon_status",
            ]
        ],
        use_container_width=True,
        hide_index=True,
        height=280,
    )


def remediation_catalog() -> None:
    st.markdown('<div class="section-title">Remediation playbook</div>', unsafe_allow_html=True)
    rows = [
        {
            "error_code": code,
            "severity": meta["severity"],
            "description": meta["description"],
            "remediation": meta["remediation"],
        }
        for code, meta in ERROR_CATALOG.items()
    ]
    catalog = pd.DataFrame(rows)
    catalog["_ord"] = catalog["severity"].map({s: i for i, s in enumerate(SEVERITY_ORDER)})
    catalog = catalog.sort_values(["_ord", "error_code"]).drop(columns=["_ord"])
    st.dataframe(catalog, use_container_width=True, hide_index=True, height=480)


def sidebar(store: DatabaseStore) -> tuple[str | None, pd.DataFrame]:
    st.sidebar.markdown("### Controls")
    st.sidebar.caption("Validate dumps · pick a run · drill into exceptions")

    if st.sidebar.button("▶ Run on sample data", use_container_width=True, type="primary"):
        with st.spinner("Running validation pipeline..."):
            result = run_pipeline(
                input_path=ROOT / "data" / "sample_daily_activity.csv",
                config_path=ROOT / "config" / "rules.yaml",
                expected_path=ROOT / "data" / "expected_counts.json",
                output_dir=ROOT / "outputs",
                db_url=DB_URL,
            )
        st.sidebar.success(f"Done — {result['exception_count']} exceptions")
        st.rerun()

    uploaded = st.sidebar.file_uploader("Upload daily CSV dump", type=["csv"])
    if uploaded is not None:
        if st.sidebar.button("Validate upload", use_container_width=True):
            tmp = ROOT / "outputs" / "_upload.csv"
            tmp.parent.mkdir(parents=True, exist_ok=True)
            tmp.write_bytes(uploaded.getvalue())
            with st.spinner("Validating uploaded file..."):
                result = run_pipeline(
                    input_path=tmp,
                    config_path=ROOT / "config" / "rules.yaml",
                    expected_path=ROOT / "data" / "expected_counts.json",
                    output_dir=ROOT / "outputs",
                    db_url=DB_URL,
                )
            st.sidebar.success(f"Done — {result['exception_count']} exceptions")
            st.rerun()

    st.sidebar.divider()
    runs = load_runs(store)
    if runs.empty:
        st.sidebar.warning("No runs yet. Click the button above.")
        return None, runs

    labels = [
        f"{r.run_id[:17]}… | rows={r.input_row_count} | exc={r.exception_count} | {r.recon_status}"
        for r in runs.itertuples()
    ]
    choice = st.sidebar.selectbox(
        "Select run",
        options=list(range(len(labels))),
        format_func=lambda i: labels[i],
    )
    st.sidebar.caption(f"Database: `{DB_PATH.name}`")
    return runs.iloc[choice]["run_id"], runs


def main() -> None:
    inject_css()
    store = get_store()
    run_id, runs = sidebar(store)

    if run_id is None:
        render_hero(None, None, None)
        st.info("Use the sidebar to run the sample pipeline or upload a CSV.")
        remediation_catalog()
        return

    run_meta = runs[runs["run_id"] == run_id].iloc[0]
    exceptions = store.load_exceptions(run_id)
    score = health_score(
        exceptions,
        int(run_meta["input_row_count"]),
        str(run_meta["recon_status"]),
    )

    render_hero(run_id, score, str(run_meta["recon_status"]))
    render_kpis(run_meta, exceptions, score)
    st.write("")

    tab_overview, tab_exceptions, tab_history, tab_playbook = st.tabs(
        ["Overview", "Exceptions", "Run history", "Playbook"]
    )

    with tab_overview:
        overview_charts(exceptions)
        severity_field_heatmap(exceptions)
        with st.expander("Run metadata"):
            st.json(
                {
                    "run_id": run_id,
                    "source_file": run_meta.get("source_file"),
                    "started_at": str(run_meta.get("started_at")),
                    "finished_at": str(run_meta.get("finished_at")),
                    "input_row_count": int(run_meta["input_row_count"]),
                    "exception_count": int(run_meta["exception_count"]),
                    "recon_status": run_meta["recon_status"],
                    "health_score": score,
                }
            )

    with tab_exceptions:
        drilldown_table(exceptions)

    with tab_history:
        run_history(runs)

    with tab_playbook:
        remediation_catalog()


if __name__ == "__main__":
    main()
