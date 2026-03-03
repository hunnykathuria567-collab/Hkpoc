import os
import pandas as pd
import requests
import json
import time
from datetime import datetime
import google.generativeai as genai

# --- 1. ARCHITECT SECRETS ---
SERPER_API_KEY = os.getenv("SERPER_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
llm_model = genai.GenerativeModel('gemini-2.5-flash')

def search_web(query, num=10, tbs="qdr:m"):
    url = "https://google.serper.dev/search"
    payload = json.dumps({"q": query, "num": num, "tbs": tbs})
    headers = {'X-API-KEY': SERPER_API_KEY, 'Content-Type': 'application/json'}
    try:
        res = requests.post(url, headers=headers, data=payload)
        return res.json().get('organic', [])
    except:
        return []

def clean_json_response(text):
    """Strips markdown and forces the LLM output into a dictionary."""
    try:
        clean_text = text.replace('```json', '').replace('```', '').strip()
        return json.loads(clean_text)
    except json.JSONDecodeError:
        return None

def extract_entity_with_llm(headline, snippet):
    """Forces Gemini to return ONLY a JSON object."""
    prompt = f"""
    Analyze this news snippet. If it's about a specific company winning a project or expanding, extract the core company name. 
    If it's just a general industry report, government news, or you cannot find a specific company, return "INVALID".
    Headline: {headline}
    Snippet: {snippet}
    
    You MUST return ONLY a valid JSON object in this exact format, with no other text:
    {{"company": "Extracted Name or INVALID"}}
    """
    try:
        response = llm_model.generate_content(prompt)
        parsed = clean_json_response(response.text)
        if parsed and parsed.get("company") != "INVALID":
            return parsed.get("company").strip()
        return None
    except:
        return None

def hunt_kdm_with_llm(company_name):
    """Forces strict JSON parsing for the LinkedIn hunt."""
    query = f"site:linkedin.com/in/ \"{company_name}\" (CFO OR \"Head of Finance\" OR \"Director Finance\")"
    results = search_web(query, num=3, tbs="")
    
    if not results:
        return "Manual Research", "N/A", "N/A"
        
    context = "\n".join([f"Title: {r.get('title')} | Link: {r.get('link')}" for r in results])
    
    prompt = f"""
    Analyze these LinkedIn search results for '{company_name}'. Find the best match for the Finance Leader/CFO.
    
    You MUST return ONLY a valid JSON object in this exact format. If no human is found, use "N/A" for all values.
    {{"name": "Person Name", "title": "Exact Job Title", "url": "LinkedIn URL"}}
    
    Data:
    {context}
    """
    try:
        response = llm_model.generate_content(prompt)
        parsed = clean_json_response(response.text)
        if parsed:
            return parsed.get("name", "N/A"), parsed.get("title", "N/A"), parsed.get("url", "N/A")
        return "Parsing Failed", "N/A", "N/A"
    except:
        return "LLM Error", "N/A", "N/A"

def execute_agent_p_pipeline():
    print("🚀 Initializing Agent P V14.0 (JSON-Enforced)...")
    
    queries = [
        "L1 bidder construction Delhi NCR 2026", 
        "SME manufacturing Noida factory expansion 2026",
        "Solar EPC India 2026"
    ]
    
    raw_signals = []
    for q in queries:
        raw_signals.extend(search_web(q, num=15))
        
    processed_entities = set()
    final_database = []
    
    for item in raw_signals:
        headline = item.get('title', '')
        snippet = item.get('snippet', '')
        url = item.get('link', '')
        
        # 1. Clean the Entity
        clean_company = extract_entity_with_llm(headline, snippet)
        
        # Skip garbage, Wikipedia, government portals, or duplicates
        if not clean_company or clean_company.lower() in processed_entities or len(clean_company) < 3:
            continue
            
        processed_entities.add(clean_company.lower())
        print(f"✅ Verified Target: {clean_company}. Hunting KDMs...")
        
        # 2. Hunt the KDM
        kdm_name, kdm_title, kdm_link = hunt_kdm_with_llm(clean_company)
        
        final_database.append({
            "Clean Entity": clean_company,
            "KDM Name": kdm_name,
            "KDM Title": kdm_title,
            "LinkedIn Profile": kdm_link,
            "Intent Signal": snippet,
            "Source URL": url,
            "Date": item.get('date', datetime.now().strftime("%Y-%m-%d"))
        })
        time.sleep(1.5) # Prevent LLM throttling

    df = pd.DataFrame(final_database)
    output_file = "Agent_P_JSON_Intelligence.xlsx"
    df.to_excel(output_file, index=False)
    
    with open(output_file, 'rb') as f:
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendDocument", 
                      data={'chat_id': TELEGRAM_CHAT_ID}, files={'document': f})
    print(f"📦 Pipeline Complete. {len(df)} heavily enriched leads delivered.")

execute_agent_p_pipeline()
