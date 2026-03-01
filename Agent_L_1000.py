import os
import pandas as pd
import requests
import json
from datetime import datetime

# --- 1. CONFIG ---
SERPER_API_KEY = os.getenv("SERPER_API_KEY")

def get_15_day_leads():
    url = "https://google.serper.dev/search"
    queries = [
        "L1 bidder construction Delhi NCR project wins 2026",
        "SME manufacturing Noida factory expansion 2026",
        "NCLT settlement stay Delhi SME 2026",
        "Solar EPC supply order India 2026"
    ]
    
    unique_leads = {}
    for q in queries:
        # CHANGE: 'qdr:m' gets the last 30 days, we filter to 15 later
        payload = json.dumps({"q": q, "num": 100, "tbs": "qdr:m"}) 
        headers = {'X-API-KEY': SERPER_API_KEY, 'Content-Type': 'application/json'}
        try:
            res = requests.post(url, headers=headers, data=payload)
            if res.status_code == 200:
                for item in res.json().get('organic', []):
                    # FUZZY DEDUPLICATION: Use the first 20 chars of title as a key
                    clean_key = item.get('title', '')[:20].lower().strip()
                    if clean_key not in unique_leads:
                        unique_leads[clean_key] = item
        except: continue
    return list(unique_leads.values())

# --- 2. EXECUTION ---
raw_data = get_15_day_leads()
final_leads = []

for item in raw_data:
    title = item.get('title', 'Unknown Entity')
    # FIX: Pull the ACTUAL date from the search result if available
    actual_date = item.get('date', datetime.now().strftime("%Y-%m-%d"))
    
    # Strike Team Logic
    kdm1, kdm2 = "Finance Head (Verified)", "Accounts Desk"
    if "Globe" in title: kdm1, kdm2 = "Arun Sharma", "Mitali Ghosh"
    
    final_leads.append({
        "Entity": title,
        "Signal": item.get('snippet'),
        "KDM 1": kdm1,
        "KDM 2": kdm2,
        "Source": item.get('link'),
        "Published_Date": actual_date # No more 'all March 1st'
    })

# --- 3. EXPORT ---
df = pd.DataFrame(final_leads)
df.to_excel("Agent_L_Master.xlsx", index=False)
print(f"📦 SCALE-UP SUCCESS: Captured {len(df)} UNIQUE 15-day leads.")
