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

# Initialize the NLP Engine 
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
llm_model = genai.GenerativeModel('gemini-2.5-flash')

def search_web(query, num=10, tbs="qdr:m"):
    """Core Serper API Call"""
    url = "https://google.serper.dev/search"
    payload = json.dumps({"q": query, "num": num, "tbs": tbs})
    headers = {'X-API-KEY': SERPER_API_KEY, 'Content-Type': 'application/json'}
    try:
        res = requests.post(url, headers=headers, data=payload)
        return res.json().get('organic', [])
    except:
        return []

def extract_entity_with_llm(headline, snippet):
    """Uses Gemini to intelligently extract JUST the company name, ignoring the noise."""
    prompt = f"""
    Extract ONLY the core Company Name from this news headline and snippet. 
    Ignore project details, monetary values, and extra words.
    Headline: {headline}
    Snippet: {snippet}
    Return strictly the company name and nothing else.
    """
    try:
        response = llm_model.generate_content(prompt)
        return response.text.strip().replace('*', '').replace('"', '')
    except:
        return headline[:20]

def hunt_kdm_with_llm(company_name):
    """Searches LinkedIn specifically and uses Gemini to find the actual human."""
    # Strict dorking for LinkedIn Profiles only
    query = f"site:linkedin.com/in/ \"{company_name}\" (CFO OR \"Head of Finance\" OR \"Director Finance\")"
    results = search_web(query, num=3, tbs="")
    
    if not results:
        return "No LinkedIn Profile Found", "N/A", "N/A"
        
    # Combine top results for the LLM to read
    context = "\n".join([f"Title: {r.get('title')} | Link: {r.get('link')} | Snippet: {r.get('snippet')}" for r in results])
    
    prompt = f"""
    You are an executive researcher. Read the following LinkedIn search results for the company '{company_name}'.
    Identify the best human match for the Finance Leader/CFO.
    Return the result strictly in this format: 
    Name | Exact Job Title | LinkedIn URL
    If no clear human name is found, return: "Manual Research Needed | N/A | N/A"
    
    Data:
    {context}
    """
    try:
        response = llm_model.generate_content(prompt)
        ans = response.text.strip().split('|')
        if len(ans) >= 3:
            return ans[0].strip(), ans[1].strip(), ans[2].strip()
        return ans[0], "Title Unknown", "Link Unknown"
    except:
        return "LLM Parsing Error", "N/A", "N/A"

def execute_agent_p_pipeline():
    print("🚀 Initializing Agent P (NLP-to-Insights Pipeline)...")
    
    # --- PHASE 1: SIGNAL ACQUISITION ---
    queries = [
        "L1 bidder construction Delhi NCR 2026", 
        "SME manufacturing Noida factory expansion 2026",
        "Solar EPC India 2026"
    ]
    
    raw_signals = []
    for q in queries:
        raw_signals.extend(search_web(q, num=15)) # Kept to 15 per query to respect LLM rate limits
        
    # --- PHASE 2: NLP PROCESSING ---
    processed_entities = set()
    final_database = []
    
    for item in raw_signals:
        headline = item.get('title', '')
        snippet = item.get('snippet', '')
        url = item.get('link', '')
        
        # 1. Clean the Entity
        clean_company = extract_entity_with_llm(headline, snippet)
        
        # Deduplication based on LLM's clean output
        if clean_company.lower() in processed_entities or len(clean_company) < 3:
            continue
            
        processed_entities.add(clean_company.lower())
        print(f"🔍 NLP Extracted Target: {clean_company}. Hunting KDMs...")
        
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
        time.sleep(1) # Prevent LLM API throttling

    # --- PHASE 3: DELIVERY ---
    df = pd.DataFrame(final_database)
    output_file = "Agent_P_Intelligence.xlsx"
    df.to_excel(output_file, index=False)
    
    with open(output_file, 'rb') as f:
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendDocument", 
                      data={'chat_id': TELEGRAM_CHAT_ID}, files={'document': f})
    print(f"📦 Pipeline Complete. {len(df)} heavily enriched leads delivered.")

execute_agent_p_pipeline()
