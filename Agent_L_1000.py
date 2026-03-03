import os
import pandas as pd
import requests
import json
import time
from datetime import datetime
import google.generativeai as genai

# --- 1. SECRETS ---
SERPER_API_KEY = os.getenv("SERPER_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

# THE UPGRADE: System Instructions force the LLM to act as a strict binary filter
sys_prompt = """
You are a strict financial data extraction API. 
1. Your ONLY job is to extract the specific PRIVATE COMPANY name winning a project, contract, or expanding.
2. If the text is about government policies, Union Budgets, PM Modi, Wikipedia, generalized industry growth, or generic 'SMEs', you MUST return "NONE".
3. Only output valid JSON. No conversational text.
"""

llm_model = genai.GenerativeModel(
    'gemini-2.5-flash', 
    generation_config={"response_mime_type": "application/json"},
    system_instruction=sys_prompt
)

def search_web(query, num=15, tbs="qdr:m"):
    url = "https://google.serper.dev/search"
    payload = json.dumps({"q": query, "num": num, "tbs": tbs})
    headers = {'X-API-KEY': SERPER_API_KEY, 'Content-Type': 'application/json'}
    try:
        return requests.post(url, headers=headers, data=payload).json().get('organic', [])
    except: return []

def extract_entity_with_llm(headline, snippet):
    prompt = f"""
    Headline: {headline}
    Snippet: {snippet}
    Return exactly this JSON: {{"company": "Clean Name or NONE"}}
    """
    try:
        res = json.loads(llm_model.generate_content(prompt).text)
        return res.get("company", "NONE")
    except: return "NONE"

def hunt_kdm_with_llm(company_name):
    query = f"site:linkedin.com/in/ \"{company_name}\" (CFO OR \"Head of Finance\" OR \"Director\")"
    results = search_web(query, num=3, tbs="")
    if not results: return "Manual Search Required", "N/A", "N/A"
        
    context = "\n".join([f"Title: {r.get('title')} | Link: {r.get('link')}" for r in results])
    prompt = f"""
    Find the Finance Leader/CFO from these LinkedIn results for '{company_name}'.
    Return exactly this JSON: {{"name": "Person Name or NONE", "title": "Job Title or NONE", "url": "URL or NONE"}}
    Data: {context}
    """
    try:
        data = json.loads(llm_model.generate_content(prompt).text)
        return data.get("name", "NONE"), data.get("title", "NONE"), data.get("url", "NONE")
    except: return "LLM Error", "N/A", "N/A"

def execute_agent_p():
    print("🚀 Initializing Agent P V17.0 (Zero-Tolerance Gatekeeper)...")
    queries = ["L1 bidder construction Delhi NCR 2026", "SME Noida factory expansion 2026", "Solar EPC India 2026"]
    
    raw_signals = []
    for q in queries: raw_signals.extend(search_web(q))
        
    processed = set()
    final_db = []
    
    for item in raw_signals:
        headline = item.get('title', '')
        snippet = item.get('snippet', '')
        
        # 1. AI Gatekeeper Evaluation
        company = extract_entity_with_llm(headline, snippet)
        
        # 2. ZERO FALLBACKS. If it says NONE, INVALID, or is empty, kill the row.
        if not company or company.upper() in ["NONE", "INVALID", "NULL"]:
            continue
            
        # Clean up any trailing LLM artifacts just in case
        company = company.replace('*', '').strip()
            
        if company.lower() in processed or len(company) < 3: continue
        processed.add(company.lower())
        print(f"✅ High-Intent B2B Target Verified: {company}")
        
        # 3. KDM Hunt
        k1, k2, k3 = hunt_kdm_with_llm(company)
        
        final_db.append({
            "Clean Entity": company,
            "KDM Name": k1,
            "KDM Title": k2,
            "LinkedIn Profile": k3,
            "Intent Signal": snippet,
            "Source URL": item.get('link')
        })
        time.sleep(1.5)

    df = pd.DataFrame(final_db)
    print(f"📊 Strike List Finalized: {len(df)} pure corporate leads.")
    df.to_excel("Agent_P_Zero_Tolerance.xlsx", index=False)
    with open("Agent_P_Zero_Tolerance.xlsx", 'rb') as f:
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendDocument", 
                      data={'chat_id': TELEGRAM_CHAT_ID}, files={'document': f})

execute_agent_p()
