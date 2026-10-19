"""Drug safety signal explorer (FDA FAERS reports), built with Streamlit."""
import os
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

DATA = Path(os.environ.get("APP_DATA", "app_data"))

# Terms about products, dosing errors and patient experience, not clinical risks.
NOISE = [
    "PRODUCT", "DEVICE", "INCORRECT", "WRONG", "OFF LABEL", "INTENTIONAL",
    "ACCIDENTAL", "MEDICATION ERROR", "DOSE OMISSION", "DRUG INEFFECTIVE",
    "THERAPEUTIC RESPONSE", "DISCOURAGEMENT", "SENSITIVITY TO WEATHER",
    "CONDITION AGGRAVATED", "PRE-EXISTING CONDITION", "TREATMENT FAILURE",
]

st.set_page_config(page_title="Drug safety signals", layout="wide")


@st.cache_data
def load_parquet(name):
    return pd.read_parquet(DATA / name)


@st.cache_data
def load_csv(name):
    return pd.read_csv(DATA / name)


signals = load_parquet("signals.parquet")
validation = load_csv("validation.csv")
timeline = load_csv("backtest_timeline.csv")
summary = load_csv("backtest_summary.csv")
onset_stats = load_csv("onset.csv")
onset_events = load_parquet("onset_events.parquet")

st.title("Drug safety signal detection from FDA adverse event reports")
st.caption(
    "FDA FAERS reports, 2018 Q1 to 2026 Q2 · about 12 million unique cases · "
    "case study on JAK inhibitors (tofacitinib, upadacitinib, baricitinib)"
)
st.warning(
    "FAERS is voluntary, unverified reporting. A statistical signal is a lead for "
    "experts to investigate. It does not show that a drug causes a side effect."
)

tab1, tab2, tab3, tab4, tab5 = st.tabs(
    [
        "Signal explorer",
        "JAK inhibitor validation",
        "Quarter-by-quarter replay",
        "Time to onset",
        "Method and limitations",
    ]
)

with tab1:
    st.subheader("Which side effects are reported unusually often with a drug?")
    drug_counts = signals.groupby("ingredient")["n_drug"].max().sort_values(ascending=False)
    names = drug_counts.index.tolist()
    default = names.index("TOFACITINIB") if "TOFACITINIB" in names else 0

    c1, c2, c3 = st.columns([2, 1, 1])
    drug = c1.selectbox("Drug (as primary suspect)", names, index=default)
    min_cases = c2.slider("Minimum cases", 3, 200, 20)
    strict = c3.checkbox("Strict signals only", value=True)
    term = st.text_input("Only side effects containing (optional)", "")
    hide_noise = st.checkbox(
        "Hide product, administrative and patient-experience terms", value=True
    )

    d = signals[(signals["ingredient"] == drug) & (signals["cases"] >= min_cases)]
    if strict:
        d = d[d["flag_strict"]]
    if term:
        d = d[d["pt"].str.contains(term.upper(), regex=False)]
    if hide_noise:
        d = d[~d["pt"].str.contains("|".join(NOISE), regex=True)]
    d = d.sort_values("ic025", ascending=False)

    m1, m2 = st.columns(2)
    m1.metric("Reports with this drug as primary suspect", f"{int(drug_counts[drug]):,}")
    m2.metric("Signals shown", f"{len(d):,}")

    top = d.head(15).iloc[::-1]
    if len(top) > 0:
        fig = px.bar(
            top,
            x="ic025",
            y="pt",
            orientation="h",
            labels={"ic025": "Information component, lower bound (higher = stronger)", "pt": ""},
            hover_data=["cases", "prr", "ror"],
        )
        st.plotly_chart(fig)
    else:
        st.info("No signals match these filters.")

    st.dataframe(
        d.head(200)[["pt", "cases", "prr", "prr_lo", "ror", "ror_lo", "ic", "ic025"]],
        hide_index=True,
    )
    st.caption(
        "Terms that simply describe the disease being treated (for example myelofibrosis "
        "for ruxolitinib) show up as strong signals. This is confounding by indication, "
        "not a side effect. The validation tab handles this by comparing similar drugs."
    )

with tab2:
    st.subheader("Does the method rediscover the known JAK inhibitor risks?")
    st.write(
        "Each dot is the reporting odds ratio (ROR) for a labelled class risk. "
        "A dot to the right of the dashed line at 1, with its whole interval above 1, "
        "means the event is reported more often with that drug."
    )
    bg = st.radio(
        "Compare against",
        ["comparators", "all other drugs"],
        horizontal=True,
        format_func=lambda x: "Similar arthritis drugs" if x == "comparators" else "All other drugs",
    )
    v = validation[validation["background"] == bg].copy()
    v["err_plus"] = v["ci_high"] - v["ror"]
    v["err_minus"] = v["ror"] - v["ci_low"]
    fig = px.scatter(
        v,
        x="ror",
        y="risk_group",
        facet_row="drug",
        error_x="err_plus",
        error_x_minus="err_minus",
        log_x=True,
        height=700,
        labels={"ror": "Reporting odds ratio (log scale)", "risk_group": ""},
    )
    fig.add_vline(x=1, line_dash="dash")
    fig.update_traces(marker_size=9)
    fig.update_xaxes(
        tickvals=[0.5, 1, 2, 4, 8, 16], ticktext=["0.5", "1", "2", "4", "8", "16"]
    )
    fig.for_each_annotation(lambda a: a.update(text=a.text.split("=")[-1]))
    st.plotly_chart(fig)
    st.dataframe(
        v[["drug", "risk_group", "cases", "drug_cases", "ror", "ci_low", "ci_high", "signal"]],
        hide_index=True,
    )
    st.caption(
        "Risk groups are keyword-based groupings of MedDRA terms, not official MedDRA "
        "queries. The comparator set is adalimumab, etanercept, infliximab, golimumab, "
        "certolizumab, abatacept, tocilizumab and sarilumab. Rituximab was removed after the "
        "first run because it is mainly used for lymphoma and inflated the cancer background."
    )

with tab3:
    st.subheader("When would each signal first have been flagged?")
    st.write(
        "Using only reports known up to each quarter, compared with similar drugs. "
        "A signal is flagged when there are at least 3 cases and the lower bound of the "
        "95% interval is above 1."
    )
    c1, c2 = st.columns(2)
    drug3 = c1.selectbox("Drug", sorted(timeline["drug"].unique()), key="drug3")
    risk3 = c2.selectbox("Risk group", list(dict.fromkeys(timeline["risk_group"])), key="risk3")
    t = timeline[(timeline["drug"] == drug3) & (timeline["risk_group"] == risk3)]

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(x=t["quarter"], y=t["ci_high"], line=dict(width=0),
                   showlegend=False, hoverinfo="skip")
    )
    fig.add_trace(
        go.Scatter(x=t["quarter"], y=t["ci_low"], fill="tonexty", line=dict(width=0),
                   name="95% interval")
    )
    fig.add_trace(
        go.Scatter(x=t["quarter"], y=t["ror"], mode="lines+markers",
                   name="ROR vs similar drugs")
    )
    flagged = t[t["flag"]]
    fig.add_trace(
        go.Scatter(x=flagged["quarter"], y=flagged["ror"], mode="markers",
                   marker=dict(size=11, symbol="diamond"), name="Flagged")
    )
    fig.add_hline(y=1, line_dash="dash")
    fig.add_shape(
        type="line", x0="2021q3", x1="2021q3", y0=0, y1=1, yref="paper",
        line=dict(dash="dot"),
    )
    fig.add_annotation(
        x="2021q3", y=1, yref="paper", text="FDA boxed warning, Sep 2021",
        showarrow=False, yanchor="bottom",
    )
    fig.update_xaxes(type="category", title="Quarter")
    fig.update_yaxes(
        type="log",
        title="Reporting odds ratio (log scale)",
        range=[-0.3, 1.7],
        tickvals=[0.5, 1, 2, 5, 10, 20, 50],
        ticktext=["0.5", "1", "2", "5", "10", "20", "50"],
    )
    st.plotly_chart(fig)

    st.dataframe(summary[summary["drug"] == drug3], hide_index=True)
    st.caption(
        "Early quarters with very few cases are cut off the top of the chart. "
        "No correction is made for testing many pairs. "
        "Read this as a pattern, not as proof of early warning."
    )

with tab4:
    st.subheader("How long after starting a drug are events reported?")
    drug4 = st.selectbox("Drug", sorted(onset_events["drug"].unique()), key="drug4")
    e = onset_events[onset_events["drug"] == drug4]
    fig = px.box(
        e,
        x="onset_days",
        y="risk_group",
        points=False,
        labels={"onset_days": "Days from starting the drug to the event", "risk_group": ""},
    )
    fig.update_xaxes(range=[0, 1500])
    st.plotly_chart(fig)
    st.dataframe(onset_stats[onset_stats["drug"] == drug4], hide_index=True)
    st.caption(
        "Weibull shape below 1 means events are concentrated soon after starting the drug "
        "and thin out later. Only reports with both a therapy start date and an event date "
        "are included, and this describes time among reported events, not each patient's risk."
    )

with tab5:
    st.subheader("Method")
    st.markdown(
        """
- **Data:** FDA FAERS quarterly files, 2018 Q1 to 2026 Q2, loaded into DuckDB.
- **Cleaning:** latest version of each case kept, primary-suspect drug only, drug names
  normalized to the active ingredient, duplicate side-effect terms removed.
- **Signal statistics:** proportional reporting ratio (PRR), reporting odds ratio (ROR) and the
  information component (IC), each with confidence bounds. A strict flag needs at least 3 cases,
  PRR of 2 or more, chi-square of 4 or more, ROR lower bound above 1 and IC lower bound above 0.
- **Validation:** tofacitinib, upadacitinib and baricitinib against similar arthritis drugs for
  thrombosis, herpes zoster, serious infection, malignancy, heart attack or stroke and cholesterol.
- **Replay:** cumulative statistics by quarter, to see when each signal would first appear.
- **Onset:** days from therapy start to event, summarized with a Weibull fit.
        """
    )
    st.subheader("Limitations")
    st.markdown(
        """
- Reports are voluntary and unverified, and reporting is affected by publicity, lawsuits and
  patient-support programs.
- Disproportionality shows association in reports, not causation, and cannot give incidence.
- Confounding by indication: drugs are reported with the disease they treat.
- No correction for multiple testing. With millions of reports, tiny differences become
  statistically significant, so signals are ranked and reviewed, not accepted.
- The primary-suspect filter is a reporter's judgement. Cases with several suspect drugs are
  counted under each.
- Cases the FDA later deleted are not removed.
- Onset analysis uses only the minority of reports with full dates and has no censoring.
        """
    )
