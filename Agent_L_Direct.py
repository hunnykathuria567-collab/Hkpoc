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
    company_name: str = Field(description="Name of the Company needing funds.")
    target_type: str = Field(description="Target 1 (Owner/CEO) or Target 2 (CFO/Accountant/Finance Head).")
    complete_name: str = Field(description="Name of the person. Put 'Not Listed' if unavailable.")
    contact_number: str = Field(description="Phone number. Put 'Not Listed' if unavailable.")
    email: str = Field(description="Email address. Put 'Not Listed' if unavailable.")
    office_address: str = Field(description="Physical address. Put 'Not Listed' if unavailable.")
    proxy_signal: str = Field(description="Why we think they need money (e.g., hiring CFO, CapEx expansion).")
    capital_need: str = Field(description="What the money is for (e.g., working capital, debt syndication, factory).")
    the_play: str = Field(description="The strategic pitch to use when contacting them, leveraging Aditya Birla.")

class LeadRoster(BaseModel):
    leads: list[LoanLead] = Field(description="List of extracted direct corporate loan leads.")

class ContactInfo(BaseModel):
    phone: str = Field(description="Extracted phone number, or 'Not Listed'.")
    email: str = Field(description="Extracted email address, or 'Not Listed'.")

# -------------------------------------------------------------------
# 2. INGESTION 1: PROXY SIGNAL DEEP SEARCH
# -------------------------------------------------------------------
def fetch_loan_signals():
    api_key = os.environ.get("SERPER_API_KEY")
    if not api_key:
        print("🛑 FATAL ERROR: SERPER_API_KEY is missing. Halting execution.")
        return ""
    
    print("🌍 Phase 1: Scanning for live capital proxy signals (Expansions & Finance Hiring)...")
    url = "https://google.serper.dev/search"
    payload = json.dumps({
      "q": "('debt syndication' OR 'fund raising' OR 'working capital' OR 'capex' OR 'project finance') AND ('Finance Manager' OR CFO OR 'manufacturing expansion' OR MSME) AND ('West Delhi' OR 'Bahadurgarh' OR 'Noida' OR 'Okhla' OR 'Gurugram' OR '110059')",
      "num": 30, # Wide net to ensure we hit 20 solid rows
      "tbs": "qdr:m"
    })
    headers = {'X-API-KEY': api_key, 'Content-Type': 'application/json'}
    
    # V2 Broader Payload: Opening up to all of Delhi NCR and broadening financial terms
    payload = json.dumps({
      "q": "('debt syndication' OR 'fund raising' OR 'working capital' OR 'corporate loan' OR 'capex') AND ('Finance' OR CFO OR 'expansion' OR MSME) AND ('Delhi' OR 'Delhi NCR' OR 'Gurugram' OR 'Noida' OR 'Faridabad')",
      "num": 40, # Scanning 40 Google pages now instead of 30
      "tbs": "qdr:y" # TEMPORARY TEST: Expanding to the last 1 year of news to guarantee a hit
    })


# -------------------------------------------------------------------
# 3. INTELLIGENCE 1: EXTRACT TARGETS
# -------------------------------------------------------------------
def process_leads_with_agent_l(raw_text):
    print("🧠 Phase 1: Identifying Finance Heads & Owners...")
    client = genai.Client() 
    prompt = f"""
    You are Agent L. Analyze this search data to find companies in Delhi NCR urgently needing corporate funding.
    Extract the company, target person, proxy signal, capital need, and strategic pitch. 
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
# 4. INGESTION & INTELLIGENCE 2: THE ENRICHMENT LOOP (CONTACTS)
# -------------------------------------------------------------------
def enrich_contact_info(company_name, person_name):
    api_key = os.environ.get("SERPER_API_KEY")
    if not api_key or person_name == "Not Listed": return {"phone": "Not Listed", "email": "Not Listed"}
    
    print(f"   🔍 Enrichment Loop: Hunting direct contact info for {person_name} at {company_name}...")
    url = "https://google.serper.dev/search"
    payload = json.dumps({
      "q": f'"{company_name}" "{person_name}" (email OR phone OR contact OR directory OR LinkedIn)',
      "num": 5
    })
    headers = {'X-API-KEY': api_key, 'Content-Type': 'application/json'}
    
    try:
        # Step A: Scrape contact specific search
        response = requests.post(url, headers=headers, data=payload)
        response.raise_for_status()
        results = response.json().get('organic', [])
        raw_contact_text = "\n".join([f"- {r.get('snippet')}" for r in results])
        
        # Step B: Gemini extracts just the phone and email
        client = genai.Client()
        prompt = f"Extract the phone number and email for {person_name} at {company_name} from this text. If not found, return 'Not Listed'. Text: {raw_contact_text}"
        
        ai_response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=genai.types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=ContactInfo,
                temperature=0.1 
            ),
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
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN_L")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID_L")
    if not bot_token or not chat_id: return
    message = (
        f"🏦 *AGENT L: NEW TARGET* 🏦\n"
        f"🏢 *Company:* {lead_data['company_name']}\n"
        f"🎯 *Target:* {lead_data['target_type']} ({lead_data['complete_name']})\n"
        f"📞 *Contact:* {lead_data['contact_number']}\n"
        f"✉️ *Email:* {lead_data['email']}\n"
        f"📍 *Location:* {lead_data['office_address']}\n\n"
        f"📡 *Signal:* {lead_data['proxy_signal']}\n"
        f"💰 *Need:* {lead_data['capital_need']}\n"
        f"♟️ *Play:* {lead_data['the_play']}"
    )
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    requests.post(url, json={"chat_id": chat_id, "text": message, "parse_mode": "Markdown"})

# -------------------------------------------------------------------
# ORCHESTRATION 
# -------------------------------------------------------------------
if __name__ == "__main__":
    print("=== INITIALIZING AGENT L (DIRECT CORPORATE LOAN ENGINE) ===\n")
    raw_data = fetch_loan_signals()
    
    if raw_data:
        roster = process_leads_with_agent_l(raw_data)
        
        if roster and "leads" in roster and roster["leads"]:
            # Hard limit to 20 rows
            target_leads = roster["leads"][:20] 
            print(f"\n✅ Phase 1 Complete. {len(target_leads)} base targets locked. Commencing Contact Enrichment Loop...\n")
            
            for index, lead in enumerate(target_leads, 1):
                # The Loop: Try to find missing emails/phones
                if lead['contact_number'] == "Not Listed" or lead['email'] == "Not Listed":
                    enriched_data = enrich_contact_info(lead['company_name'], lead['complete_name'])
                    if enriched_data['phone'] != "Not Listed": lead['contact_number'] = enriched_data['phone']
                    if enriched_data['email'] != "Not Listed": lead['email'] = enriched_data['email']
                
                print(f"[{index}/20] Processed: {lead['company_name']} -> {lead['contact_number']} | {lead['email']}")
                save_lead_to_csv(lead)
                push_to_telegram(lead)
            
            print(f"\n✅ Run Complete. {len(target_leads)} enriched rows saved to Excel and pushed to Telegram.")
        else:
            print("No direct loan targets identified today.")
            open("Agent_L_Corporate_Loans.csv", 'a').close()
    else:
        open("Agent_L_Corporate_Loans.csv", 'a').close()
