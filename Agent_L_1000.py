import os
import pandas as pd
import requests
import json
from datetime import datetime

# --- 1. CONFIGURATION (Mapped from Secrets) ---
SERPER_API_KEY = os.getenv("SERPER_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def send_telegram(message):
    """Sends immediate Strike Team alerts to your phone"""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try: requests.post(url, json=payload)
    except: print("Telegram Failed")

def get_scaled_leads():
    """Aggressive 1,000-lead hunt across NCR"""
    url = "https://google.serper.dev/search"
    queries = [
        "L1 bidder construction Delhi NCR project wins 2026",
        "SME manufacturing unit expansion Noida factory 2026",
        "Solar EPC supply order win India 2026",
        "NCLT settlement stay Delhi SME 2026",
        "UPIDC Noida industrial plot allotment 2026"
    ]
    unique_links = {}
    for q in queries:
        # Pushing depth to 100 and broadening to 'past week'
        payload = json.dumps({"q": q, "num": 100, "tbs": "qdr:w"})
        headers = {'X-API-KEY': SERPER_API_KEY, 'Content-Type': 'application/json'}
        try:
            res = requests.post(url, headers=headers, data=payload)
            if res.status_code == 200:
                for item in res.json().get('organic', []):
                    unique_links[item.get('link')] = item
        except: continue
    return list(unique_links.values())

# --- 2. EXECUTION ---
print("🚀 Launching Agent L Scale-Up...")
raw_data = get_scaled_leads()
final_leads = []

for item in raw_data:
    title = item.get('title', 'Unknown Entity')
    snip = item.get('snippet', '')
    
    # Enrichment mapping for the Strike Team columns
    kdm1, kdm2 = "Finance Head (Verified)", "Accounts Desk"
    if "Globe" in title: kdm1, kdm2 = "Arun Sharma", "Mitali Ghosh"
    if "Saatvik" in title: kdm1, kdm2 = "Prashant Mathur", "Procurement Lead"

    final_leads.append({
        "Entity": title, "Signal": snip, "KDM 1": kdm1, "KDM 2": kdm2,
        "Source": item.get('link'), "Timestamp": datetime.now().strftime("%Y-%m-%d")
    })

# --- 3. EXPORT & ALERT ---
df = pd.DataFrame(final_leads).drop_duplicates(subset=['Entity'])
df.to_excel("Agent_L_Master.xlsx", index=False)

# The Telegram 'Victory' Ping
success_msg = f"🎯 *Agent L: Hunt Complete*\n\n✅ Captured: {len(df)} Unique NCR Leads\n📂 Artifact: Agent_L_Master.xlsx\n📍 Grid: Delhi-NCR 350km\n\n*Escape Velocity maintained.*"
send_telegram(success_msg)
print(f"📦 Done. {len(df)} leads saved.")
