import os
import json
import csv
import requests
from google import genai
from pydantic import BaseModel, Field

# --- SCHEMA 1: PHASE 1 (COMPANY IDENTIFICATION) ---
class CompanySignal(BaseModel):
    name: str = Field(description="Name of the company.")
    signal: str = Field(description="Brief reason (e.g., 50Cr expansion, NCLT case).")
    source: str = Field(description="URL of the news/source.")

class SignalList(BaseModel):
    companies: list[CompanySignal]

# --- SCHEMA 2: PHASE 2 (FINANCE STRIKE TEAM ENRICHMENT) ---
class FinanceContact(BaseModel):
    role: str = Field(description="CFO, Accountant, or Finance Lead.")
    name: str = Field(description="Full name or 'Not Listed'.")
    phone: str = Field(description="Direct phone or 'Not Listed'.")
    email: str = Field(description="Direct email or 'Not Listed'.")

class EnrichedLead(BaseModel):
    company_name: str
    strike_team: list[FinanceContact] = Field(description="List of the 3 key finance targets.")
    address: str = Field(description="Registered Office Address.")
    capital_need: str = Field(description="Estimated amount (>1Cr).")
    the_play: str = Field(description="Specific pitch: How Lokesh can solve their current liquidity/capex gap.")
    source_link: str

# -------------------------------------------------------------------
# PHASE 1: WIDE-MESH SCAN
# -------------------------------------------------------------------
def get_company_signals():
    api_key = os.environ.get("SERPER_API_KEY")
    url = "https://google.serper.dev/search"
    print("🌍 Phase 1: Identifying high-intent corporate signals...")
    
    payload = json.dumps({
      "q": "(\"wins contract\" OR \"bags order\" OR \"expansion\" OR \"NCLT\" OR \"liquidity\") AND (\"Pvt Ltd\" OR \"Limited\") AND (Delhi OR Noida OR Gurugram OR Faridabad OR Haryana)",
      "num": 40, "tbs": "qdr:m"
    })
    
    try:
        res = requests.post(url, headers={'X-API-KEY': api_key, 'Content-Type': 'application/json'}, data=payload)
        snippets = "\n".join([f"Co: {r.get('title')} | Snip: {r.get('snippet')} | Link: {r.get('link')}" for r in res.json().get('organic', [])])
        
        client = genai.Client()
        prompt = f"Identify the top 10 most promising Pvt Ltd companies from these snippets involved in >1Cr expansions, orders, or NCLT. Snippets:\n{snippets}"
        ai_res = client.models.generate_content(model='gemini-2.5-flash', contents=prompt, config=genai.types.GenerateContentConfig(response_mime_type="application/json", response_schema=SignalList))
        return json.loads(ai_res.text).get("companies", [])
    except Exception: return []

# -------------------------------------------------------------------
# PHASE 2: FINANCE STRIKE TEAM DEEP DIVE
# -------------------------------------------------------------------
def enrich_company(co_data):
    api_key = os.environ.get("SERPER_API_KEY")
    co_name = co_data['name']
    print(f"   🎯 Phase 2: Hunting Finance Strike Team for {co_name}...")
    
    # Sniper search for the 3 target roles
    url = "https://google.serper.dev/search"
    payload = json.dumps({"q": f'"{co_name}" (CFO OR "Chief Financial Officer" OR Accountant OR "Finance Manager" OR "Head of Finance") (contact OR phone OR email OR LinkedIn)', "num": 10})
    
    try:
        res = requests.post(url, headers={'X-API-KEY': api_key, 'Content-Type': 'application/json'}, data=payload)
        deep_text = "\n".join([r.get('snippet') for r in res.json().get('organic', [])])
        
        client = genai.Client()
        prompt = f"""
        Company: {co_name}
        Signal: {co_data['signal']}
        
        Extract a 'Strike Team' of up to 3 people:
        1. CFO / Chief Financial Officer
        2. Senior Accountant / Accounts Head
        3. Any other Finance Leadership
        
        For each, find Name, Phone, and Email. If not found in snippets, put 'Not Listed'.
        Also provide the physical address and a pitch for Lokesh from Aditya Birla.
        
        Search Results:
        {deep_text}
        """
        ai_res = client.models.generate_content(model='gemini-2.5-flash', contents=prompt, config=genai.types.GenerateContentConfig(response_mime_type="application/json", response_schema=EnrichedLead))
        return json.loads(ai_res.text)
    except Exception: return None

# -------------------------------------------------------------------
# DELIVERY: MULTI-TARGET FORMATTING
# -------------------------------------------------------------------
def push_to_telegram(lead):
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not lead: return
    
    team_msg = ""
    for member in lead['strike_team']:
        team_msg += f"👤 *{member['role']}:* {member['name']}\n📞 {member['phone']} | ✉️ {member['email']}\n\n"

    msg = (
        f"🏦 *AGENT L: FINANCE STRIKE TEAM* 🏦\n"
        f"🏢 *Company:* {lead['company_name']}\n"
        f"📍 *Address:* {lead['address']}\n\n"
        f"🎯 *TARGETS:*\n{team_msg}"
        f"💰 *Need:* {lead['capital_need']}\n"
        f"♟️ *The Play:* {lead['the_play']}\n\n"
        f"🔗 *Source:* {lead['source_link']}"
    )
    requests.post(f"https://api.telegram.org/bot{bot_token}/sendMessage", json={"chat_id": chat_id, "text": msg, "parse_mode": "Markdown"})

if __name__ == "__main__":
    signals = get_company_signals()
    if signals:
        for co in signals[:8]: # Processing top 8 to stay within rate limits
            full_lead = enrich_company(co)
            if full_lead:
                push_to_telegram(full_lead)
                # Save to CSV for the master database
                with open("Agent_L_StrikeTeam.csv", "a", newline="", encoding="utf-8") as f:
                    csv.DictWriter(f, fieldnames=full_lead.keys()).writerow(full_lead)
    else:
        requests.post(f"https://api.telegram.org/bot{os.environ.get('TELEGRAM_BOT_TOKEN')}/sendMessage", 
                      json={"chat_id": os.environ.get('TELEGRAM_CHAT_ID'), "text": "🟢 *AGENT L: HEARTBEAT*\nSystem Active. No strike team targets found today."})
