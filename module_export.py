"""
module_export.py
Executive PDF / Email Export
Generates a clean executive brief as downloadable HTML (print-to-PDF ready)
and a pre-filled email draft — both from live data, zero manual effort.
"""

from datetime import date
import pandas as pd


def _euro(x):
    return f"€{x:,.0f}"


def build_export_html(df, rec_df, demand_df, today):
    """
    Returns a self-contained HTML string styled for print / PDF.
    Works without any external dependencies.
    """

    report_date = today.strftime("%d %B %Y")

    # ---- top-line numbers ----
    total_risk      = df["Value at Risk"].sum()
    recoverable     = rec_df["Net Value Saved"].sum() if not rec_df.empty else 0
    blocked         = int((df["Risk Level"] == "Blocked").sum())
    critical_high   = int(df["Risk Level"].isin(["Critical","High"]).sum())
    total_actions   = len(rec_df)

    # ---- top 5 at-risk batches ----
    top_risk = (
        df.sort_values("Value at Risk", ascending=False)
        .head(5)[["Location","Product","Batch","Days to Expiry","At Risk Qty","Value at Risk","Risk Level"]]
    )

    # ---- top 5 recommendations ----
    top_recs = rec_df.head(5) if not rec_df.empty else pd.DataFrame()

    # ---- risk rows html ----
    risk_rows = ""
    for _, r in top_risk.iterrows():
        color = {"Critical":"#fee2e2","High":"#ffedd5","Medium":"#dbeafe","Low":"#dcfce7","Blocked":"#ede9fe"}.get(r["Risk Level"],"#f8fafc")
        risk_rows += f"""
        <tr style="background:{color}">
            <td>{r['Location']}</td>
            <td>{r['Product']}</td>
            <td>{r['Batch']}</td>
            <td>{int(r['Days to Expiry'])} days</td>
            <td>{int(r['At Risk Qty'])}</td>
            <td><b>{_euro(r['Value at Risk'])}</b></td>
            <td>{r['Risk Level']}</td>
        </tr>"""

    # ---- rec rows html ----
    rec_rows = ""
    if not top_recs.empty:
        for _, r in top_recs.iterrows():
            rec_rows += f"""
        <tr>
            <td>{r['From']}</td>
            <td>{r['To']}</td>
            <td>{r['Product']}</td>
            <td>{int(r['Qty'])}</td>
            <td>{_euro(r['Net Value Saved'])}</td>
            <td>{r['Confidence']}%</td>
            <td>{r['Compliance']}</td>
            <td>{r['Priority']}</td>
        </tr>"""
    else:
        rec_rows = "<tr><td colspan='8' style='text-align:center;color:#64748b'>No redistribution recommendations available</td></tr>"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>Inventory Executive Brief — {report_date}</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;900&display=swap');
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: 'Inter', sans-serif; background: #f8fafc; color: #111827; font-size: 13px; }}
  .page {{ max-width: 960px; margin: 0 auto; padding: 40px 48px; background: #ffffff; }}
  .header {{ background: linear-gradient(135deg,#0b1f3a,#1f6fb2); color: white; border-radius: 16px; padding: 28px 32px; margin-bottom: 28px; }}
  .header h1 {{ font-size: 22px; font-weight: 900; color: white; margin-bottom: 4px; }}
  .header p {{ font-size: 13px; color: #bfdbfe; }}
  .kpi-row {{ display: grid; grid-template-columns: repeat(5, 1fr); gap: 14px; margin-bottom: 28px; }}
  .kpi-box {{ background: #f1f5f9; border-radius: 12px; padding: 16px; text-align: center; }}
  .kpi-box .label {{ font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: .06em; color: #64748b; margin-bottom: 6px; }}
  .kpi-box .value {{ font-size: 20px; font-weight: 900; color: #0b1f3a; }}
  .kpi-box.red .value {{ color: #991b1b; }}
  .kpi-box.green .value {{ color: #166534; }}
  .kpi-box.amber .value {{ color: #92400e; }}
  .section {{ margin-bottom: 28px; }}
  .section h2 {{ font-size: 14px; font-weight: 800; color: #0b1f3a; margin-bottom: 12px; border-bottom: 2px solid #e2e8f0; padding-bottom: 6px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 12px; }}
  th {{ background: #0b1f3a; color: white; padding: 9px 10px; text-align: left; font-weight: 700; font-size: 11px; }}
  td {{ padding: 8px 10px; border-bottom: 1px solid #e2e8f0; }}
  tr:last-child td {{ border-bottom: none; }}
  .footer {{ margin-top: 32px; padding-top: 16px; border-top: 1px solid #e2e8f0; font-size: 11px; color: #94a3b8; display: flex; justify-content: space-between; }}
  .note {{ background: #eef6ff; border-left: 4px solid #1f6fb2; border-radius: 8px; padding: 12px 16px; font-size: 12px; color: #1e3a5f; margin-bottom: 20px; }}
  @media print {{
    body {{ background: white; }}
    .page {{ padding: 20px; box-shadow: none; }}
  }}
</style>
</head>
<body>
<div class="page">

  <div class="header">
    <h1>Neurovascular Inventory — Executive Brief</h1>
    <p>Prepared: {report_date} &nbsp;·&nbsp; Confidential &nbsp;·&nbsp; For internal use only</p>
  </div>

  <div class="kpi-row">
    <div class="kpi-box red">
      <div class="label">Total Value at Risk</div>
      <div class="value">{_euro(total_risk)}</div>
    </div>
    <div class="kpi-box green">
      <div class="label">Recoverable Value</div>
      <div class="value">{_euro(recoverable)}</div>
    </div>
    <div class="kpi-box amber">
      <div class="label">Critical / High Batches</div>
      <div class="value">{critical_high}</div>
    </div>
    <div class="kpi-box red">
      <div class="label">Blocked Batches</div>
      <div class="value">{blocked}</div>
    </div>
    <div class="kpi-box">
      <div class="label">Recommended Actions</div>
      <div class="value">{total_actions}</div>
    </div>
  </div>

  <div class="note">
    <b>Summary:</b> The system has identified {_euro(total_risk)} of inventory value at risk of expiry or write-off.
    Through demand-matched redistribution, an estimated <b>{_euro(recoverable)}</b> is recoverable.
    {critical_high} batches are rated Critical or High urgency. {blocked} batch(es) are currently blocked for quality or compliance reasons.
    Immediate action on the top recommendations below is advised.
  </div>

  <div class="section">
    <h2>Top At-Risk Inventory Positions</h2>
    <table>
      <thead>
        <tr>
          <th>Location</th><th>Product</th><th>Batch</th>
          <th>Days to Expiry</th><th>At-Risk Qty</th>
          <th>Value at Risk</th><th>Risk Level</th>
        </tr>
      </thead>
      <tbody>{risk_rows}</tbody>
    </table>
  </div>

  <div class="section">
    <h2>Recommended Redistribution Actions</h2>
    <table>
      <thead>
        <tr>
          <th>From</th><th>To</th><th>Product</th><th>Qty</th>
          <th>Net Value Saved</th><th>Confidence</th><th>Compliance</th><th>Priority</th>
        </tr>
      </thead>
      <tbody>{rec_rows}</tbody>
    </table>
  </div>

  <div class="footer">
    <span>Neurovascular Inventory Control Tower</span>
    <span>Generated {report_date} &nbsp;·&nbsp; Data as of system snapshot</span>
  </div>

</div>
</body>
</html>"""
    return html


def build_email_draft(df, rec_df, today):
    """
    Returns a plain-text pre-filled email draft string.
    """
    report_date = today.strftime("%d %B %Y")
    total_risk  = df["Value at Risk"].sum()
    recoverable = rec_df["Net Value Saved"].sum() if not rec_df.empty else 0
    critical_high = int(df["Risk Level"].isin(["Critical","High"]).sum())

    top3 = []
    if not rec_df.empty:
        for _, r in rec_df.head(3).iterrows():
            top3.append(
                f"  • Transfer {int(r['Qty'])} units of {r['Product']} (Batch {r['Batch']}) "
                f"from {r['From']} to {r['To']} — Net saving: {_euro(r['Net Value Saved'])} "
                f"| Confidence: {r['Confidence']}% | {r['Compliance']}"
            )
    top3_text = "\n".join(top3) if top3 else "  No redistribution actions currently available."

    top_risk_row = df.sort_values("Value at Risk", ascending=False).iloc[0]

    email = f"""Subject: Inventory Risk Alert — Action Required by [DATE]

Dear [Name],

I'm writing to flag an urgent inventory position that requires leadership decision this week.

SITUATION SUMMARY ({report_date})
───────────────────────────────────
• Total inventory value at risk of expiry: {_euro(total_risk)}
• Estimated recoverable through redistribution: {_euro(recoverable)}
• Batches rated Critical or High urgency: {critical_high}
• Highest single exposure: {top_risk_row['Product']} batch {top_risk_row['Batch']} at {top_risk_row['Location']} — {_euro(top_risk_row['Value at Risk'])} | {int(top_risk_row['Days to Expiry'])} days to expiry

TOP RECOMMENDED ACTIONS
───────────────────────────────────
{top3_text}

NEXT STEPS REQUESTED
───────────────────────────────────
1. Approve redistribution transfers listed above by [DATE]
2. Confirm logistics coordination with supply chain team
3. Flag any compliance or regulatory concerns before transfer initiation

The full interactive analysis is available in the Inventory Control Tower dashboard.
Please revert by [DATE] to avoid further expiry exposure.

Best regards,
[Your Name]
[Title] | [Team]
"""
    return email


def render_export_page(df, rec_df, demand_df, today):
    """
    Streamlit page — call this from the main router.
    """
    import streamlit as st

    st.markdown('<div class="section-title">Executive Export</div>', unsafe_allow_html=True)
    st.markdown(
        '<p class="small-muted">Generate a one-click executive brief as a print-ready HTML report or a pre-filled email draft — built from live inventory data.</p>',
        unsafe_allow_html=True,
    )

    tab1, tab2 = st.tabs(["📄 PDF / Print Report", "✉️ Email Draft"])

    with tab1:
        st.markdown("### Executive Brief — Print / PDF")
        st.markdown(
            """
<div class="info-box">
    <h4>How to use</h4>
    <p>Click <b>Generate Report</b> to build the brief from current data. Then click <b>Download HTML</b>.
    Open the file in any browser and use <b>File → Print → Save as PDF</b> for a clean one-page PDF.</p>
</div>
""",
            unsafe_allow_html=True,
        )

        col1, col2 = st.columns(2)
        with col1:
            include_recs  = st.checkbox("Include redistribution recommendations", value=True)
            include_risks = st.checkbox("Include top at-risk batches", value=True)
        with col2:
            report_title = st.text_input("Custom report title (optional)", placeholder="e.g. Q2 2026 Inventory Review")

        if st.button("Generate Report", type="primary", key="gen_report_btn"):
            html = build_export_html(df, rec_df if include_recs else pd.DataFrame(), demand_df, today)

            if report_title:
                html = html.replace("Neurovascular Inventory — Executive Brief", report_title)

            if not include_risks:
                # strip the risk table section — simple marker approach
                import re
                html = re.sub(r'<div class="section">.*?Top At-Risk.*?</div>\s*</div>', "", html, flags=re.DOTALL)

            st.download_button(
                label="⬇️ Download HTML Report",
                data=html.encode("utf-8"),
                file_name=f"inventory_brief_{today.strftime('%Y%m%d')}.html",
                mime="text/html",
                key="download_html_btn",
            )

            st.markdown("#### Preview")
            st.components.v1.html(html, height=680, scrolling=True)

    with tab2:
        st.markdown("### Pre-Filled Email Draft")
        st.markdown(
            """
<div class="info-box">
    <h4>How to use</h4>
    <p>The draft is auto-built from live data. Edit the placeholders in <b>[brackets]</b>, then copy into your email client.</p>
</div>
""",
            unsafe_allow_html=True,
        )

        email_text = build_email_draft(df, rec_df, today)

        edited = st.text_area(
            "Email draft (edit before sending)",
            value=email_text,
            height=480,
            key="email_draft_area",
        )

        c1, c2 = st.columns(2)
        with c1:
            st.download_button(
                label="⬇️ Download as .txt",
                data=edited.encode("utf-8"),
                file_name=f"inventory_email_draft_{today.strftime('%Y%m%d')}.txt",
                mime="text/plain",
                key="download_email_btn",
            )
        with c2:
            if st.button("🔄 Regenerate from latest data", key="regen_email_btn"):
                st.rerun()

        st.caption("Tip: Placeholders like [Name], [DATE], [Title] should be replaced before sending.")
