import os
import json
import requests
from google import genai
from pydantic import BaseModel, Field

# -------------------------------------------------------------------
# 1. AGENT P: OUTPUT SCHEMAS (The 10-Column TAP Array)
# -------------------------------------------------------------------
class HomologationLead(BaseModel):
    target_entity: str = Field(description="Name of the OEM, startup, or manufacturer.")
    hq_location: str = Field(description="Headquarters location (e.g., Gurgaon, Noida).")
    product_category: str = Field(description="e-2W, e-3W, Micro EV, Battery Swapping, or Charger.")
    intent_signal: str = Field(description="The trigger event (e.g., funding, prototype testing).")
    financial_health: str = Field(description="Mention of funding, bootstrapped status, or pricing.")
    estimated_timeline: str = Field(description="When are they launching or expanding?")
    key_decision_maker: str = Field(description="Name/Title of the CEO, Founder, or Head of Ops.")
    kdm_digital_footprint: str = Field(description="Likely digital footprint or platform to reach them.")
    compliance_gap: str = Field(description="Why they need an Indian ICAT agent right now (e.g., AIS-156).")
    priority_score: int = Field(description="1 to 5 ranking. 5 is NCR startup launching soon.", ge=1, le=5)

class LeadRoster(BaseModel):
    leads: list[HomologationLead] = Field(description="A list of up to 10 qualified homologation leads.")

# -------------------------------------------------------------------
# 2. INGESTION: DEEP GOOGLE SEARCH (SERPER.DEV)
# -------------------------------------------------------------------
def fetch_market_signals():
    api_key = os.environ.get("SERPER_API_KEY")
    if not api_key:
        print("⚠️ No SERPER_API_KEY found. Running in Test Mode with multi-target mock data...\n")
        return """
        Article 1: Gurugram-based 'Blinq Mobility' spotted testing their first working prototype 'Car1' 
        on the road. The bootstrapped startup is officially setting parameters to apply for ICAT certification 
        this year. They are using custom composite body panels for their affordable micro-EV.
        
        Article 2: Noida-based 'VoltSwap Networks' just raised a small seed round to deploy 50 
        new public EV battery swapping stations across Delhi NCR. The founder noted they are currently 
        navigating the strict AIS-156 Amendment 3 thermal runaway testing for their new proprietary battery packs.
        """
    
    print("🌍 Agent P is running a deep Google Search (NCR, Startups, Hardware/Batteries)...")
    url = "https://google.serper.dev/search"
    
    # V7.3 The Ultimate Sniper Payload (Vehicles + Batteries + Infra)
    payload = json.dumps({
      "q": "(e-2W OR e-3W OR retrofit OR micro-EV OR 'battery swapping' OR 'EV charger') AND (startup OR seed OR grant OR bootstrapped) AND ('Delhi NCR' OR Gurgaon OR Noida) AND (ICAT OR ARAI OR homologation OR 'AIS-156' OR 'IS 17017' OR testing) -Tata -Mahindra -Ola -Ather -Hero -Bajaj",
      "num": 10,
      "tbs": "qdr:w" # Last 7 days only
    })
    
    headers = {
      'X-API-KEY': api_key,
      'Content-Type': 'application/json'
    }
    
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
def process_leads_with_agent_p(raw_text):
    print("🧠 Agent P is analyzing the perimeter...")
    client = genai.Client() 
    
    prompt = f"""
    You are Agent P, a Strategic Lead Architect. Analyze the following market news.
    Identify ALL companies (up to 10) that will likely require automotive homologation (ICAT/ARAI) in India soon. 
    
    STRICT TARGETING CRITERIA:
    1. Location: MUST be operating, expanding, or headquartered in/near Delhi NCR (Gurgaon, Noida, etc.).
    2. Budget Profile: Prioritize low-budget, bootstrapped, tier-2 vendors, or early-stage startups.
    3. Tech Profile: Include vehicles (e-2W/e-3W), battery swapping networks, and charging infra.
    
    SCORING LOGIC:
    - Score 5/5: Startup launching in NCR facing direct ICAT/AIS-156 hurdles.
    
    Extract the details into the defined JSON array.
    
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
        print(f"Agent P Processing Error: {e}")
        return None

# -------------------------------------------------------------------
# 4. DELIVERY: TELEGRAM PUSH NOTIFICATION (SINGLE ROW FORMAT)
# -------------------------------------------------------------------
def push_to_telegram(lead_data):
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    
    if not bot_token or not chat_id:
        return

    message = (
        f"🚨 *AGENT P: NEW TAP ACQUIRED* 🚨\n\n"
        f"🏢 *Target:* {lead_data['target_entity']}\n"
        f"📍 *HQ:* {lead_data['hq_location']}\n"
        f"🔋 *Category:* {lead_data['product_category']}\n"
        f"🎯 *Signal:* {lead_data['intent_signal']}\n"
        f"💰 *Financials:* {lead_data['financial_health']}\n"
        f"📅 *Timeline:* {lead_data['estimated_timeline']}\n"
        f"👤 *KDM:* {lead_data['key_decision_maker']}\n"
        f"🌐 *KDM Footprint:* {lead_data['kdm_digital_footprint']}\n"
        f"⚠️ *Gap:* {lead_data['compliance_gap']}\n"
        f"🔥 *Priority Score:* {lead_data['priority_score']}/5"
    )
    
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    requests.post(url, json={"chat_id": chat_id, "text": message, "parse_mode": "Markdown"})

# -------------------------------------------------------------------
# ORCHESTRATION (The Real-Time Loop)
# -------------------------------------------------------------------
if __name__ == "__main__":
    print("=== INITIALIZING AGENT P (V8.0 - STREAM EDITION) ===")
    
    raw_data = fetch_market_signals()
    
    if raw_data:
        roster = process_leads_with_agent_p(raw_data)
        
        # Check if the intelligence layer returned a list of leads
        if roster and "leads" in roster and roster["leads"]:
            total_leads = len(roster["leads"])
            print(f"🎯 Target Acquisition Protocol successful. {total_leads} targets locked.\n")
            
            # THE LOOP: Process and push one at a time
            for i, lead in enumerate(roster["leads"], 1):
                print(f"--- TARGET {i}/{total_leads} ---")
                print(json.dumps(lead, indent=4))
                push_to_telegram(lead)
                print(f"📱 Target {i} forwarded to Telegram.\n")
                
        else:
            print("No actionable targets identified today.")
