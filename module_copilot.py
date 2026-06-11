"""
module_copilot.py
Inventory Intelligence Copilot — proactive observations + chat-style Q&A.

Purpose:
- Auto-surfaces business insights from inventory, demand, and redistribution data.
- Provides a chat-style interface with suggested questions.
- Falls back to deterministic rule-based answers when no LLM API key is present.
"""

from __future__ import annotations

import html
import os
from typing import Any

import pandas as pd


def _money(x: float | int) -> str:
    """Format currency in a generic business-friendly way."""
    try:
        return f"€{float(x):,.0f}"
    except Exception:
        return "€0"


def _safe_col(df: pd.DataFrame, col: str, default: Any = None) -> pd.Series:
    """Return a column if present, otherwise a default Series."""
    if col in df.columns:
        return df[col]
    return pd.Series([default] * len(df), index=df.index)


def _first_available_col(df: pd.DataFrame, options: list[str], default: str = "") -> pd.Series:
    """Return the first matching column from a list of options."""
    for col in options:
        if col in df.columns:
            return df[col]
    return pd.Series([default] * len(df), index=df.index)


# -----------------------------------------------------------------------
# PROACTIVE INSIGHT GENERATOR
# -----------------------------------------------------------------------

def generate_proactive_insights(
    df: pd.DataFrame,
    rec_df: pd.DataFrame,
    demand_df: pd.DataFrame,
    today=None,
) -> list[dict[str, str]]:
    """
    Returns a list of insight dicts:
    {
        "title": str,
        "body": str,
        "severity": "critical" | "warning" | "info" | "success"
    }
    """
    insights: list[dict[str, str]] = []

    if df is None or df.empty:
        return [{
            "title": "No inventory data available",
            "body": "Upload or connect inventory data to generate risk observations and recommendations.",
            "severity": "info",
        }]

    work = df.copy()

    # Defensive default columns
    work["Days to Expiry"] = pd.to_numeric(_safe_col(work, "Days to Expiry", 9999), errors="coerce").fillna(9999)
    work["At Risk Qty"] = pd.to_numeric(_safe_col(work, "At Risk Qty", 0), errors="coerce").fillna(0)
    work["Inventory Value"] = pd.to_numeric(_safe_col(work, "Inventory Value", 0), errors="coerce").fillna(0)
    work["Value at Risk"] = pd.to_numeric(_safe_col(work, "Value at Risk", 0), errors="coerce").fillna(0)
    work["Risk Level"] = _safe_col(work, "Risk Level", "Unknown")
    work["Location"] = _safe_col(work, "Location", "Unknown location")
    work["SKU"] = _safe_col(work, "SKU", "")
    work["Product"] = _safe_col(work, "Product", "Product")
    work["Batch"] = _safe_col(work, "Batch", "Batch")
    work["Qty"] = pd.to_numeric(_safe_col(work, "Qty", 0), errors="coerce").fillna(0)
    work["Expected Usage Before Expiry"] = pd.to_numeric(
        _safe_col(work, "Expected Usage Before Expiry", 0), errors="coerce"
    ).fillna(0)
    work["Usable Inventory Score"] = pd.to_numeric(
        _safe_col(work, "Usable Inventory Score", 100), errors="coerce"
    ).fillna(100)
    work["Recall Status"] = _safe_col(work, "Recall Status", "Clear")

    demand = demand_df.copy() if demand_df is not None else pd.DataFrame()
    recs = rec_df.copy() if rec_df is not None else pd.DataFrame()

    # 1. Batches expiring within 60 days with no matched demand
    expiring_soon = work[(work["Days to Expiry"] <= 60) & (work["At Risk Qty"] > 0)].copy()
    no_demand_locations: list[str] = []
    if not expiring_soon.empty:
        for _, row in expiring_soon.iterrows():
            has_demand = False
            if not demand.empty and "SKU" in demand.columns:
                has_demand = not demand[demand["SKU"].astype(str) == str(row["SKU"])].empty
            if not has_demand:
                no_demand_locations.append(str(row["Location"]))

    if no_demand_locations:
        insights.append({
            "title": f"{len(no_demand_locations)} batch(es) expiring within 60 days with no matched demand",
            "body": (
                f"Affected locations: {', '.join(no_demand_locations)}. "
                "These batches are at elevated write-off risk unless transferred, consumed, or reviewed."
            ),
            "severity": "critical",
        })

    # 2. Blocked batches holding capital
    blocked = work[work["Risk Level"].astype(str).str.lower().eq("blocked")]
    if not blocked.empty:
        blocked_value = blocked["Inventory Value"].sum()
        locations = ", ".join(blocked["Location"].astype(str).unique().tolist())
        insights.append({
            "title": f"{len(blocked)} blocked batch(es) holding {_money(blocked_value)}",
            "body": (
                f"Affected locations: {locations}. These batches cannot be transferred until "
                "quality, recall, or compliance holds are resolved."
            ),
            "severity": "critical",
        })

    # 3. Highest recovery opportunity
    if not recs.empty and "Net Value Saved" in recs.columns:
        recs["Net Value Saved"] = pd.to_numeric(recs["Net Value Saved"], errors="coerce").fillna(0)
        top = recs.sort_values("Net Value Saved", ascending=False).iloc[0]
        product = top.get("Product", "product")
        batch = top.get("Batch", "batch")
        source = top.get("From", "source")
        destination = top.get("To", "destination")
        qty = int(pd.to_numeric(top.get("Qty", 0), errors="coerce") or 0)
        confidence = top.get("Confidence", "N/A")
        compliance = top.get("Compliance", "N/A")
        insights.append({
            "title": f"Highest recovery opportunity: {_money(top['Net Value Saved'])}",
            "body": (
                f"Move {qty} unit(s) of {product} batch {batch} from {source} to {destination}. "
                f"Confidence: {confidence}%. Compliance status: {compliance}."
            ),
            "severity": "success",
        })

    # 4. Low usable inventory score
    low_score = work[work["Usable Inventory Score"] < 40].copy()
    if not low_score.empty:
        worst = low_score.sort_values("Usable Inventory Score").iloc[0]
        insights.append({
            "title": f"Usable inventory score is critically low at {worst['Location']}",
            "body": (
                f"{worst['Product']} batch {worst['Batch']} has a usable score of "
                f"{worst['Usable Inventory Score']:.0f}%. Expected usage before expiry is "
                f"{int(worst['Expected Usage Before Expiry'])} unit(s) against {int(worst['Qty'])} in stock."
            ),
            "severity": "warning",
        })

    # 5. Demand outstripping available clear supply
    if not demand.empty and {"SKU", "Expected Demand 60D"}.issubset(demand.columns):
        demand["Expected Demand 60D"] = pd.to_numeric(demand["Expected Demand 60D"], errors="coerce").fillna(0)
        for sku in demand["SKU"].dropna().astype(str).unique():
            total_demand = demand[demand["SKU"].astype(str) == sku]["Expected Demand 60D"].sum()
            total_supply = work[(work["SKU"].astype(str) == sku) & (work["Recall Status"].astype(str) == "Clear")]["Qty"].sum()
            if total_supply > 0 and total_demand > total_supply * 0.8:
                product_name = demand[demand["SKU"].astype(str) == sku].iloc[0].get("Product", sku)
                insights.append({
                    "title": f"Demand may outstrip clear supply for {product_name}",
                    "body": (
                        f"Expected 60-day demand is {int(total_demand)} unit(s), while clear available "
                        f"stock is {int(total_supply)} unit(s). Consider reallocation or production planning."
                    ),
                    "severity": "warning",
                })

    # 6. Recoverable value summary
    total_risk = work["Value at Risk"].sum()
    recoverable = recs["Net Value Saved"].sum() if not recs.empty and "Net Value Saved" in recs.columns else 0
    if total_risk > 0:
        pct = (recoverable / total_risk * 100) if total_risk else 0
        insights.append({
            "title": f"{pct:.0f}% of at-risk value is recoverable through recommendations",
            "body": (
                f"Total exposure is {_money(total_risk)}. Recommended transfers can recover "
                f"approximately {_money(recoverable)} after logistics cost."
            ),
            "severity": "info",
        })

    return insights


# -----------------------------------------------------------------------
# ANSWER ENGINE
# -----------------------------------------------------------------------

def _fallback_answer(q: str, df: pd.DataFrame, rec_df: pd.DataFrame) -> str:
    """Rule-based answer engine used when no LLM key is configured."""
    q_lower = q.lower().strip()

    if df is None or df.empty:
        return "No inventory data is available yet. Connect or upload inventory data to analyze risk, demand, and redistribution options."

    work = df.copy()
    work["Value at Risk"] = pd.to_numeric(_safe_col(work, "Value at Risk", 0), errors="coerce").fillna(0)
    work["Days to Expiry"] = pd.to_numeric(_safe_col(work, "Days to Expiry", 9999), errors="coerce").fillna(9999)
    work["Risk Level"] = _safe_col(work, "Risk Level", "Unknown")
    work["Location"] = _safe_col(work, "Location", "Unknown location")
    work["Product"] = _safe_col(work, "Product", "Product")
    work["Batch"] = _safe_col(work, "Batch", "Batch")
    work["At Risk Qty"] = pd.to_numeric(_safe_col(work, "At Risk Qty", 0), errors="coerce").fillna(0)
    work["Inventory Value"] = pd.to_numeric(_safe_col(work, "Inventory Value", 0), errors="coerce").fillna(0)

    recs = rec_df.copy() if rec_df is not None else pd.DataFrame()
    if not recs.empty and "Net Value Saved" in recs.columns:
        recs["Net Value Saved"] = pd.to_numeric(recs["Net Value Saved"], errors="coerce").fillna(0)

    if any(w in q_lower for w in ["transfer", "redistribute", "move", "recommendation", "action"]):
        if not recs.empty:
            top = recs.sort_values("Net Value Saved", ascending=False).iloc[0] if "Net Value Saved" in recs.columns else recs.iloc[0]
            return (
                f"Top recommended action: move {int(pd.to_numeric(top.get('Qty', 0), errors='coerce') or 0)} unit(s) "
                f"of {top.get('Product', 'product')} batch {top.get('Batch', 'batch')} "
                f"from {top.get('From', 'source')} to {top.get('To', 'destination')}. "
                f"Estimated net value saved: {_money(top.get('Net Value Saved', 0))}. "
                f"Confidence: {top.get('Confidence', 'N/A')}%. Compliance status: {top.get('Compliance', 'N/A')}."
            )
        return "There are no transfer recommendations available from the current dataset."

    if any(w in q_lower for w in ["highest risk", "most at risk", "biggest exposure", "worst", "risk"]):
        top = work.sort_values("Value at Risk", ascending=False).iloc[0]
        return (
            f"The highest financial exposure is {top['Product']} batch {top['Batch']} at {top['Location']}. "
            f"Value at risk: {_money(top['Value at Risk'])}. "
            f"Days to expiry: {int(top['Days to Expiry'])}. Risk level: {top['Risk Level']}."
        )

    if any(w in q_lower for w in ["compliance", "eligible", "blocked", "quality", "regulatory", "recall"]):
        blocked = work[work["Risk Level"].astype(str).str.lower().eq("blocked")]
        if blocked.empty:
            return "No batches are currently blocked. Transfer eligibility should still be validated using lot traceability, expiry validity, recall status, and storage-condition checks."
        value = blocked["Inventory Value"].sum()
        locations = ", ".join(blocked["Location"].astype(str).unique().tolist())
        return f"{len(blocked)} batch(es) are currently blocked at {locations}, holding {_money(value)} in inventory value. They cannot be transferred until the hold is cleared."

    if any(w in q_lower for w in ["nothing", "do nothing", "no action", "ignore"]):
        total_risk = work["Value at Risk"].sum()
        recoverable = recs["Net Value Saved"].sum() if not recs.empty and "Net Value Saved" in recs.columns else 0
        return (
            f"If no action is taken, estimated write-off exposure is {_money(total_risk)}. "
            f"Recommended redistribution actions can potentially recover {_money(recoverable)} of that exposure."
        )

    if any(w in q_lower for w in ["calculate", "at-risk", "at risk", "formula", "quantity"]):
        return (
            "At-risk quantity is calculated as: Current Stock minus Expected Usage Before Expiry minus Safety Stock. "
            "Expected Usage is based on monthly usage and time remaining before expiry. Negative values are treated as zero risk."
        )

    if any(w in q_lower for w in ["recover", "recoverable", "save", "savings", "value"]):
        recoverable = recs["Net Value Saved"].sum() if not recs.empty and "Net Value Saved" in recs.columns else 0
        return (
            f"Estimated recoverable value from current recommendations is {_money(recoverable)}. "
            "This is net of logistics cost where that field is available."
        )

    if any(w in q_lower for w in ["expired", "expiry", "expire", "near expiry"]):
        expiring = work[(work["Days to Expiry"] <= 60) & (work["At Risk Qty"] > 0)].copy()
        if expiring.empty:
            return "No at-risk batches are expiring within 60 days based on the current dataset."
        top = expiring.sort_values("Days to Expiry").iloc[0]
        return (
            f"The most urgent expiry item is {top['Product']} batch {top['Batch']} at {top['Location']}, "
            f"with {int(top['Days to Expiry'])} day(s) remaining and {int(top['At Risk Qty'])} at-risk unit(s)."
        )

    top_risk = work.sort_values("Value at Risk", ascending=False).iloc[0]
    return (
        "The control tower monitors expiry risk, demand matching, compliance, and redistribution economics. "
        f"Currently, the highest single exposure is {top_risk['Product']} at {top_risk['Location']} "
        f"with {_money(top_risk['Value at Risk'])} at risk. Ask about risk, expiry, transfers, compliance, or recoverable value."
    )


def _try_groq(q: str, df: pd.DataFrame, rec_df: pd.DataFrame, api_key: str, Groq) -> str:
    """Optional LLM answer engine. Uses only provided data context."""
    inventory_cols = [
        "Location", "Product", "Batch", "Expiry", "Qty", "At Risk Qty",
        "Value at Risk", "Risk Level", "Recall Status", "Transfer Allowed"
    ]
    available_inventory_cols = [c for c in inventory_cols if c in df.columns]

    context = f"""
Inventory positions:
{df[available_inventory_cols].to_string(index=False) if available_inventory_cols else df.to_string(index=False)}

System recommendations:
{rec_df.to_string(index=False) if rec_df is not None and not rec_df.empty else "None available"}
"""

    client = Groq(api_key=api_key)
    res = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are an enterprise medical-device inventory intelligence copilot. "
                    "Use only the data provided. Be concise, factual, and business-ready. "
                    "Always quantify answers with numbers from the data. "
                    "Never mention any specific company name. Never fabricate data. "
                    "If the data is insufficient, say exactly what is missing."
                ),
            },
            {"role": "user", "content": context},
            {"role": "user", "content": q},
        ],
        temperature=0.2,
        max_tokens=600,
    )
    return res.choices[0].message.content


# -----------------------------------------------------------------------
# CHAT UI
# -----------------------------------------------------------------------

def _answer_question(q: str, df: pd.DataFrame, rec_df: pd.DataFrame) -> str:
    """Route question to LLM if available, otherwise fallback."""
    try:
        from groq import Groq
    except Exception:
        Groq = None

    api_key = os.getenv("GROQ_API_KEY", "")
    if api_key and Groq is not None:
        try:
            return _try_groq(q, df, rec_df, api_key, Groq)
        except Exception:
            return _fallback_answer(q, df, rec_df)

    return _fallback_answer(q, df, rec_df)


def _render_message(role: str, content: str) -> None:
    """Render a chat bubble with Streamlit chat_message if available."""
    import streamlit as st

    safe_content = str(content)

    try:
        with st.chat_message("user" if role == "user" else "assistant"):
            st.markdown(safe_content)
    except Exception:
        # Fallback for older Streamlit versions
        if role == "user":
            st.markdown(
                f"""
<div style="display:flex;justify-content:flex-end;margin:8px 0;">
  <div style="max-width:78%;background:#dbeafe;color:#0b1f3a;border-radius:16px 16px 4px 16px;padding:12px 14px;font-size:14px;">
    {html.escape(safe_content)}
  </div>
</div>
""",
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f"""
<div style="display:flex;justify-content:flex-start;margin:8px 0;">
  <div style="max-width:78%;background:#ffffff;border:1px solid #dbe3ef;color:#111827;border-radius:16px 16px 16px 4px;padding:12px 14px;font-size:14px;box-shadow:0 4px 12px rgba(0,0,0,0.04);">
    {html.escape(safe_content)}
  </div>
</div>
""",
                unsafe_allow_html=True,
            )


def render_copilot_page(
    df: pd.DataFrame,
    rec_df: pd.DataFrame,
    demand_df: pd.DataFrame,
    today=None,
) -> None:
    """
    Render the Inventory Copilot page.

    Expected dataframes:
    - df: inventory positions
    - rec_df: recommended transfers
    - demand_df: demand signals
    """
    import streamlit as st

    st.markdown('<div class="section-title">Inventory Copilot</div>', unsafe_allow_html=True)
    st.markdown(
        '<p class="small-muted">Chat with the control tower using live inventory, expiry, demand, compliance, and transfer data.</p>',
        unsafe_allow_html=True,
    )

    # CSS cleanup for chat-like layout and clear question buttons
    st.markdown(
        """
<style>
.chat-suggestion-title {
    font-size: 13px;
    font-weight: 800;
    color: #334155;
    margin: 8px 0 4px 0;
}
.insight-card {
    border-radius: 14px;
    padding: 14px 18px;
    margin-bottom: 10px;
}
div[data-testid="stChatMessage"] {
    border-radius: 16px;
}
</style>
""",
        unsafe_allow_html=True,
    )

    # Proactive insights, kept as one clear section
    with st.expander("System observations", expanded=True):
        insights = generate_proactive_insights(df, rec_df, demand_df, today)

        severity_styles = {
            "critical": ("background:#fee2e2;border-left:5px solid #d92d20;", "#7f1d1d", "🔴"),
            "warning":  ("background:#ffedd5;border-left:5px solid #f79009;", "#78350f", "🟡"),
            "success":  ("background:#dcfce7;border-left:5px solid #12b76a;", "#14532d", "🟢"),
            "info":     ("background:#eef6ff;border-left:5px solid #1f6fb2;", "#1e3a5f", "🔵"),
        }

        if not insights:
            st.info("No active observations — all inventory positions appear stable.")
        else:
            for ins in insights[:6]:
                style, text_color, icon = severity_styles.get(ins["severity"], severity_styles["info"])
                st.markdown(
                    f"""
<div class="insight-card" style="{style}">
    <div style="font-weight:800;font-size:14px;color:{text_color};margin-bottom:4px;">{icon} {html.escape(ins['title'])}</div>
    <div style="font-size:13px;color:{text_color};opacity:0.92;">{html.escape(ins['body'])}</div>
</div>
""",
                    unsafe_allow_html=True,
                )

    # Initialize chat history with assistant greeting
    if "copilot_chat_history" not in st.session_state:
        st.session_state["copilot_chat_history"] = [
            {
                "role": "assistant",
                "content": (
                    "Hi — I can help you inspect inventory risk, expiry exposure, redistribution options, "
                    "compliance holds, and recoverable value. Choose a question below or type your own."
                ),
            }
        ]

    suggested_questions = [
        "Which batch has the highest financial risk?",
        "Which transfer should be prioritized first?",
        "Which products are near expiry?",
        "Which transfers are compliance eligible?",
        "What happens if we do nothing?",
        "How is at-risk quantity calculated?",
        "What is the total recoverable value?",
        "Which batches are blocked or on quality hold?",
    ]

    st.markdown('<div class="chat-suggestion-title">Suggested questions</div>', unsafe_allow_html=True)

    # Render suggested questions as chat-like quick action buttons
    cols = st.columns(2)
    clicked_question = None
    for i, question in enumerate(suggested_questions):
        with cols[i % 2]:
            if st.button(question, key=f"copilot_suggestion_{i}", use_container_width=True):
                clicked_question = question

    # Render chat history
    st.markdown("### Chat")
    for msg in st.session_state["copilot_chat_history"]:
        _render_message(msg["role"], msg["content"])

    # User input via chat_input where supported
    prompt = None
    try:
        prompt = st.chat_input("Ask about inventory risk, expiry, transfer recommendations, or compliance...")
    except Exception:
        prompt = st.text_input(
            "Ask a question",
            placeholder="Ask about inventory risk, expiry, transfer recommendations, or compliance...",
            key="copilot_text_input",
        )
        send = st.button("Send", type="primary", key="copilot_send")
        if not send:
            prompt = None

    # If suggested question clicked, treat it exactly like user chat input
    if clicked_question:
        prompt = clicked_question

    if prompt and str(prompt).strip():
        question = str(prompt).strip()
        answer = _answer_question(question, df, rec_df)

        st.session_state["copilot_chat_history"].append({"role": "user", "content": question})
        st.session_state["copilot_chat_history"].append({"role": "assistant", "content": answer})
        st.rerun()

    col_clear, col_spacer = st.columns([1, 5])
    with col_clear:
        if st.button("Clear chat", key="copilot_clear_chat"):
            st.session_state["copilot_chat_history"] = [
                {
                    "role": "assistant",
                    "content": (
                        "Chat cleared. Choose a suggested question or type a new one."
                    ),
                }
            ]
            st.rerun()
