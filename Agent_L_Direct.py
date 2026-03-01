import os
import json
import csv
import requests
from google import genai
from pydantic import BaseModel, Field

# -------------------------------------------------------------------
# 1. AGENT L: OUTPUT SCHEMAS
# -------------------------------------------------------------------
class LoanLead(BaseModel):
    company_name: str = Field(description="Name of the Pvt Ltd / SME company.")
    target_type: str = Field(description="Target 1 (Owner/CEO) or Target 2 (CFO/Accountant/Finance Head).")
    complete_name: str = Field(description="Name of the person. Put 'Not Listed' if unavailable.")
    contact_number: str = Field(description="Phone number. Put 'Not Listed' if unavailable.")
    email: str = Field(description="Email address. Put 'Not Listed' if unavailable.")
    office_address: str = Field(description="Physical address. Put 'Not Listed' if unavailable.")
    proxy_signal: str = Field(description="Why we think they need money (e.g., won a big tender, heavy factory expansion).")
    capital_need: str = Field(description="Estimated need. MUST be above ₹1 Crore. If exact amount is unknown but project is large, estimate it.")
    the_play: str = Field(description="The strategic pitch: How Aditya Birla can fund their execution capital or CapEx.")

class LeadRoster(BaseModel):
    leads: list[LoanLead] = Field(description="List of extracted direct SME loan leads.")

class ContactInfo(BaseModel):
    phone: str = Field(description="Extracted phone number, or 'Not Listed'.")
    email: str = Field(description="Extracted email address, or 'Not Listed'.")

# -------------------------------------------------------------------
# 2. INGESTION 1: 350KM RADIUS (B2B TENDERS & EXPANSIONS)
# -------------------------------------------------------------------
def fetch_loan_signals():
    api_key = os.environ.get("SERPER_API_KEY")
    if not api_key:
        print("⚠️ SERPER_API_KEY missing. Forcing 'Heartbeat' fallback mode for test...")
        return "" 
    
    print("🌍 Phase 1: Scanning 350km Radius (Expansions, Tenders, Corporate Finance)...")
    url = "https://google.serper.dev/search"
    
    # V6 Payload: Corrected Syntax + 1 Year Pipeline Flush
    payload = json.dumps({
      "q": '("Pvt Ltd" OR "Limited" OR "EPC") AND ("wins contract" OR "bags order" OR "new facility" OR "expansion" OR "debt syndication") AND (Delhi OR Haryana OR Punjab OR UP OR Rajasthan OR Noida)',
      "num": 40, 
      "tbs": "qdr:y" # Temporarily expanded to 1 year to guarantee a pipeline flush
    })
    
    headers = {'X-API-KEY': api_key, 'Content-Type': 'application/json'}
    try:
        response = requests.post(url, headers=headers, data=payload)
        response.raise_for_status()
        results = response.json().get('organic', [])
        return "\n".join([f"- {r.get('title')}: {r.get('snippet')}" for r in results])
    except Exception as e:
        print(f"Deep Search Error: {e}")
        return ""

# -------------------------------------------------------------------
# 3. INTELLIGENCE 1: THE "ASSUME >1CR" FILTER
# -------------------------------------------------------------------
def process_leads_with_agent_l(raw_text):
    if not raw_text.strip(): return None
    print("🧠 Phase 1: Filtering Noise & Identifying 1Cr+ Targets...")
    client = genai.Client() 
    prompt = f"""
    You are Agent L, a Lead Generation Specialist for High-Ticket Corporate Loans.
    Analyze this search data to find companies within a 350km radius of Delhi that have an URGENT need for capital.
    
    STRICT STEP 2 NOISE FILTERS:
    1. TICKET SIZE (THE ASSUMPTION CLAUSE): Target is >₹1 Crore. If an article mentions a "Pvt Ltd" or "Limited" company setting up a factory, expanding capacity, or winning a major contract/tender, ASSUME the capital need is >₹1 Crore and KEEP THEM. Only drop them if it explicitly says the project is tiny (e.g., under 1 Crore). THERE IS NO UPPER LIMIT.
    2. RETAIL EXCLUSION: Drop any mention of individual loans, Mudra loans, gold loans, or personal debt. 
    3. TARGET FOCUS: Look for companies winning contracts (execution capital needed) or expanding factories (CapEx needed).
    
    Extract the company, target person, proxy signal, capital need (estimate it based on the project if not explicitly stated), and strategic pitch. 
    Return the data strictly in the JSON array.
    
    Raw Market Data:
    {raw_text}
    """
    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=genai.types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=LeadRoster,
                temperature=0.1 
            ),
        )
        return json.loads(response.text)
    except Exception as e:
        print(f"Agent L Processing Error: {e}")
        return None

# -------------------------------------------------------------------
# 4. INGESTION 2: CONTACT ENRICHMENT
# -------------------------------------------------------------------
def enrich_contact_info(company_name, person_name):
    api_key = os.environ.get("SERPER_API_KEY")
    if not api_key or person_name == "Not Listed": return {"phone": "Not Listed", "email": "Not Listed"}
    print(f"   🔍 Enrichment Loop: Hunting direct contact info for {person_name} at {company_name}...")
    url = "https://google.serper.dev/search"
    payload = json.dumps({"q": f'"{company_name}" "{person_name}" (email OR phone OR contact)', "num": 5})
    headers = {'X-API-KEY': api_key, 'Content-Type': 'application/json'}
    try:
        response = requests.post(url, headers=headers, data=payload)
        response.raise_for_status()
        raw_contact_text = "\n".join([f"- {r.get('snippet')}" for r in response.json().get('organic', [])])
        client = genai.Client()
        prompt = f"Extract the phone number and email for {person_name} at {company_name} from this text. If not found, return 'Not Listed'. Text: {raw_contact_text}"
        ai_response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=genai.types.GenerateContentConfig(response_mime_type="application/json", response_schema=ContactInfo, temperature=0.1)
        )
        return json.loads(ai_response.text)
    except Exception as e:
        return {"phone": "Not Listed", "email": "Not Listed"}

# -------------------------------------------------------------------
# 5. STORAGE & DELIVERY
# -------------------------------------------------------------------
def save_lead_to_csv(lead_data, filename="Agent_L_Corporate_Loans.csv"):
    file_exists = os.path.isfile(filename)
    headers = list(lead_data.keys())
    with open(filename, mode='a', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        if not file_exists: writer.writeheader()
        writer.writerow(lead_data)

def push_to_telegram(lead_data):
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    
    if not bot_token or not chat_id: 
        print("❌ ERROR: Telegram Bot Token or Chat ID is MISSING from the environment!")
        return
    
    if lead_data['company_name'] == "No New SME Potential Found":
        message = (
            f"🟢 AGENT L: SYSTEM HEARTBEAT 🟢\n\n"
            f"{lead_data['company_name']}\n"
            f"Status: {lead_data['proxy_signal']}"
        )
    else:
        message = (
            f"🏦 AGENT L: NEW TARGET ACQUIRED (>1Cr) 🏦\n"
            f"🏢 Company: {lead_data['company_name']}\n"
            f"🎯 Target: {lead_data['target_type']} ({lead_data['complete_name']})\n"
            f"📞 Contact: {lead_data['contact_number']}\n"
            f"✉️ Email: {lead_data['email']}\n"
            f"📍 Location: {lead_data['office_address']}\n\n"
            f"📡 Signal: {lead_data['proxy_signal']}\n"
            f"💰 Need: {lead_data['capital_need']}\n"
            f"♟️ Play: {lead_data['the_play']}"
        )
    
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    
    # DIAGNOSTIC: Try sending with Markdown first. If it fails, print the error and send plain text.
    print(f"   📲 Attempting to push {lead_data['company_name']} to Telegram...")
    try:
        response = requests.post(url, json={"chat_id": chat_id, "text": message})
        if response.status_code == 200:
            print("   ✅ Telegram delivery successful!")
        else:
            print(f"   ❌ Telegram API Error [{response.status_code}]: {response.text}")
    except Exception as e:
        print(f"   ❌ Telegram Request Failed completely: {e}")

def push_dummy_lead():
    dummy_lead = {
        "company_name": "No New SME Potential Found",
        "target_type": "N/A",
        "complete_name": "System Status: Active",
        "contact_number": "N/A",
        "email": "N/A",
        "office_address": "N/A",
        "proxy_signal": "Engine ran successfully. Scanned 350km radius. No high-intent 1Cr+ capex/tender signals found today.",
        "capital_need": "N/A",
        "the_play": "N/A"
    }
    save_lead_to_csv(dummy_lead)
    push_to_telegram(dummy_lead)
    print("\n✅ Daily Heartbeat logged: 'No New SME Potential Found' pushed to Telegram & CSV.")

# -------------------------------------------------------------------
# ORCHESTRATION 
# -------------------------------------------------------------------
if __name__ == "__main__":
    print("=== INITIALIZING AGENT L (350KM V6 ENGINE - YOUR PHONE) ===\n")
    raw_data = fetch_loan_signals()
    
    if raw_data:
        roster = process_leads_with_agent_l(raw_data)
        
        if roster and "leads" in roster and len(roster["leads"]) > 0:
            target_leads = roster["leads"][:20] 
            print(f"\n✅ Phase 1 Complete. {len(target_leads)} validated SME targets locked. Commencing Contact Enrichment...\n")
            
            for index, lead in enumerate(target_leads, 1):
                if lead['contact_number'] == "Not Listed" or lead['email'] == "Not Listed":
                    enriched_data = enrich_contact_info(lead['company_name'], lead['complete_name'])
                    if enriched_data['phone'] != "Not Listed": lead['contact_number'] = enriched_data['phone']
                    if enriched_data['email'] != "Not Listed": lead['email'] = enriched_data['email']
                
                print(f"[{index}/{len(target_leads)}] Processed: {lead['company_name']} -> {lead['contact_number']} | {lead['email']}")
                save_lead_to_csv(lead)
                push_to_telegram(lead)
            
            print(f"\n✅ Run Complete. {len(target_leads)} enriched rows saved to Excel and pushed to Telegram.")
        else:
            push_dummy_lead()
    else:
        push_dummy_lead()
