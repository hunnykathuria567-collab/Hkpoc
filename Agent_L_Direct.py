import os
import json
import csv
import requests
from google import genai
from pydantic import BaseModel, Field

# -------------------------------------------------------------------
# 1. AGENT L: OUTPUT SCHEMAS (NOW WITH URL & DATE)
# -------------------------------------------------------------------
class LoanLead(BaseModel):
    company_name: str = Field(description="Name of the Pvt Ltd / SME company.")
    target_type: str = Field(description="Put 'Target 1' or 'Target 2'. If unknown, put 'KDM'.")
    complete_name: str = Field(description="Name of the person. If not in snippet, MUST put 'Not Listed'.")
    contact_number: str = Field(description="Phone number. MUST put 'Not Listed'.")
    email: str = Field(description="Email address. MUST put 'Not Listed'.")
    office_address: str = Field(description="Location mentioned in snippet. If none, put 'Delhi NCR Region'.")
    proxy_signal: str = Field(description="The exact reason from the snippet (e.g., won a tender, expanding).")
    capital_need: str = Field(description="Estimate the need. If unknown, put 'Est. >₹1 Crore (Working Capital/CapEx)'.")
    the_play: str = Field(description="A 1-sentence pitch for Aditya Birla based on the signal.")
    source_link: str = Field(description="The exact URL of the news article or source.")
    publish_date: str = Field(description="The date the article was published.")

class LeadRoster(BaseModel):
    leads: list[LoanLead] = Field(description="List of extracted corporate leads.")

class ContactInfo(BaseModel):
    phone: str = Field(description="Extracted phone number, or 'Not Listed'.")
    email: str = Field(description="Extracted email address, or 'Not Listed'.")

# -------------------------------------------------------------------
# 2. INGESTION 1: THE "CRORE" GUARANTEE + METADATA EXTRACTION
# -------------------------------------------------------------------
def fetch_loan_signals():
    api_key = os.environ.get("SERPER_API_KEY")
    if not api_key: return "" 
    
    print("🌍 Phase 1: Scanning for 'Crore' level Expansions & Tenders...")
    url = "https://google.serper.dev/search"
    
    # V10 Payload: Perfectly escaped to prevent Serper 400 errors
    payload = json.dumps({
      "q": "\"Pvt Ltd\" AND \"Crore\" AND (\"expansion\" OR \"wins order\" OR \"NCLT\") AND (\"Delhi\" OR \"Noida\" OR \"Gurugram\" OR \"Haryana\")",
      "num": 40, 
      "tbs": "qdr:y" 
    })
    
    headers = {'X-API-KEY': api_key, 'Content-Type': 'application/json'}
    try:
        response = requests.post(url, headers=headers, data=payload)
        response.raise_for_status()
        results = response.json().get('organic', [])
        
        # CHANGED: Now feeding the Link and Date directly into the LLM prompt
        raw_text = "\n".join([f"- Title: {r.get('title')}\n  Snippet: {r.get('snippet')}\n  Link: {r.get('link')}\n  Date: {r.get('date', 'Recent')}\n" for r in results])
        return raw_text
    except Exception as e:
        print(f"Deep Search Error: {e}")
        return ""

# -------------------------------------------------------------------
# 3. INTELLIGENCE 1: SNIPPET-RESILIENT AI
# -------------------------------------------------------------------
def process_leads_with_agent_l(raw_text):
    if not raw_text.strip(): return None
    print("🧠 Phase 1: AI Reading Snippets & Extracting URLs...")
    client = genai.Client() 
    prompt = f"""
    You are Agent L. You are reading short Google search snippets. 
    
    CRITICAL INSTRUCTIONS:
    1. Do NOT drop a company just because a person's name or email is missing. Use "Not Listed".
    2. If a snippet mentions a company winning a contract/order, expanding a facility, or facing distress, EXTRACT IT.
    3. Since we searched for "Crore", assume the capital need is >₹1 Crore for execution/capex.
    4. Map the provided "Link" and "Date" directly to the source_link and publish_date fields.
    
    Extract every corporate entity you find that fits this criteria.
    
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
def enrich_contact_info(company_name):
    api_key = os.environ.get("SERPER_API_KEY")
    if not api_key: return {"phone": "Not Listed", "email": "Not Listed"}
    url = "https://google.serper.dev/search"
    payload = json.dumps({"q": f'"{company_name}" (email OR phone OR contact)', "num": 5})
    headers = {'X-API-KEY': api_key, 'Content-Type': 'application/json'}
    try:
        response = requests.post(url, headers=headers, data=payload)
        raw_contact_text = "\n".join([f"- {r.get('snippet')}" for r in response.json().get('organic', [])])
        client = genai.Client()
        ai_response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=f"Extract phone and email for {company_name} from this text. If not found, return 'Not Listed'. Text: {raw_contact_text}",
            config=genai.types.GenerateContentConfig(response_mime_type="application/json", response_schema=ContactInfo, temperature=0.1)
        )
        return json.loads(ai_response.text)
    except Exception:
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
    if not bot_token or not chat_id: return
    
    if lead_data['company_name'] == "No New SME Potential Found":
        message = f"🟢 *AGENT L: SYSTEM HEARTBEAT* 🟢\n\n*{lead_data['company_name']}*\nStatus: {lead_data['proxy_signal']}"
    else:
        message = (
            f"🏦 *AGENT L: TARGET ACQUIRED (>1Cr)* 🏦\n"
            f"🏢 *Company:* {lead_data['company_name']}\n"
            f"🎯 *Target:* {lead_data['target_type']} ({lead_data['complete_name']})\n"
            f"📞 *Contact:* {lead_data['contact_number']}\n"
            f"✉️ *Email:* {lead_data['email']}\n"
            f"📍 *Location:* {lead_data['office_address']}\n\n"
            f"📡 *Signal:* {lead_data['proxy_signal']}\n"
            f"💰 *Need:* {lead_data['capital_need']}\n"
            f"♟️ *Play:* {lead_data['the_play']}\n\n"
            f"🔗 *Source:* {lead_data['source_link']}\n"
            f"📅 *Published:* {lead_data['publish_date']}"
        )
    try:
        requests.post(f"https://api.telegram.org/bot{bot_token}/sendMessage", json={"chat_id": chat_id, "text": message})
    except Exception:
        pass

def push_dummy_lead():
    dummy_lead = {
        "company_name": "No New SME Potential Found",
        "target_type": "N/A", "complete_name": "System Status: Active", "contact_number": "N/A", "email": "N/A", "office_address": "N/A",
        "proxy_signal": "Engine ran successfully. No snippet matched the >1Cr criteria today.",
        "capital_need": "N/A", "the_play": "N/A", "source_link": "N/A", "publish_date": "N/A"
    }
    save_lead_to_csv(dummy_lead)
    push_to_telegram(dummy_lead)

# -------------------------------------------------------------------
# ORCHESTRATION 
# -------------------------------------------------------------------
if __name__ == "__main__":
    print("=== INITIALIZING AGENT L (V10 - URL & DATE EXTRACTION) ===\n")
    raw_data = fetch_loan_signals()
    
    if raw_data:
        roster = process_leads_with_agent_l(raw_data)
        if roster and "leads" in roster and len(roster["leads"]) > 0:
            target_leads = roster["leads"][:20] 
            for lead in target_leads:
                if lead['contact_number'] == "Not Listed" or lead['email'] == "Not Listed":
                    enriched_data = enrich_contact_info(lead['company_name'])
                    if enriched_data['phone'] != "Not Listed": lead['contact_number'] = enriched_data['phone']
                    if enriched_data['email'] != "Not Listed": lead['email'] = enriched_data['email']
                save_lead_to_csv(lead)
                push_to_telegram(lead)
        else:
            push_dummy_lead()
    else:
        push_dummy_lead()
