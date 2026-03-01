import os
import json
import csv
import requests
import smtplib
from datetime import datetime
from email.message import EmailMessage
from google import genai
from pydantic import BaseModel, Field

# -------------------------------------------------------------------
# 1. AGENT P: OUTPUT SCHEMA (The 10-Column TAP)
# -------------------------------------------------------------------
class HomologationLead(BaseModel):
    target_entity: str = Field(description="Name of the OEM, startup, or manufacturer.")
    hq_location: str = Field(description="Headquarters location (e.g., UAE, Netherlands, NCR, Taiwan).")
    product_category: str = Field(description="e-2W, e-3W, Battery, or Component.")
    intent_signal: str = Field(description="The trigger event (e.g., funding, India launch, import).")
    financial_health: str = Field(description="Mention of funding amounts or revenue.")
    estimated_timeline: str = Field(description="When are they launching or expanding?")
    key_decision_maker: str = Field(description="Name/Title of the CEO, CTO, or Head of India Ops.")
    kdm_digital_footprint: str = Field(description="Likely digital footprint or platform to reach them.")
    compliance_gap: str = Field(description="Why they need an Indian ICAT agent right now.")
    priority_score: int = Field(description="1 to 5 ranking. 5 is high funding/immediate launch.", ge=1, le=5)

# -------------------------------------------------------------------
# 2. INGESTION (Falls back to mock data if no NewsAPI key is found)
# -------------------------------------------------------------------
def fetch_market_signals():
    api_key = os.environ.get("NEWS_API_KEY")
    if not api_key:
        print("⚠️ No NEWS_API_KEY found. Running in Test Mode with mock data...")
        return """
        Press Release: Amsterdam-based 'AeroVolt Mobility' has just secured a $5M Series A round 
        to expand its premium electric 2-wheeler operations into the Indian market. 
        CEO Martijn Van Der Berg stated the company is finalizing its supply chain in Delhi NCR 
        and aims for a Q3 launch. Experts note European battery enclosures face strict 
        thermal propagation testing under India's AIS-156 Amendment 3 regulations.
        """
    
    url = f"https://newsapi.org/v2/everything?q=(EV OR Mobility OR Battery) AND (India OR NCR) AND (Launch OR Expand OR Funded)&sortBy=publishedAt&apiKey={api_key}"
    try:
        response = requests.get(url)
        response.raise_for_status()
        articles = response.json().get('articles', [])
        return "\n".join([f"- {a['title']}: {a['description']}" for a in articles[:10]])
    except Exception as e:
        print(f"Ingestion Error: {e}")
        return ""

# -------------------------------------------------------------------
# 3. INTELLIGENCE: GEMINI 2.5 FLASH
# -------------------------------------------------------------------
def process_leads_with_agent_p(raw_text):
    print("🧠 Agent P is scanning the perimeter...")
    client = genai.Client() # Uses the GEMINI_API_KEY environment variable
    
    prompt = f"""
    You are Agent P, a Strategic Lead Architect. Analyze the following market news.
    Identify any company that will likely require automotive homologation (ICAT/ARAI) in India soon. 
    Extract the details strictly into the defined JSON schema. If no valid leads, return nothing.
    
    Raw Market Data:
    {raw_text}
    """
    
    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=genai.types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=HomologationLead,
                temperature=0.1 
            ),
        )
        return json.loads(response.text)
    except Exception as e:
        print(f"Agent P Processing Error: {e}")
        return None

# -------------------------------------------------------------------
# 4. STORAGE: APPEND TO EXCEL-READY CSV
# -------------------------------------------------------------------
def save_lead_to_csv(lead_data, filename="homologation_leads.csv"):
    if not lead_data: return filename
    
    file_exists = os.path.isfile(filename)
    headers = list(lead_data.keys())
    
    with open(filename, mode='a', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        if not file_exists:
            writer.writeheader()
        writer.writerow(lead_data)
    
    print(f"✅ Lead successfully appended to {filename}")
    return filename

# -------------------------------------------------------------------
# 5. DELIVERY: TELEGRAM PUSH NOTIFICATION
# -------------------------------------------------------------------
def push_to_telegram(lead_data):
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    
    if not bot_token or not chat_id:
        print("⚠️ Telegram credentials not set. Skipping push notification.")
        return

    message = (
        f"🚨 *AGENT P: NEW TAP ACQUIRED* 🚨\n\n"
        f"🏢 *Target:* {lead_data['target_entity']} ({lead_data['hq_location']})\n"
        f"🔋 *Category:* {lead_data['product_category']}\n"
        f"🎯 *Signal:* {lead_data['intent_signal']}\n"
        f"⚠️ *Gap:* {lead_data['compliance_gap']}\n"
        f"🔥 *Priority Score:* {lead_data['priority_score']}/5"
    )
    
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    requests.post(url, json={"chat_id": chat_id, "text": message, "parse_mode": "Markdown"})
    print("📱 High-priority lead forwarded to Telegram.")

# -------------------------------------------------------------------
# 6. DISPATCH: WEEKLY SMTP EMAIL TO AGENT
# -------------------------------------------------------------------
def email_csv_to_agent(csv_filename):
    """Emails the CSV file. Designed to run only on Fridays."""
    today = datetime.today()
    if today.weekday() != 4: # 4 = Friday
        print("⏳ Not Friday. Skipping weekly CSV email dispatch.")
        return

    sender_email = os.environ.get("SMTP_EMAIL")
    sender_password = os.environ.get("SMTP_APP_PASSWORD") # Use an App Password, not main password
    agent_email = "agent.contact@example.com" # Replace with your agent's actual email
    
    if not sender_email or not sender_password:
        print("⚠️ SMTP credentials not set. Skipping email dispatch.")
        return

    print(f"📧 It's Friday. Preparing to dispatch {csv_filename} to {agent_email}...")
    
    msg = EmailMessage()
    msg['Subject'] = f"Agent P: Weekly ICAT Homologation Targets ({today.strftime('%Y-%m-%d')})"
    msg['From'] = sender_email
    msg['To'] = agent_email
    msg.set_content("Attached is the latest automated TAP intelligence for ICAT homologation targets.\n\n- Agent P")

    # Attach the CSV
    with open(csv_filename, 'rb') as f:
        file_data = f.read()
    msg.add_attachment(file_data, maintype='text', subtype='csv', filename=csv_filename)

    # Send via Gmail SMTP (Change to smtp-mail.outlook.com if using Outlook)
    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
            smtp.login(sender_email, sender_password)
            smtp.send_message(msg)
        print("✅ Weekly intelligence report successfully dispatched via SMTP.")
    except Exception as e:
        print(f"SMTP Dispatch Error: {e}")

# -------------------------------------------------------------------
# ORCHESTRATION (The "Wicket Keeper" Loop)
# -------------------------------------------------------------------
if __name__ == "__main__":
    print(f"=== INITIALIZING AGENT P (V7.0) ENGINE at {datetime.now().strftime('%H:%M:%S')} ===")
    
    # 1. Scrape
    raw_data = fetch_market_signals()
    
    # 2. Process
    if raw_data:
        lead = process_leads_with_agent_p(raw_data)
        
        # 3. Route
        if lead:
            print(json.dumps(lead, indent=4))
            csv_file = save_lead_to_csv(lead)
            push_to_telegram(lead)
            email_csv_to_agent(csv_file)
        else:
            print("No actionable homologation targets identified today.")
