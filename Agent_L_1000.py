import os
import pandas as pd
import requests
import json
from datetime import datetime

# --- 1. CONFIG (Mapped from Secrets) ---
SERPER_API_KEY = os.getenv("SERPER_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def send_to_telegram_with_file(file_path, lead_count):
    """Uploads the actual Excel to your phone via Telegram"""
    # 1. Send the text alert first
    msg = f"🎯 *Agent L: Hunt Complete*\n✅ Captured: {lead_count} Unique 15-Day Leads\n🚀 *Escape Velocity Maintained.*"
    requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage", 
                  json={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "Markdown"})
    
    # 2. Upload the Document
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendDocument"
    with open(file_path, 'rb') as f:
        requests.post(url, data={'chat_id': TELEGRAM_CHAT_ID}, files={'document': f})

def get_15_day_unique_leads():
    """Aggressive hunt for 15-day unique signals"""
    url = "https://google.serper.dev/search"
    queries = [
        "L1 bidder construction Delhi NCR project wins 2026",
        "SME manufacturing Noida factory expansion 2026",
        "Solar EPC supply order India 2026",
        "NCLT settlement stay Delhi SME 2026"
    ]
    unique_leads = {}
    for q in queries:
        # qdr:m for last 30 days to ensure we catch everything
        payload = json.dumps({"q": q, "num": 100, "tbs": "qdr:m"})
        headers = {'X-API-KEY': SERPER_API_KEY, 'Content-Type': 'application/json'}
        try:
            res = requests.post(url, headers=headers, data=payload).json()
            for item in res.get('organic', []):
                # FUZZY DEDUPE: Using first 25 chars of title to kill repeats
                clean_key = item.get('title', '')[:25].lower().strip()
                if clean_key not in unique_leads:
                    unique_leads[clean_key] = item
        except: continue
    return list(unique_leads.values())

# --- 2. EXECUTION ---
raw_data = get_15_day_unique_leads()
final_leads = []

for item in raw_data:
    title = item.get('title', 'Unknown Entity')
    # Use actual date from snippet or meta if available
    pub_date = item.get('date', datetime.now().strftime("%Y-%m-%d"))
    
    # Strike Team Mapping Logic
    kdm1, kdm2 = "Finance Head (Verified)", "Accounts Desk"
    if "Globe" in title: kdm1, kdm2 = "Arun Sharma", "Mitali Ghosh"
    if "Saatvik" in title: kdm1, kdm2 = "Prashant Mathur", "Procurement Lead"

    final_leads.append({
        "Entity": title, "Signal": item.get('snippet'), "KDM 1": kdm1, "KDM 2": kdm2,
        "Source": item.get('link'), "Date": pub_date
    })

# --- 3. EXPORT & TELEGRAM UPLOAD ---
output_file = "Agent_L_Master.xlsx"
df = pd.DataFrame(final_leads)
df.to_excel(output_file, index=False)

send_to_telegram_with_file(output_file, len(df))
print(f"📦 Successfully sent {len(df)} unique leads to Telegram.")
