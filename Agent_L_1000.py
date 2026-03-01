import os
import json
import pandas as pd
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
    role: str = Field(description="CFO, Accountant, or Finance Lead")
    name: str = Field(description="Full name")
    phone: str = Field(description="Extracted phone/mobile")
    email: str = Field(description="Extracted corporate email")

class EnrichedLead(BaseModel):
    company_name: str
    strike_team: list[FinanceContact]
    address: str
    capital_need: str
    the_play: str
    source_link: str

class ContactInfo(BaseModel):
    contacts: list[FinanceContact]

# -------------------------------------------------------------------
# PHASE 1: TARGET ACQUISITION (MULTI-STREAM)
# -------------------------------------------------------------------
def get_company_signals():
    api_key = os.environ.get("SERPER_API_KEY")
    url = "https://google.serper.dev/search"
    queries = [
        "\"Pvt Ltd\" wins contract Delhi NCR Haryana Punjab",
        "\"Pvt Ltd\" NCLT Delhi expansion petition 2026",
        "\"Pvt Ltd\" bags order machinery factory setup North India"
    ]
    all_snippets = []
    print("🌍 Phase 1: Scanning 350km radius for high-intent signals...")
    for q in queries:
        try:
            res = requests.post(url, headers={'X-API-KEY': api_key, 'Content-Type': 'application/json'}, 
                                json={"q": q, "num": 30, "tbs": "qdr:m"})
            all_snippets.extend([f"Co: {r.get('title')} | Snip: {r.get('snippet')} | Link: {r.get('link')}" for r in res.json().get('organic', [])])
        except Exception: continue

    if not all_snippets: return []
    client = genai.Client()
    prompt = f"Identify the top 15 companies from these snippets involved in >1Cr deals. Output JSON list. Snippets:\n" + "\n".join(all_snippets)
    try:
        ai_res = client.models.generate_content(model='gemini-2.5-flash', contents=prompt, config=genai.types.GenerateContentConfig(response_mime_type="application/json", response_schema=SignalList))
        return json.loads(ai_res.text).get("companies", [])
    except Exception: return []

# -------------------------------------------------------------------
# PHASE 2: FALLBACK ENRICHMENT (SNIPER MODE)
# -------------------------------------------------------------------
def deep_enrich_strike_team(company_name, original_signal):
    api_key = os.environ.get("SERPER_API_KEY")
    url = "https://google.serper.dev/search"
    print(f"   🔍 Fallback: Sniper-searching contact info for {company_name}...")
    
    # Specific dork to find CFO/Accountant contact info
    q = f'"{company_name}" (CFO OR Accountant OR "Finance Head") (contact OR phone OR email OR mobile)'
    try:
        res = requests.post(url, headers={'X-API-KEY': api_key, 'Content-Type': 'application/json'}, json={"q": q, "num": 10})
        snippets = "\n".join([r.get('snippet') for r in res.json().get('organic', [])])
        
        client = genai.Client()
        prompt = f"Using these snippets, find the Name, Phone, and Email for the CFO, Accountant, and Finance Lead of {company_name}. If missing, search patterns like '981...' or '@co.com'. Results:\n{snippets}"
        ai_res = client.models.generate_content(model='gemini-2.5-flash', contents=prompt, config=genai.types.GenerateContentConfig(response_mime_type="application/json", response_schema=EnrichedLead))
        return json.loads(ai_res.text)
    except Exception: return None

# -------------------------------------------------------------------
# DELIVERY: EXCEL DISPATCH
# -------------------------------------------------------------------
def send_excel_to_telegram(file_path):
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    url = f"https://api.telegram.org/bot{bot_token}/sendDocument"
    with open(file_path, 'rb') as file:
        requests.post(url, data={'chat_id': chat_id, 'caption': "📊 AGENT L: Master Lead Database (1,000 Row Limit)"}, files={'document': file})

# -------------------------------------------------------------------
# MAIN ORCHESTRATION
# -------------------------------------------------------------------
if __name__ == "__main__":
    signals = get_company_signals()
    leads_for_excel = []
    
    if signals:
        for co in signals[:10]:
            full_lead = deep_enrich_strike_team(co['name'], co['signal'])
            if full_lead:
                row = {
                    "Company": full_lead.get('company_name', co['name']),
                    "Signal": co['signal'],
                    "Estimated Need": full_lead.get('capital_need', 'Est. >1Cr'),
                    "Pitch": full_lead.get('the_play', 'N/A'),
                    "Address": full_lead.get('address', 'N/A'),
                    "Source": co['source']
                }
                # Mapping the Strike Team members to columns
                for i, member in enumerate(full_lead.get('strike_team', [])[:3]):
                    row[f"Target_{i+1}_Role"] = member.get('role', 'N/A')
                    row[f"Target_{i+1}_Name"] = member.get('name', 'N/A')
                    row[f"Target_{i+1}_Phone"] = member.get('phone', 'N/A')
                    row[f"Target_{i+1}_Email"] = member.get('email', 'N/A')
                leads_for_excel.append(row)

    # Database Maintenance (1,000 Row Limit)
    df_new = pd.DataFrame(leads_for_excel)
    file_name = "Agent_L_StrikeTeam_Master.xlsx"
    
    if os.path.exists(file_name):
        df_old = pd.read_excel(file_name)
        df_final = pd.concat([df_old, df_new]).drop_duplicates(subset=['Company']).tail(1000)
    else:
        df_final = df_new.tail(1000)

    if not df_final.empty:
        df_final.to_excel(file_name, index=False)
        send_excel_to_telegram(file_name)
    else:
        print("No new signals found today.")
