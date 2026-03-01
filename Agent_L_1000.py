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
# PHASE 1: MULTI-STREAM SCAN
# -------------------------------------------------------------------
def get_company_signals():
    api_key = os.environ.get("SERPER_API_KEY")
    url = "https://google.serper.dev/search"
    queries = [
        "\"Pvt Ltd\" wins contract Delhi NCR 2026",
        "\"Pvt Ltd\" NCLT Delhi petition March 2026",
        "\"Pvt Ltd\" factory expansion Haryana Punjab 2026"
    ]
    all_snippets = []
    print(f"🌍 Phase 1: Scanning for high-value targets...")
    for q in queries:
        try:
            res = requests.post(url, headers={'X-API-KEY': api_key, 'Content-Type': 'application/json'}, 
                                json={"q": q, "num": 40, "tbs": "qdr:m"})
            all_snippets.extend([f"Co: {r.get('title')} | Snip: {r.get('snippet')} | Link: {r.get('link')}" for r in res.json().get('organic', [])])
        except Exception: continue

    if not all_snippets: return []
    client = genai.Client()
    prompt = f"Identify up to 20 companies from these snippets involved in >1Cr deals. Output JSON list. Snippets:\n" + "\n".join(all_snippets)
    try:
        ai_res = client.models.generate_content(model='gemini-2.5-flash', contents=prompt, config=genai.types.GenerateContentConfig(response_mime_type="application/json", response_schema=SignalList))
        return json.loads(ai_res.text).get("companies", [])
    except Exception: return []

# -------------------------------------------------------------------
# PHASE 2: DEEP DIVE & ENRICHMENT
# -------------------------------------------------------------------
def enrich_company(co_data):
    api_key = os.environ.get("SERPER_API_KEY")
    co_name = co_data['name']
    url = "https://google.serper.dev/search"
    payload = json.dumps({"q": f'"{co_name}" (CFO OR Accountant OR "Finance Manager") (contact OR phone OR email)', "num": 10})
    try:
        res = requests.post(url, headers={'X-API-KEY': api_key, 'Content-Type': 'application/json'}, data=payload)
        deep_text = "\n".join([r.get('snippet') for r in res.json().get('organic', [])])
        client = genai.Client()
        prompt = f"Extract Strike Team (CFO, Accountant, Finance Lead) for {co_name}. Use 'Not Listed' if missing. Results:\n{deep_text}"
        ai_res = client.models.generate_content(model='gemini-2.5-flash', contents=prompt, config=genai.types.GenerateContentConfig(response_mime_type="application/json", response_schema=EnrichedLead))
        result = json.loads(ai_res.text)
        result['source_link'] = co_data['source']
        return result
    except Exception: return None

# -------------------------------------------------------------------
# TELEGRAM DOCUMENT DISPATCH
# -------------------------------------------------------------------
def send_excel_to_telegram(file_path):
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not os.path.exists(file_path): return
    
    url = f"https://api.telegram.org/bot{bot_token}/sendDocument"
    print(f"📤 Dispatching 1,000 Row Limit Master List to Telegram...")
    with open(file_path, 'rb') as file:
        requests.post(url, data={'chat_id': chat_id, 'caption': "🏦 AGENT L: Verified SME Finance Leads (Bulk Export)"}, files={'document': file})

# -------------------------------------------------------------------
# MAIN ORCHESTRATION
# -------------------------------------------------------------------
if __name__ == "__main__":
    signals = get_company_signals()
    leads_for_excel = []
    
    if signals:
        for co in signals:
            full_lead = enrich_company(co)
            if full_lead:
                # Flattening Strike Team for Excel Rows
                row = {
                    "Company": full_lead['company_name'],
                    "Capital Need": full_lead['capital_need'],
                    "The Play": full_lead['the_play'],
                    "Address": full_lead['address'],
                    "Source Link": full_lead['source_link']
                }
                # Add up to 3 contacts to the same row
                for i, member in enumerate(full_lead.get('strike_team', [])[:3]):
                    row[f"Target_{i+1}_Role"] = member['role']
                    row[f"Target_{i+1}_Name"] = member['name']
                    row[f"Target_{i+1}_Phone"] = member['phone']
                
                leads_for_excel.append(row)

    # 1,000 Row Limit Enforcement & Excel Creation
    df_new = pd.DataFrame(leads_for_excel)
    file_name = "Agent_L_Master_Leads.xlsx"
    
    if os.path.exists(file_name):
        df_old = pd.read_excel(file_name)
        df_final = pd.concat([df_old, df_new]).drop_duplicates(subset=['Company']).tail(1000)
    else:
        df_final = df_new.tail(1000)

    df_final.to_excel(file_name, index=False)
    
    if not df_final.empty:
        send_excel_to_telegram(file_name)
    else:
        print("No new leads found to update Excel.")
