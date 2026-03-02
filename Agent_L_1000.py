import os
import pandas as pd
import requests
import json
from datetime import datetime
import re

# --- 1. ARCHITECT SECRETS ---
SERPER_API_KEY = os.getenv("SERPER_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def google_search(query, num=5, tbs=""):
    """Core search utility for recursive hunting"""
    url = "https://google.serper.dev/search"
    headers = {'X-API-KEY': SERPER_API_KEY, 'Content-Type': 'application/json'}
    payload = json.dumps({"q": query, "num": num, "tbs": tbs})
    try:
        res = requests.post(url, headers=headers, data=payload)
        return res.json().get('organic', [])
    except: return []

def find_kdm_contact(company, name):
    """STAGE 3: Recursive loop to find phone/email footprints"""
    # Searching for specific contact strings: 'mobile', 'contact', 'direct', '@company.com'
    query = f'"{name}" "{company}" (mobile OR contact OR "direct dial" OR email)'
    results = google_search(query, num=3)
    
    contacts = []
    for r in results:
        snippet = r.get('snippet', '')
        # Regex to catch Indian mobile patterns or email formats
        phones = re.findall(r'(\+91[\-\s]?)?[6-9]\d{9}', snippet)
        emails = re.findall(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', snippet)
        if phones: contacts.extend(phones)
        if emails: contacts.extend(emails)
    
    return ", ".join(list(set(contacts))) if contacts else "Direct Desk / LinkedIn Only"

def run_v11_recursive_engine():
    """The Autonomous Pipeline: News -> Person -> Contact"""
    print("🚀 Initializing V11.0 Recursive Intelligence Engine...")
    
    # --- STEP 1: SIGNAL ACQUISITION (15-Day Window) ---
    queries = ["L1 bidder construction Delhi NCR 2026", "SME Noida expansion 2026", "Solar EPC India 2026"]
    unique_signals = {}
    for q in queries:
        results = google_search(q, num=50, tbs="qdr:m")
        for item in results:
            title = item.get('title', '')
            # Dynamic Entity Extraction
            entity = title.split(' wins')[0].split(' secures')[0].split(' emerges')[0].strip()
            if entity.lower() not in unique_signals:
                unique_signals[entity.lower()] = {"name": entity, "item": item}

    # --- STEP 2 & 3: PERSON & CONTACT DISCOVERY ---
    final_db = []
    for company_id, data in unique_signals.items():
        comp_name = data['name']
        print(f"🔍 Hunting Strike Team for: {comp_name}")
        
        # Find the Person (KDM)
        person_results = google_search(f"{comp_name} CFO Finance Head LinkedIn 2026", num=2)
        kdm_name = person_results[0].get('title', 'Unknown').split(' - ')[0] if person_results else "N/A"
        kdm_link = person_results[0].get('link', 'N/A') if person_results else "N/A"
        
        # Find the Contact (Third Loop)
        contact_info = "Researching..."
        if kdm_name != "Unknown":
            contact_info = find_kdm_contact(comp_name, kdm_name)
        
        final_db.append({
            "Entity": comp_name,
            "KDM Name": kdm_name,
            "Contact Info (Dynamic)": contact_info, # THE WINNING COLUMN
            "LinkedIn Profile": kdm_link,
            "Intent Signal": data['item'].get('snippet'),
            "Source": data['item'].get('link')
        })

    # --- 4. EXPORT & TELEGRAM ---
    df = pd.DataFrame(final_db)
    df.to_excel("Agent_L_Recursive_Master.xlsx", index=False)
    with open("Agent_L_Recursive_Master.xlsx", 'rb') as f:
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendDocument", 
                      data={'chat_id': TELEGRAM_CHAT_ID}, files={'document': f})

run_v11_recursive_engine()
