"""
module_roi.py
Redistribution ROI Calculator
A standalone mini-tool for supply chain managers to instantly evaluate
whether a transfer is worth actioning vs writing off.
"""

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go


def _euro(x):
    return f"€{x:,.0f}"


def compute_roi(units, unit_value, logistics_cost, monthly_usage_at_dest,
                days_to_expiry, write_off_pct=1.0, commercial_cost=0):
    """
    Core ROI calculation. Returns a dict of all financial metrics.
    """
    gross_value         = units * unit_value
    net_value_saved     = gross_value - logistics_cost - commercial_cost
    write_off_if_nothing = gross_value * write_off_pct

    # break-even: how many units need to be consumed to cover logistics
    if unit_value > 0:
        breakeven_units = (logistics_cost + commercial_cost) / unit_value
    else:
        breakeven_units = 0

    # payback days: how many days until transferred units cover the cost
    if monthly_usage_at_dest > 0:
        payback_days = (breakeven_units / monthly_usage_at_dest) * 30
    else:
        payback_days = float("inf")

    roi_pct = (net_value_saved / (logistics_cost + commercial_cost + 1)) * 100 if (logistics_cost + commercial_cost) > 0 else float("inf")

    viable = (
        net_value_saved > 0
        and payback_days < days_to_expiry
        and net_value_saved > write_off_if_nothing * 0.1  # at least 10% better than doing nothing
    )

    verdict = "✅ Action Recommended" if viable and net_value_saved > 0 else (
        "⚠️ Review Required" if net_value_saved > 0 else "❌ Write-Off Likely Cheaper"
    )

    return {
        "Gross Value of Stock": gross_value,
        "Logistics Cost": logistics_cost,
        "Commercial Cost": commercial_cost,
        "Net Value Saved": net_value_saved,
        "Write-Off if No Action": write_off_if_nothing,
        "Break-Even Units": round(breakeven_units, 1),
        "Payback Days": round(payback_days, 1) if payback_days != float("inf") else None,
        "ROI %": round(roi_pct, 1) if roi_pct != float("inf") else None,
        "Verdict": verdict,
        "Viable": viable,
    }


def render_roi_page(df, rec_df):
    import streamlit as st

    st.markdown('<div class="section-title">Redistribution ROI Calculator</div>', unsafe_allow_html=True)
    st.markdown(
        '<p class="small-muted">Instantly evaluate whether a transfer is worth actioning. Enter parameters manually or load from a system recommendation.</p>',
        unsafe_allow_html=True,
    )

    # ---- Quick-load from recommendations ----
    if not rec_df.empty:
        st.markdown("### Quick Load from Recommendation")
        st.markdown(
            """
<div class="info-box">
    <h4>Load from an existing recommendation</h4>
    <p>Select any system recommendation to auto-fill the calculator. You can then adjust inputs to test assumptions.</p>
</div>
""",
            unsafe_allow_html=True,
        )

        rec_options = ["— Enter manually —"] + [
            f"{r['From']} → {r['To']} | {r['Product']} | Batch {r['Batch']}"
            for _, r in rec_df.iterrows()
        ]
        selected_rec = st.selectbox("Load a recommendation", rec_options, key="roi_rec_selector")

        preload = None
        if selected_rec != "— Enter manually —":
            idx = rec_options.index(selected_rec) - 1
            preload = rec_df.iloc[idx]
    else:
        preload = None

    st.markdown("### Calculator Inputs")

    c1, c2 = st.columns(2)

    with c1:
        st.markdown("**Transfer Details**")

        all_locations = sorted(df["Location"].unique().tolist())

        from_loc_default = preload["From"] if preload is not None else all_locations[0]
        to_loc_default   = preload["To"]   if preload is not None else (all_locations[1] if len(all_locations) > 1 else all_locations[0])

        from_loc = st.selectbox("From Location", all_locations,
                                index=all_locations.index(from_loc_default) if from_loc_default in all_locations else 0,
                                key="roi_from_loc")
        to_loc   = st.selectbox("To Location",   all_locations,
                                index=all_locations.index(to_loc_default) if to_loc_default in all_locations else 0,
                                key="roi_to_loc")

        units_default = int(preload["Qty"]) if preload is not None else 50
        unit_val_default = int(preload["Gross Value Saved"] / preload["Qty"]) if preload is not None else 3000

        units     = st.number_input("Units to Transfer", min_value=1, max_value=10000, value=units_default, step=1, key="roi_units")
        unit_val  = st.number_input("Unit Value (€)", min_value=1, max_value=100000, value=unit_val_default, step=100, key="roi_unit_val")

    with c2:
        st.markdown("**Cost & Demand Assumptions**")

        logistics_default = int(preload["Logistics Cost"]) if preload is not None else 6800
        logistics_cost = st.number_input("Logistics Cost (€)", min_value=0, max_value=100000, value=logistics_default, step=200, key="roi_logistics")

        commercial_cost = st.number_input("Commercial / Admin Cost (€)", min_value=0, max_value=50000, value=0, step=100, key="roi_commercial")

        # try to auto-fill monthly usage at destination
        dest_row = df[df["Location"] == to_loc]
        dest_usage_default = int(dest_row["Monthly Usage"].values[0]) if not dest_row.empty else 20
        monthly_usage = st.number_input("Monthly Usage at Destination", min_value=0, max_value=1000, value=dest_usage_default, step=1, key="roi_monthly_usage")

        # days to expiry auto-fill from source
        src_row = df[df["Location"] == from_loc]
        dte_default = int(src_row["Days to Expiry"].values[0]) if not src_row.empty else 90
        days_to_expiry = st.number_input("Days to Expiry", min_value=1, max_value=1000, value=dte_default, step=1, key="roi_dte")

        write_off_pct = st.slider("Write-off % if no action", min_value=10, max_value=100, value=80, step=5, key="roi_writeoff") / 100

    # ---- Compute ----
    result = compute_roi(
        units=units,
        unit_value=unit_val,
        logistics_cost=logistics_cost,
        monthly_usage_at_dest=monthly_usage,
        days_to_expiry=days_to_expiry,
        write_off_pct=write_off_pct,
        commercial_cost=commercial_cost,
    )

    st.markdown("---")
    st.markdown("### Result")

    verdict_color = {"✅ Action Recommended": "#dcfce7", "⚠️ Review Required": "#ffedd5", "❌ Write-Off Likely Cheaper": "#fee2e2"}.get(result["Verdict"], "#f1f5f9")
    verdict_text_color = {"✅ Action Recommended": "#166534", "⚠️ Review Required": "#92400e", "❌ Write-Off Likely Cheaper": "#991b1b"}.get(result["Verdict"], "#111827")

    st.markdown(
        f"""
<div style="background:{verdict_color};border-radius:16px;padding:18px 24px;margin-bottom:18px;">
    <span style="font-size:20px;font-weight:900;color:{verdict_text_color}">{result['Verdict']}</span>
    <span style="font-size:13px;color:{verdict_text_color};margin-left:16px;">
        Transfer {units} units from <b>{from_loc}</b> to <b>{to_loc}</b>
    </span>
</div>
""",
        unsafe_allow_html=True,
    )

    c1, c2, c3, c4 = st.columns(4)

    def kpi_mini(col, label, value, sub=""):
        col.markdown(
            f"""
<div class="kpi">
    <div class="kpi-label">{label}</div>
    <div class="kpi-value">{value}</div>
    <div class="kpi-sub">{sub}</div>
</div>
""",
            unsafe_allow_html=True,
        )

    kpi_mini(c1, "Net Value Saved", _euro(result["Net Value Saved"]), "After all costs")
    kpi_mini(c2, "Write-Off if No Action", _euro(result["Write-Off if No Action"]), f"At {int(write_off_pct*100)}% write-off rate")
    kpi_mini(c3, "Break-Even Units", str(result["Break-Even Units"]), "Units needed to cover costs")
    payback_display = f"{result['Payback Days']} days" if result["Payback Days"] is not None else "N/A (no demand)"
    roi_display = f"{result['ROI %']}%" if result["ROI %"] is not None else "∞"
    kpi_mini(c4, "Payback Period", payback_display, f"ROI: {roi_display}")

    # ---- Waterfall chart ----
    st.markdown("### Financial Breakdown")

    waterfall_x = ["Gross Stock Value", "Logistics Cost", "Commercial Cost", "Net Value Saved"]
    waterfall_y = [
        result["Gross Value of Stock"],
        -result["Logistics Cost"],
        -result["Commercial Cost"],
        result["Net Value Saved"],
    ]
    bar_colors = ["#1f6fb2", "#d92d20", "#f79009", "#12b76a" if result["Net Value Saved"] > 0 else "#d92d20"]

    fig = go.Figure(go.Bar(
        x=waterfall_x,
        y=waterfall_y,
        marker_color=bar_colors,
        text=[_euro(abs(v)) for v in waterfall_y],
        textposition="outside",
    ))
    fig.update_layout(
        height=360,
        paper_bgcolor="#ffffff",
        plot_bgcolor="#ffffff",
        font_color="#111827",
        yaxis_title="Value (€)",
        xaxis_title="",
        yaxis_tickprefix="€",
        showlegend=False,
    )
    st.plotly_chart(fig, use_container_width=True)

    # ---- Action vs Write-off comparison ----
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("### Action vs Write-Off Comparison")
        comp_df = pd.DataFrame({
            "Scenario": ["Transfer Now", "Write Off"],
            "Value": [max(result["Net Value Saved"], 0), result["Write-Off if No Action"]],
            "Type": ["Recovery", "Loss"],
        })
        fig2 = px.bar(
            comp_df, x="Scenario", y="Value", color="Type", text="Value",
            color_discrete_map={"Recovery": "#12b76a", "Loss": "#d92d20"},
            height=320,
        )
        fig2.update_traces(texttemplate="€%{text:,.0f}", textposition="outside")
        fig2.update_layout(paper_bgcolor="#ffffff", plot_bgcolor="#ffffff", font_color="#111827", yaxis_tickprefix="€", showlegend=False)
        st.plotly_chart(fig2, use_container_width=True)

    with c2:
        st.markdown("### Sensitivity: Transfer Units vs Net Value")
        unit_range = list(range(max(1, units // 4), units * 2, max(1, units // 8)))
        sensitivity = [
            compute_roi(u, unit_val, logistics_cost, monthly_usage, days_to_expiry, write_off_pct, commercial_cost)["Net Value Saved"]
            for u in unit_range
        ]
        sens_df = pd.DataFrame({"Units": unit_range, "Net Value Saved": sensitivity})
        fig3 = px.line(
            sens_df, x="Units", y="Net Value Saved",
            markers=True, height=320,
            color_discrete_sequence=["#1f6fb2"],
        )
        fig3.add_hline(y=0, line_dash="dash", line_color="#d92d20", annotation_text="Break-even")
        fig3.update_layout(paper_bgcolor="#ffffff", plot_bgcolor="#ffffff", font_color="#111827", yaxis_tickprefix="€")
        st.plotly_chart(fig3, use_container_width=True)

    # ---- Full metrics table ----
    st.markdown("### Full Metrics Summary")
    metrics_display = {
        "Metric": list(result.keys())[:-2],  # exclude Verdict, Viable
        "Value": [
            _euro(result["Gross Value of Stock"]),
            _euro(result["Logistics Cost"]),
            _euro(result["Commercial Cost"]),
            _euro(result["Net Value Saved"]),
            _euro(result["Write-Off if No Action"]),
            str(result["Break-Even Units"]) + " units",
            (str(result["Payback Days"]) + " days") if result["Payback Days"] is not None else "N/A",
            (str(result["ROI %"]) + "%") if result["ROI %"] is not None else "∞",
        ]
    }
    st.dataframe(pd.DataFrame(metrics_display), use_container_width=True, hide_index=True)
