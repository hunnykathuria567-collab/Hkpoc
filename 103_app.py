import streamlit as st
import os
import re
import pandas as pd
import databricks.sql
import google.generativeai as genai
from dotenv import load_dotenv
from typing import TypedDict, Optional, Dict, Any
from langgraph.graph import StateGraph, END

# ==========================================
# 1. INITIALIZATION & CONFIG
# ==========================================
load_dotenv('.env_0228')
load_dotenv('.env')

api_key = os.getenv("GEMINI_MODEL_KEY")
model_name = os.getenv("GEMINI_MODEL_NAME")

if not model_name:
    model_name = "gemini-2.5-flash"

if api_key:
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(model_name)

st.set_page_config(page_title="Strategic Architect Dashboard", layout="wide")

# ==========================================
# 2. LANGGRAPH STATE DEFINITION
# ==========================================
class AgentState(TypedDict):
    user_query: str
    intent_map: Dict[str, Any]
    status: str
    clarification_request: Optional[Dict[str, Any]]
    generated_sql: Optional[str]
    error_feedback: Optional[str]
    retry_count: int
    final_payload: Optional[Dict[str, Any]]

# ==========================================
# 3. AGENT NODES
# ==========================================
def run_opener_node(state: AgentState) -> AgentState:
    query = state["user_query"]
    
    intent_map = {"metric": "funnel metrics", "time_filter": "2025-Q4", "filters": None, "is_comparison": False}
    if "compare" in query.lower() or "both" in query.lower():
        intent_map["is_comparison"] = True

    if "team" not in query.lower() and "mql" not in query.lower() and "smb" not in query.lower():
        return {
            **state,
            "status": "needs_clarification",
            "intent_map": intent_map,
            "clarification_request": {
                "param": "Team_Type",
                "prompt": "Which team's pipeline would you like to analyze?",
                "options": ["MQL", "SMB", "BOTH"]
            }
        }
        
    return {**state, "status": "ready_for_sql", "intent_map": intent_map}

def run_pacer_node(state: AgentState) -> AgentState:
    mock_sql = """
    SELECT Team_Type, Week_Number, COUNT(DISTINCT Lead_id) as total_leads 
    FROM b2b_tmp.vw_fact_leads_unified_hk_12DEC 
    WHERE Is_Valid_For_Metrics = 1 AND Reporting_Quarter = '2025-Q4'
    GROUP BY Team_Type, Week_Number
    ORDER BY Week_Number
    """
    return {**state, "status": "auditing", "generated_sql": mock_sql.strip()}

def run_wicket_keeper_node(state: AgentState) -> AgentState:
    sql_to_test = state["generated_sql"]
    if re.search(r'\bWHERE\b', sql_to_test, re.IGNORECASE):
        dry_run_sql = re.sub(r'\b(WHERE)\b', r'\1 1=0 AND ', sql_to_test, count=1, flags=re.IGNORECASE)
    else:
        dry_run_sql = f"{sql_to_test} WHERE 1=0"

    try:
        if os.getenv("DATABRICKS_SERVER_HOSTNAME"):
            conn = databricks.sql.connect(
                server_hostname=os.getenv("DATABRICKS_SERVER_HOSTNAME"),
                http_path=os.getenv("DATABRICKS_HTTP_PATH"),
                access_token=os.getenv("DATABRICKS_TOKEN")
            )
            cursor = conn.cursor()
            cursor.execute(dry_run_sql)
            cursor.close()
            conn.close()
        return {**state, "status": "ready_for_captain", "error_feedback": None}
    except Exception as e:
        retries = state.get("retry_count", 0) + 1
        if retries >= 3:
            return {**state, "status": "complete", "final_payload": {"error": "Max retries hit. Manual review required."}}
        return {**state, "status": "sql_failed", "error_feedback": str(e), "retry_count": retries}

def run_captain_node(state: AgentState) -> AgentState:
    is_comparison = state["intent_map"].get("is_comparison", True)
    
    raw_data = [
        {"Team_Type": "MQL", "Total Leads (K)": 69.8, "Touched %": 64.6, "Dispose %": 55.1, "Converted %": 3.5},
        {"Team_Type": "SMB", "Total Leads (K)": 186.6, "Touched %": 68.2, "Dispose %": 39.4, "Converted %": 3.6}
    ]
    
    chart_type = "line" if is_comparison else "bar"
    
    payload = {
        "kpis": [
            {"label": "Touched %", "value": "64.6%", "delta": "0.4% low", "icon": "✋"},
            {"label": "Converted %", "value": "3.5%", "delta": "-0.2% low", "icon": "🎯"},
            {"label": "Total Leads (K)", "value": "186.6K", "delta": "+3.7K high", "icon": "📈"},
            {"label": "Dispose %", "value": "55.1%", "delta": "+5.1% high", "icon": "🗑️"}
        ],
        "insights_grid": {
            "Executive Summary": ["Q4 2025 campaign performance shows strong MQL engagement.", "SMB leads at 186.6K exceed MQL (69.8K)."],
            "Trend Analysis": ["Q4 2025 week-over-week MQL touched stable.", "SMB lead-to-won 3.5% vs MQL 2.3% conversion trends."],
            "Key Insights": ["SMB total leads 186.6K - 2.7x MQL volume.", "MQL ARPT $3.7K (+68%) vs SMB $2.2K.", "SMB touched rate (68.2%) exceeds MQL by 3.6pp."],
            "Growth Insights": ["SMB total leads 186.6K > 2.7x MQL volume.", "MQL ARPT $3.7K + 68% vs SMB $2.2K conversion optimization."],
            "Volatility": ["Weekly variance within acceptable range.", "MQL disposed 55.1% vs SMB 39.4% lead quality profiles."],
            "Promotional Correlation": ["Q4 seasonal patterns align with campaign timing.", "NQL demand gen vs SMB sales conversion rates."]
        },
        "chart_title": "Weekly Lead Trends (K) - Q4 2025",
        "chart_type": chart_type,
        "chart_index": ["W1", "W2", "W3", "W4", "W5", "W6", "W7", "W8", "W9", "W10", "W11", "W12"],
        "chart_data": {
            "MQL": [5.2, 5.5, 5.8, 6.0, 5.9, 6.2, 6.1, 5.8, 5.7, 5.9, 5.8, 5.9],
            "SMB": [14.5, 15.0, 15.2, 16.1, 15.8, 16.5, 16.2, 15.5, 15.0, 15.4, 15.2, 16.2]
        },
        "sql": state["generated_sql"],
        "data": raw_data
    }
    return {**state, "status": "complete", "final_payload": payload}

# ==========================================
# 4. LANGGRAPH ORCHESTRATION
# ==========================================
workflow = StateGraph(AgentState)
workflow.add_node("the_opener", run_opener_node)
workflow.add_node("the_pacer", run_pacer_node)
workflow.add_node("the_wicket_keeper", run_wicket_keeper_node)
workflow.add_node("the_captain", run_captain_node)

workflow.set_entry_point("the_opener")
workflow.add_conditional_edges("the_opener", lambda state: END if state["status"] == "needs_clarification" else "the_pacer")
workflow.add_edge("the_pacer", "the_wicket_keeper")
workflow.add_conditional_edges("the_wicket_keeper", lambda state: "the_pacer" if state["status"] == "sql_failed" else "the_captain")
workflow.add_edge("the_captain", END)

app_graph = workflow.compile()

# ==========================================
# 5. UI STREAMLIT MAIN
# ==========================================
def main():
    st.markdown("""
        <style>
        @keyframes blinker { 50% { opacity: 0; } }
        .blink-green { color: #10b981; animation: blinker 1s linear infinite; font-size: 10px; }
        .solid-green { color: #10b981; font-size: 10px; }
        .solid-gray { color: #d1d5db; font-size: 10px; }
        .status-text { font-weight: 600; font-family: sans-serif; font-size: 16px; margin-left: 10px; color: #374151;}
        
        .kpi-card {
            background-color: #f8f9fa;
            border-radius: 12px;
            padding: 25px 15px;
            text-align: center;
            box-shadow: 0 4px 6px rgba(0,0,0,0.05);
            border: 1px solid #e5e7eb;
            margin-bottom: 20px;
        }
        .kpi-icon { font-size: 48px; margin-bottom: 12px; }
        .kpi-label { font-size: 24px; font-weight: 800; color: #1e3a8a; margin-bottom: 8px; }
        .kpi-val { font-size: 20px; font-weight: 700; color: #111827; }
        .kpi-delta { font-size: 15px; margin-top: 8px; font-weight: 500;}
        .delta-high { color: #10b981; }
        .delta-low { color: #ef4444; }
        
        /* =========================================================
           NUCLEAR PRINT CSS - FIXES RIGHT SIDE CROPPING
           ========================================================= */
        @media print {
            @page { 
                size: landscape !important; 
                margin: 10mm !important; 
            }
            
            body, html, .stApp { 
                zoom: 0.70 !important; 
                background: white !important;
            }
            
            [data-testid="stSidebar"], [data-testid="stHeader"], 
            [data-testid="stToolbar"], [data-testid="stChatInput"], 
            [data-testid="stSelectbox"], button { 
                display: none !important; 
            }
            
            .block-container { 
                max-width: 100% !important; 
                width: 100% !important; 
                padding: 0 !important; 
                margin: 0 !important; 
            }
            
            .kpi-card { page-break-inside: avoid !important; }
            canvas { max-width: 100% !important; height: auto !important; }
        }
        </style>
    """, unsafe_allow_html=True)

    # Sidebar Logo Logic Fallback
    try:
        col1, col2, col3 = st.sidebar.columns([1, 2, 1])
        with col2:
            st.image("analytics_2471711.png", use_column_width=True)
    except Exception:
        st.sidebar.image("analytics_2471711.png", width=150)
        
    st.sidebar.markdown("---")
    
    status_classes = {
        "Opener": "solid-gray", "Pacer": "solid-gray", 
        "Wicket Keeper": "solid-gray", "All-Rounder": "solid-gray", "Captain": "solid-gray"
    }

    if "agent_state" in st.session_state and st.session_state.agent_state:
        current_status = st.session_state.agent_state["status"]
        if current_status in ["processing", "needs_clarification"]:
            status_classes["Opener"] = "blink-green"
        elif current_status in ["ready_for_sql", "sql_failed"]:
            status_classes["Opener"] = "solid-green"
            status_classes["Pacer"] = "blink-green"
        elif current_status == "auditing":
            status_classes["Opener"] = "solid-green"
            status_classes["Pacer"] = "solid-green"
            status_classes["Wicket Keeper"] = "blink-green"
        elif current_status == "ready_for_captain":
            status_classes["Opener"] = "solid-green"
            status_classes["Pacer"] = "solid-green"
            status_classes["Wicket Keeper"] = "solid-green"
            status_classes["All-Rounder"] = "blink-green" 
        elif current_status == "complete":
            for k in status_classes:
                status_classes[k] = "solid-green"

    st.sidebar.markdown("<h3 style='text-align: center;'>⚙️ Engine Status</h3>", unsafe_allow_html=True)
    
    status_html = f"""
    <div style="display: flex; justify-content: center; width: 100%;">
        <div style="display: flex; flex-direction: column; align-items: flex-start;">
            <div style="display: flex; align-items: center; margin-bottom: 10px;">
                <span class='{status_classes['Opener']}'>●</span>
                <span class='status-text'>The Opener</span>
            </div>
            <div style="display: flex; align-items: center; margin-bottom: 10px;">
                <span class='{status_classes['Pacer']}'>●</span>
                <span class='status-text'>The Pacer</span>
            </div>
            <div style="display: flex; align-items: center; margin-bottom: 10px;">
                <span class='{status_classes['Wicket Keeper']}'>●</span>
                <span class='status-text'>Wicket Keeper</span>
            </div>
            <div style="display: flex; align-items: center; margin-bottom: 10px;">
                <span class='{status_classes['All-Rounder']}'>●</span>
                <span class='status-text'>All-Rounder</span>
            </div>
            <div style="display: flex; align-items: center; margin-bottom: 10px;">
                <span class='{status_classes['Captain']}'>●</span>
                <span class='status-text'>The Captain</span>
            </div>
        </div>
    </div>
    """
    st.sidebar.markdown(status_html, unsafe_allow_html=True)
    st.sidebar.markdown("---")
    st.title("The Playing XI: Insights Engine")

    st.markdown("### 🔍 Ask The Playing XI")
    
    sample_prompts = [
        "Select a sample question or type your own...",
        "Show me MQL funnel metrics for Q4 2025",
        "Show me SMB funnel metrics for Q4 2025",
        "Compare MQL vs SMB weekly lead trends for Q4 2025",
        "Compare MQL funnel metrics between production and redesigned views for Q4 2025",
        "Show me top 10 MQL demand campaigns by WON ARR"
    ]
    
    selected_prompt = st.selectbox("Sample Questions", options=sample_prompts, label_visibility="collapsed")
    custom_query = st.chat_input("Or type your custom campaign question here...")
    
    query = None
    if custom_query:
        query = custom_query
    elif selected_prompt != sample_prompts[0]:
        if st.button("▶ Run Selected Query", type="primary"):
            query = selected_prompt

    if query:
        initial_state = {"user_query": query, "retry_count": 0, "status": "processing"}
        st.session_state.agent_state = app_graph.invoke(initial_state)
        st.rerun()

    if "agent_state" in st.session_state and st.session_state.agent_state:
        state = st.session_state.agent_state
        
        if state["status"] == "needs_clarification":
            st.warning("⚠️ Clarification Required")
            st.markdown(f"**{state['clarification_request']['prompt']}**")
            choice = st.radio("Select:", state['clarification_request']['options'])
            if st.button("Apply & Execute"):
                state["intent_map"]["filters"] = f"Team_Type = '{choice}'"
                state["status"] = "ready_for_sql"
                st.session_state.agent_state = app_graph.invoke(state)
                st.rerun()

        elif state["status"] == "complete":
            payload = state["final_payload"]
            if "error" in payload:
                st.error(payload["error"])
            else:
                st.markdown("---")
                
                kpi_cols = st.columns(4)
                for idx, kpi in enumerate(payload["kpis"]):
                    with kpi_cols[idx]:
                        delta_class = "delta-high" if "high" in kpi['delta'].lower() else "delta-low"
                        arrow = "↑" if "high" in kpi['delta'].lower() else "↓"
                        st.markdown(f"""
                        <div class="kpi-card">
                            <div class="kpi-icon">{kpi['icon']}</div>
                            <div class="kpi-label">{kpi['label']}</div>
                            <div class="kpi-val">{kpi['value']}</div>
                            <div class="kpi-delta {delta_class}">{arrow} {kpi['delta']}</div>
                        </div>
                        """, unsafe_allow_html=True)
                
                st.markdown("<br>", unsafe_allow_html=True)
                
                st.markdown(f"#### {payload.get('chart_title', 'Weekly Lead Trends (K)')}")
                chart_df = pd.DataFrame(payload["chart_data"], index=payload["chart_index"])
                
                if payload.get("chart_type") == "line":
                    st.line_chart(chart_df, height=350)
                else:
                    st.bar_chart(chart_df, height=350)
                    
                st.markdown("<br>", unsafe_allow_html=True)

                r1c1, r1c2, r1c3 = st.columns(3)
                with r1c1:
                    st.markdown("### 📝 Executive Summary")
                    for item in payload["insights_grid"]["Executive Summary"]: st.markdown(f"- {item}")
                with r1c2:
                    st.markdown("### 📈 Trend Analysis")
                    for item in payload["insights_grid"]["Trend Analysis"]: st.markdown(f"- {item}")
                with r1c3:
                    st.markdown("### 💡 Key Insights")
                    for item in payload["insights_grid"]["Key Insights"]: st.markdown(f"- {item}")
                
                st.markdown("<br>", unsafe_allow_html=True)
                
                r2c1, r2c2, r2c3 = st.columns(3)
                with r2c1:
                    st.markdown("### 🚀 Growth Insights")
                    for item in payload["insights_grid"]["Growth Insights"]: st.markdown(f"- {item}")
                with r2c2:
                    st.markdown("### ⚖️ Volatility")
                    for item in payload["insights_grid"]["Volatility"]: st.markdown(f"- {item}")
                with r2c3:
                    st.markdown("### 🎯 Promotional Correlation")
                    for item in payload["insights_grid"]["Promotional Correlation"]: st.markdown(f"- {item}")

                st.markdown("---")

                with st.expander("📝 View Generated SQL"):
                    st.code(payload["sql"], language="sql")
                    st.download_button(
                        label="⬇️ Download SQL Query (.sql)",
                        data=payload["sql"],
                        file_name="CD_HK_Generated_Query.sql",
                        mime="text/plain"
                    )

                with st.expander("📊 View Raw Data Table"):
                    st.dataframe(payload["data"], use_container_width=True)

if __name__ == "__main__":
    main()