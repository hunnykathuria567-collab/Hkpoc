import os
import pandas as pd
import requests
import json
from datetime import datetime

# --- 1. SECRETS ---
SERPER_API_KEY = os.getenv("SERPER_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def get_unique_15day_leads():
    url = "https://google.serper.dev/search"
    # DIVERSIFIED QUERIES: Targeting different sectors to hit 1,000+ unique potential
    queries = [
        "L1 bidder construction Delhi NCR wins 2026",
        "SME manufacturing expansion Noida 2026",
        "Solar EPC order India March 2026",
        "NCLT settlement stay Delhi SME 2026",
        "UPIDC industrial allotment list 2026"
    ]
    
    unique_pool = {}
    for q in queries:
        # Pushing num to 100 to maximize volume
        payload = json.dumps({"q": q, "num": 100, "tbs": "qdr:m"})
        headers = {'X-API-KEY': SERPER_API_KEY, 'Content-Type': 'application/json'}
        try:
            res = requests.post(url, headers=headers, data=payload).json()
            for item in res.get('organic', []):
                title = item.get('title', 'Unknown')
                # ENTITY RESOLUTION: Normalize name to first 2 words to kill headline repeats
                norm_name = " ".join(title.split()[:2]).lower().strip()
                if norm_name not in unique_pool:
                    unique_pool[norm_name] = item
        except: continue
    return list(unique_pool.values())

# --- 2. THE STRIKE TEAM MAPPING ---
raw_data = get_unique_15day_leads()
final_leads = []

for item in raw_data:
    title = item.get('title')
    # Hardcoded Gold Data for the 'Whales'
    kdm_map = {
        "globe civil": ("Ved Khurana (Chairman)", "Vineet Rattan (CS)", "Vipul Khurana (Dir)", "+91-11-46561560"),
        "saatvik": ("Abani Jha (CFO)", "Bhagya Hasija (CS)", "Prashant Mathur (CEO)", "0124-3626755"),
        "alpex solar": ("L K Dhamija (VP Fin)", "Arun Singh (GM)", "Ashwani Sehgal (MD)", "+91-120-2341146"),
        "addverb": ("Ashu Kansal (CFO)", "Divya Wadhawan (CS)", "Sangeet Kumar (Founder)", "0120-6915100")
    }
    
    # Check for match in our Gold Map
    norm_check = " ".join(title.split()[:2]).lower().strip()
    c1, c2, c3, phone = kdm_map.get(norm_check, ("Researching CFO", "Researching CS", "Researching MD", "Checking Desk Line"))

    final_leads.append({
        "Entity": title,
        "Contact 1": c1, "Contact 2": c2, "Contact 3": c3,
        "Desk Number": phone,
        "Intent Signal": item.get('snippet'),
        "Source": item.get('link'),
        "Published_Date": item.get('date', datetime.now().strftime("%Y-%m-%d"))
    })

# --- 3. EXPORT & TELEGRAM ---
df = pd.DataFrame(final_leads)
output_file = "Agent_L_Master.xlsx"
df.to_excel(output_file, index=False)

# Telegram sendDocument logic
url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendDocument"
with open(output_file, 'rb') as f:
    requests.post(url, data={'chat_id': TELEGRAM_CHAT_ID}, files={'document': f})
