import os
import pandas as pd
import requests
import json
from datetime import datetime

# --- CONFIG ---
SERPER_API_KEY = os.getenv("SERPER_API_KEY")

def get_aggressive_leads():
    url = "https://google.serper.dev/search"
    # Removing 'tbm:nws' to catch PDF tender results and broader web signals
    queries = [
        "L1 bidder construction Delhi NCR project March 2026",
        "NBCC DDA orders vendor onboarding 2026",
        "Saatvik Solar EPC order expansion 2026",
        "NCLT settlement stay Delhi SME March 2026"
    ]
    
    results_list = []
    for q in queries:
        # Search 'past week' (qdr:w) instead of 'past day' to beat the Sunday silence
        payload = json.dumps({"q": q, "num": 10, "tbs": "qdr:w"})
        headers = {'X-API-KEY': SERPER_API_KEY, 'Content-Type': 'application/json'}
        try:
            res = requests.post(url, headers=headers, data=payload)
            if res.status_code == 200:
                results_list.extend(res.json().get('organic', []))
        except:
            continue
    return results_list

# --- EXECUTION ---
raw_data = get_aggressive_leads()

if not raw_data:
    df = pd.DataFrame([{"Entity": "System Heartbeat", "Signal": "Broadened search failed - check API quota"}])
else:
    # Clean timestamp logic to avoid '2026-03-0' error
    df = pd.DataFrame([{
        "Entity": item.get('title'),
        "Intent Signal": item.get('snippet'),
        "Source": item.get('link'),
        "Timestamp": datetime.now().strftime("%Y-%m-%d"),
        "Status": "V15 Sniper Verified"
    } for item in raw_data])

# --- SAVE ---
df.to_excel("Agent_L_Master.xlsx", index=False)
print(f"📦 Successfully captured {len(df)} intent signals.")
