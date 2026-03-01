import os
import json
import requests
from google import genai
from pydantic import BaseModel, Field

# -------------------------------------------------------------------
# 1. AGENT L: OUTPUT SCHEMA (Direct Client Table + Strategy)
# -------------------------------------------------------------------
class LoanLead(BaseModel):
    company_name: str = Field(description="Name of the Company needing funds.")
    target_type: str = Field(description="Target 1 (Owner/CEO) or Target 2 (CFO/Accountant/Finance Head).")
    complete_name: str = Field(description="Name of the person. Put 'Not Listed' if unavailable.")
    contact_number: str = Field(description="Phone number. Put 'Not Listed' if unavailable.")
    email: str = Field(description="Email address. Put 'Not Listed' if unavailable.")
    office_address: str = Field(description="Physical address. Put 'Not Listed' if unavailable.")
    proxy_signal: str = Field(description="The Proxy Signal: Why we think they need money (e.g., hiring CFO, CapEx expansion).")
    capital_need: str = Field(description="The Capital Need: What the money is specifically for (e.g., working capital, debt syndication, factory).")
    the_play: str = Field(description="The Play: The exact strategic pitch to use when contacting them, bypassing retail queues leveraging Aditya Birla.")

class LeadRoster(BaseModel):
    leads: list[LoanLead] = Field(description="List of all extracted direct corporate loan leads.")

# -------------------------------------------------------------------
# 2. INGESTION: PROXY SIGNAL DEEP SEARCH (LIVE PRODUCTION)
# -------------------------------------------------------------------
def fetch_loan_signals():
    api_key = os.environ.get("SERPER_API_KEY")
    if not api_key:
        print("🛑 FATAL ERROR: SERPER_API_KEY is missing. Halting execution.")
        return ""
    
    print("🌍 Agent L is scanning for live capital proxy signals (Expansions & Finance Hiring)...")
    url = "https://google.serper.dev/search"
    
    # The D2C Sniper Payload: Targeting Finance Job JDs, CapEx, and Working Capital needs near West Delhi/NCR
    payload = json.dumps({
      "q": "('debt syndication' OR 'fund raising' OR 'working capital' OR 'capex' OR 'project finance') AND ('Finance Manager' OR CFO OR 'manufacturing expansion' OR MSME) AND ('West Delhi' OR 'Bahadurgarh' OR 'Noida' OR 'Okhla' OR 'Gurugram' OR '110059')",
      "num": 20, # Pulling a wider net of organic results
      "tbs": "qdr:m" # Scanning the last 30 days only to ensure urgency
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
# 3. INTELLIGENCE: GEMINI 2.5 FLASH
# -------------------------------------------------------------------
def process_leads_with_agent_l(raw_text):
    print("🧠 Agent L is identifying Finance Heads & Owners...\n")
    client = genai.Client() 
    
    prompt = f"""
    You are Agent L, a Lead Generation Specialist for High-Ticket Corporate Loans (>1 Crore).
    Analyze the following search data to find EVERY company in Delhi NCR that urgently needs corporate funding.
    
    PROXY SIGNALS TO LOOK FOR:
    - Companies hiring Finance Managers/CFOs specifically for "fund raising" or "debt syndication".
    - Companies announcing manufacturing expansions, new factories, or large export orders (CapEx needs).
    - Companies seeking MSME subsidies or working capital.
    
    STRICT TARGET PROFILES:
    - Target 2: Accountant, CFO, or Head of Finance (PRIORITY TARGET).
    - Target 1: Owner, Founder, or Director.
    - DO NOT include DSAs, banks, or external loan consultants. Direct companies only.
    
    Extract the contact data and strategy, and return it strictly in the defined JSON array. Do not limit the number of companies.
    
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
# 4. DELIVERY: TELEGRAM PUSH NOTIFICATION (AGENT L)
# -------------------------------------------------------------------
def push_to_telegram(lead_data):
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN_L")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID_L")
    
    if not bot_token or not chat_id:
        return

    message = (
        f"🏦 *AGENT L: NEW CORPORATE LOAN TARGET* 🏦\n\n"
        f"🏢 *Company:* {lead_data['company_name']}\n"
        f"🎯 *Target:* {lead_data['target_type']} ({lead_data['complete_name']})\n"
        f"📞 *Contact:* {lead_data['contact_number']}\n"
        f"✉️ *Email:* {lead_data['email']}\n"
        f"📍 *Location:* {lead_data['office_address']}\n\n"
        f"📡 *The Proxy Signal:*\n{lead_data['proxy_signal']}\n\n"
        f"💰 *The Capital Need:*\n{lead_data['capital_need']}\n\n"
        f"♟️ *The Play:*\n{lead_data['the_play']}"
    )
    
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    requests.post(url, json={"chat_id": chat_id, "text": message, "parse_mode": "Markdown"})

# -------------------------------------------------------------------
# ORCHESTRATION (Table Output Format + Telegram Loop)
# -------------------------------------------------------------------
if __name__ == "__main__":
    print("=== INITIALIZING AGENT L (DIRECT CORPORATE LOAN ENGINE) ===\n")
    raw_data = fetch_loan_signals()
    
    if raw_data:
        roster = process_leads_with_agent_l(raw_data)
        
        if roster and "leads" in roster and roster["leads"]:
            print("---------------------------------------------------------------------------------------------------")
            print("COMPANY NAME | TARGET TYPE | COMPLETE NAME | CONTACT NUMBER | EMAIL | OFFICE ADDRESS | THE PROXY SIGNAL | THE CAPITAL NEED | THE PLAY")
            print("---------------------------------------------------------------------------------------------------")
            
            for lead in roster["leads"]:
                # Print to CLI Table
                row = f"- {lead['company_name']} | {lead['target_type']} | {lead['complete_name']} | {lead['contact_number']} | {lead['email']} | {lead['office_address']} | {lead['proxy_signal']} | {lead['capital_need']} | {lead['the_play']}"
                print(row)
                
                # Push to Telegram
                push_to_telegram(lead)
            
            print("---------------------------------------------------------------------------------------------------")
            print(f"✅ Successfully extracted and pushed {len(roster['leads'])} direct loan targets.")
        else:
            print("No direct loan targets identified today.")
