import os
import pandas as pd
import requests
import json
from datetime import datetime

# --- 1. ARCHITECT SECRETS ---
SERPER_API_KEY = os.getenv("SERPER_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def find_premium_targets(company_name):
    """Targets high-level KDMs for Premium InMail outreach"""
    url = "https://google.serper.dev/search"
    # Specific dork to find 'Open' or 'Premium' looking profiles for top Finance KDMs
    query = f"site:linkedin.com/in/ '{company_name}' (CFO OR 'Finance Director' OR 'VP Finance')"
    headers = {'X-API-KEY': SERPER_API_KEY, 'Content-Type': 'application/json'}
    payload = json.dumps({"q": query, "num": 5})
    
    try:
        res = requests.post(url, headers=headers, data=payload).json()
        results = res.get('organic', [])
        
        target_list = []
        for r in results[:3]: # Getting top 3 for better choice
            name_title = r.get('title', 'Unknown').split(' - ')[0]
            link = r.get('link', 'No Link')
            target_list.append(f"{name_title} | URL: {link}")
            
        return target_list if target_list else ["Target Not Found", "", ""]
    except:
        return ["Search Error", "", ""]

def run_v9_1_premium_sniper():
    """The Final Monday Morning Pipeline: Signal -> Premium Target Discovery"""
    print("🚀 Initializing V9.1 Premium-Enhanced Sniper...")
    search_url = "https://google.serper.dev/search"
    queries = ["L1 bidder construction Delhi NCR 2026", "SME Noida factory expansion 2026", "Solar EPC India 2026"]
    
    unique_signals = {}
    for q in queries:
        payload = json.dumps({"q": q, "num": 50, "tbs": "qdr:m"})
        res = requests.post(search_url, headers={'X-API-KEY': SERPER_API_KEY}, data=payload).json()
        for item in res.get('organic', []):
            title = item.get('title', '')
            entity = title.split(' wins')[0].split(' secures')[0].split(' emerges')[0].strip()
            if entity.lower() not in unique_signals:
                unique_signals[entity.lower()] = {"name": entity, "item": item}

    final_leads = []
    for company_id, data in unique_signals.items():
        # DYNAMIC SEARCH FOR PREMIUM INMAIL TARGETS
        targets = find_premium_targets(data['name'])
        
        # Ensure we have 3 slots for Column consistency
        while len(targets) < 3: targets.append("N/A")
        
        final_leads.append({
            "Entity": data['name'],
            "InMail Target 1": targets[0],
            "InMail Target 2": targets[1],
            "InMail Target 3": targets[2],
            "Intent Signal": data['item'].get('snippet'),
            "Source News": data['item'].get('link')
        })

    # --- 2. EXPORT & DELIVERY ---
    df = pd.DataFrame(final_leads)
    df.to_excel("Agent_L_Premium_StrikeList.xlsx", index=False)
    
    with open("Agent_L_Premium_StrikeList.xlsx", 'rb') as f:
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendDocument", 
                      data={'chat_id': TELEGRAM_CHAT_ID}, files={'document': f})

run_v9_1_premium_sniper()
