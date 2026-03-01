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

# -------------------------------------------------------------------
# PHASE 1: TARGET ACQUISITION (WIDE NET)
# -------------------------------------------------------------------
def get_company_signals():
    api_key = os.environ.get("SERPER_API_KEY")
    url = "https://google.serper.dev/search"
    queries = [
        "\"Pvt Ltd\" wins contract Delhi NCR Haryana",
        "\"Pvt Ltd\" NCLT Delhi petition 2026",
        "\"Pvt Ltd\" bags order factory expansion North India"
    ]
    all_snippets = []
    print("🌍 Phase 1: Scanning 350km radius for signals...")
    for q in queries:
        try:
            res = requests.post(url, headers={'X-API-KEY': api_key, 'Content-Type': 'application/json'}, 
                                json={"q": q, "num": 25, "tbs": "qdr:m"})
            all_snippets.extend([f"Co: {r.get('title')} | Snip: {r.get('snippet')} | Link: {r.get('link')}" for r in res.json().get('organic', [])])
        except Exception: continue

    if not all_snippets: return []
    client = genai.Client()
    prompt = f"Identify the top 15 companies from these snippets involved in >1Cr deals. Output JSON. Snippets:\n" + "\n".join(all_snippets)
    try:
        ai_res = client.models.generate_content(model='gemini-2.5-flash', contents=prompt, config=genai.types.GenerateContentConfig(response_mime_type="application/json", response_schema=SignalList))
        return json.loads(ai_res.text).get("companies", [])
    except Exception: return []

# -------------------------------------------------------------------
# PHASE 2: STRIKE TEAM ENRICHMENT (SNIPER FALLBACK)
# -------------------------------------------------------------------
def deep_enrich_strike_team(company_name):
    api_key = os.environ.get("SERPER_API_KEY")
    url = "https://google.serper.dev/search"
    print(f"   🔍 Sniper searching contacts for {company_name}...")
    
    q = f'"{company_name}" (CFO OR Accountant OR "Finance Head") (contact OR phone OR email)'
    try:
        res = requests.post(url, headers={'X-API-KEY': api_key, 'Content-Type': 'application/json'}, json={"q": q, "num": 10})
        snippets = "\n".join([r.get('snippet') for r in res.json().get('organic', [])])
        
        client = genai.Client()
        prompt = f"Find Name, Phone, and Email for the CFO, Accountant, and Finance Lead of {company_name}. Look for numbers starting with 981 or +91. Results:\n{snippets}"
        ai_res = client.models.generate_content(model='gemini-2.5-flash', contents=prompt, config=genai.types.GenerateContentConfig(response_mime_type="application/json", response_schema=EnrichedLead))
        return json.loads(ai_res.text)
    except Exception: return None

# -------------------------------------------------------------------
# DELIVERY
# -------------------------------------------------------------------
def send_excel_to_telegram(file_path):
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    url = f"https://api.telegram.org/bot{bot_token}/sendDocument"
    with open(file_path, 'rb') as file:
        requests.post(url, data={'chat_id': chat_id, 'caption': "📊 Master Lead Database (Limit 1,000)"}, files={'document': file})

if __name__ == "__main__":
    signals = get_company_signals()
    leads_for_excel = []
    
    if signals:
        for co in signals[:10]:
            full_lead = deep_enrich_strike_team(co['name'])
            if full_lead:
                row = {
                    "Company": company_name := full_lead.get('company_name', co['name']),
                    "Signal": co['signal'],
                    "Source": co['source'],
                    "Address": full_lead.get('address', 'N/A'),
                    "Pitch": full_lead.get('the_play', 'N/A')
                }
                for i, member in enumerate(full_lead.get('strike_team', [])[:3]):
                    row[f"Target_{i+1}_Name"] = member.get('name', 'N/A')
                    row[f"Target_{i+1}_Phone"] = member.get('phone', 'N/A')
                    row[f"Target_{i+1}_Email"] = member.get('email', 'N/A')
                leads_for_excel.append(row)

    file_name = "Agent_L_Master.xlsx"
    df_new = pd.DataFrame(leads_for_excel)
    
    if os.path.exists(file_name):
        df_old = pd.read_excel(file_name)
        df_final = pd.concat([df_old, df_new]).drop_duplicates(subset=['Company']).tail(1000)
    else:
        df_final = df_new.tail(1000)

    if not df_final.empty:
        df_final.to_excel(file_name, index=False)
        send_excel_to_telegram(file_name)
