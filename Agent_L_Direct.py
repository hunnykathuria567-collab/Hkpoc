import os
import json
import csv
import requests
from google import genai
from pydantic import BaseModel, Field

# --- SCHEMAS ---
class CompanySignal(BaseModel):
    name: str
    signal: str
    source: str

class SignalList(BaseModel):
    companies: list[CompanySignal]

class FinanceContact(BaseModel):
    role: str
    name: str
    phone: str
    email: str

class EnrichedLead(BaseModel):
    company_name: str
    strike_team: list[FinanceContact]
    address: str
    capital_need: str
    the_play: str
    source_link: str

# -------------------------------------------------------------------
# PHASE 1: MULTI-STREAM SCAN (3 SEPARATE QUERIES)
# -------------------------------------------------------------------
def get_company_signals():
    api_key = os.environ.get("SERPER_API_KEY")
    url = "https://google.serper.dev/search"
    
    # We run 3 simple queries to avoid "Empty Result" errors
    queries = [
        "\"Pvt Ltd\" wins contract Delhi NCR",
        "\"Pvt Ltd\" NCLT Delhi petition 2026",
        "\"Pvt Ltd\" factory expansion Haryana Punjab"
    ]
    
    all_snippets = []
    print(f"🌍 Phase 1: Running {len(queries)} stream scan...")
    
    for q in queries:
        try:
            res = requests.post(url, headers={'X-API-KEY': api_key, 'Content-Type': 'application/json'}, 
                                json={"q": q, "num": 20, "tbs": "qdr:m"})
            all_snippets.extend([f"Co: {r.get('title')} | Snip: {r.get('snippet')} | Link: {r.get('link')}" for r in res.json().get('organic', [])])
        except Exception: continue

    if not all_snippets: return []

    client = genai.Client()
    prompt = f"Identify the top 10 companies from these snippets involved in >1Cr expansions, orders, or NCLT distress. Snippets:\n" + "\n".join(all_snippets)
    try:
        ai_res = client.models.generate_content(model='gemini-2.5-flash', contents=prompt, config=genai.types.GenerateContentConfig(response_mime_type="application/json", response_schema=SignalList))
        return json.loads(ai_res.text).get("companies", [])
    except Exception: return []

# -------------------------------------------------------------------
# PHASE 2: FINANCE STRIKE TEAM DEEP DIVE
# -------------------------------------------------------------------
def enrich_company(co_data):
    api_key = os.environ.get("SERPER_API_KEY")
    co_name = co_data['name']
    print(f"   🎯 Phase 2: Sniper-searching Finance Team for {co_name}...")
    
    url = "https://google.serper.dev/search"
    payload = json.dumps({"q": f'"{co_name}" (CFO OR Accountant OR "Finance Manager") (contact OR phone OR email)', "num": 10})
    
    try:
        res = requests.post(url, headers={'X-API-KEY': api_key, 'Content-Type': 'application/json'}, data=payload)
        deep_text = "\n".join([r.get('snippet') for r in res.json().get('organic', [])])
        
        client = genai.Client()
        prompt = f"Extract a 'Strike Team' (CFO, Accountant, Finance Lead) for {co_name}. Use 'Not Listed' if missing. Results:\n{deep_text}"
        ai_res = client.models.generate_content(model='gemini-2.5-flash', contents=prompt, config=genai.types.GenerateContentConfig(response_mime_type="application/json", response_schema=EnrichedLead))
        result = json.loads(ai_res.text)
        result['source_link'] = co_data['source'] # Ensure source link is passed
        return result
    except Exception: return None

# -------------------------------------------------------------------
# DELIVERY
# -------------------------------------------------------------------
def push_to_telegram(lead):
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not lead: return
    
    team_msg = ""
    for member in lead.get('strike_team', []):
        team_msg += f"👤 *{member['role']}:* {member['name']}\n📞 {member['phone']}\n\n"

    msg = (
        f"🏦 *AGENT L: STRIKE TEAM TARGET* 🏦\n"
        f"🏢 *Company:* {lead['company_name']}\n\n"
        f"🎯 *CONTACTS:*\n{team_msg}"
        f"💰 *Need:* {lead['capital_need']}\n"
        f"♟️ *The Play:* {lead['the_play']}\n\n"
        f"🔗 *Source:* {lead['source_link']}"
    )
    requests.post(f"https://api.telegram.org/bot{bot_token}/sendMessage", json={"chat_id": chat_id, "text": msg, "parse_mode": "Markdown"})

if __name__ == "__main__":
    signals = get_company_signals()
    if signals:
        for co in signals[:8]:
            full_lead = enrich_company(co)
            if full_lead:
                push_to_telegram(full_lead)
    else:
        # Simple heartbeat if nothing found
        requests.post(f"https://api.telegram.org/bot{os.environ.get('TELEGRAM_BOT_TOKEN')}/sendMessage", 
                      json={"chat_id": os.environ.get('TELEGRAM_CHAT_ID'), "text": "🟢 *AGENT L: SYSTEM ACTIVE*\nNo high-intent targets found in the last 24 hours."})
