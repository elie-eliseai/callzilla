#!/usr/bin/env python3
"""
Create complex call trees using TwiML Bins (Twilio-hosted)
These should work better than Flask webhooks for testing
"""

import os
from twilio.rest import Client
from dotenv import load_dotenv

load_dotenv()

# Twilio credentials
account_sid = os.getenv('TWILIO_ACCOUNT_SID')
auth_token = os.getenv('TWILIO_AUTH_TOKEN')
client = Client(account_sid, auth_token)

# Your phone number for human endpoint
HUMAN_NUMBER = "+12022158237"


def create_bin(friendly_name, twiml_content):
    """Create a TwiML Bin and return its URL"""
    try:
        # Check if bin already exists
        bins = client.serverless.services.list()
        # TwiML Bins are accessed differently - via the main API
        
        # Create the TwiML Bin
        twiml_bin = client.studio.v2.twiml_bins.create(
            friendly_name=friendly_name,
            twiml=twiml_content
        )
        print(f"✅ Created: {friendly_name}")
        print(f"   URL: {twiml_bin.url}")
        return twiml_bin.url
    except Exception as e:
        # Try alternative API endpoint
        pass
    
    # Alternative: Use the TwiML Bins API directly
    try:
        from twilio.rest import Client
        twiml_bin = client.messaging.v1.twiml_bins.create(
            friendly_name=friendly_name,
            twiml=twiml_content
        )
        print(f"✅ Created: {friendly_name}")
        return twiml_bin.url
    except Exception as e2:
        print(f"❌ Error creating {friendly_name}: {e2}")
        return None


def build_complex_tree():
    """Build a complex multi-layer call tree using TwiML Bins"""
    
    print("\n" + "="*70)
    print("🌳 Creating Complex Test Call Tree via TwiML Bins")
    print("="*70 + "\n")
    
    # Build from bottom up (endpoints first, then menus that reference them)
    
    # ===== ENDPOINTS =====
    
    # Human transfer endpoint
    human_twiml = f'''<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say voice="Polly.Joanna">Please hold while we connect you to a leasing specialist.</Say>
    <Dial>{HUMAN_NUMBER}</Dial>
</Response>'''
    
    # Voicemail endpoint
    voicemail_twiml = '''<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say voice="Polly.Joanna">You've reached the leasing office voicemail. We're currently assisting other callers. Please leave your name, number, and a brief message after the tone.</Say>
    <Pause length="1"/>
    <Say voice="Polly.Joanna">Beep!</Say>
    <Record maxLength="60" />
</Response>'''
    
    # AI Assistant endpoint
    ai_twiml = '''<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say voice="Polly.Joanna">Hi! I'm Mia, your Virtual Leasing Assistant powered by EliseAI. I can help you with pricing, availability, scheduling tours, and more. What can I help you with today?</Say>
    <Pause length="5"/>
    <Say voice="Polly.Joanna">I didn't catch that. Feel free to ask about our apartments, or say agent to speak with someone.</Say>
    <Pause length="5"/>
    <Say voice="Polly.Joanna">Let me connect you with a team member.</Say>
    <Dial>+12022158237</Dial>
</Response>'''
    
    # Info endpoints (voicemail-like)
    rates_twiml = '''<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say voice="Polly.Joanna">Our current rental rates are as follows: Studio apartments start at $1,200 per month. One bedroom apartments range from $1,450 to $1,650. Two bedroom apartments start at $1,850. Three bedroom townhomes are available starting at $2,400. All rates are subject to availability and may vary based on floor plan and move-in date. For the most current pricing, please visit our website or speak with a leasing consultant.</Say>
    <Pause length="2"/>
    <Say voice="Polly.Joanna">To speak with a leasing specialist, press 1. To return to the main menu, press 9.</Say>
    <Gather numDigits="1" timeout="10">
    </Gather>
</Response>'''
    
    # Create endpoints
    print("📍 Creating endpoints...")
    
    bins = {}
    bins['human'] = create_bin("Test-Human-Transfer", human_twiml)
    bins['voicemail'] = create_bin("Test-Voicemail", voicemail_twiml)
    bins['ai'] = create_bin("Test-AI-Assistant", ai_twiml)
    bins['rates'] = create_bin("Test-Rates-Info", rates_twiml)
    
    print("\n" + "-"*70 + "\n")
    
    # ===== LAYER 3 - Deep menus =====
    print("📍 Creating Layer 3 menus...")
    
    # Application status submenu
    application_twiml = f'''<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Gather numDigits="1" timeout="10" action="">
        <Say voice="Polly.Joanna">Application Status Menu. Press 1 to check the status of your application online - visit our website and click My Application. Press 2 to speak with our application processing team. Press 3 to request a call back within 24 hours.</Say>
    </Gather>
    <Say voice="Polly.Joanna">We didn't get your selection.</Say>
    <Redirect></Redirect>
</Response>'''
    
    # Tour scheduling submenu
    tours_twiml = f'''<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Gather numDigits="1" timeout="10" input="dtmf speech" hints="virtual, in person, self guided">
        <Say voice="Polly.Joanna">Tour Scheduling. Press 1 for a self-guided tour - available 7 days a week from 9 AM to 6 PM. Press 2 to schedule an in-person tour with a leasing agent. Or say virtual for a virtual tour option.</Say>
    </Gather>
    <Say voice="Polly.Joanna">Sorry, I didn't catch that.</Say>
    <Redirect></Redirect>
</Response>'''
    
    bins['application'] = create_bin("Test-Application-Menu", application_twiml)
    bins['tours'] = create_bin("Test-Tours-Menu", tours_twiml)
    
    print("\n" + "-"*70 + "\n")
    
    # ===== LAYER 2 =====
    print("📍 Creating Layer 2 menus...")
    
    # Leasing submenu (the correct path)
    leasing_twiml = f'''<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Gather numDigits="1" timeout="10">
        <Say voice="Polly.Joanna">Leasing Department. Press 1 for current rental rates and availability. Press 2 to check application status. Press 3 to schedule a tour. Press 4 to speak with a leasing consultant now.</Say>
    </Gather>
    <Say voice="Polly.Joanna">I'm sorry, we didn't receive your selection.</Say>
    <Redirect></Redirect>
</Response>'''
    
    # Current residents (TRAP - not leasing!)
    residents_twiml = f'''<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Gather numDigits="1" timeout="10">
        <Say voice="Polly.Joanna">Current Residents Menu. Press 1 for rent payment options. Press 2 for lease renewal information. Press 3 to submit a maintenance request. Press 4 to reach the resident services team.</Say>
    </Gather>
    <Say voice="Polly.Joanna">Please make a selection.</Say>
    <Redirect></Redirect>
</Response>'''
    
    bins['leasing'] = create_bin("Test-Leasing-Menu", leasing_twiml)
    bins['residents'] = create_bin("Test-Residents-Menu", residents_twiml)
    
    print("\n" + "-"*70 + "\n")
    
    # ===== LAYER 1 - Main Menu =====
    print("📍 Creating Main Menu (Layer 1)...")
    
    main_twiml = f'''<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Gather numDigits="1" timeout="10" input="dtmf speech" hints="leasing, residents, maintenance">
        <Say voice="Polly.Joanna">Thank you for calling Sunset Ridge Apartments, where luxury meets convenience. Press 1 or say leasing for leasing and availability. Press 2 for current residents. Press 3 or say maintenance for maintenance requests. Press 0 to speak with an operator.</Say>
    </Gather>
    <Say voice="Polly.Joanna">We didn't receive your selection. Please try again.</Say>
    <Redirect></Redirect>
</Response>'''
    
    bins['main'] = create_bin("Test-Main-Menu", main_twiml)
    
    # ===== SUMMARY =====
    print("\n" + "="*70)
    print("✅ CALL TREE CREATED!")
    print("="*70)
    print("\n📋 STRUCTURE:")
    print("""
    MAIN MENU
    ├── 1: Leasing
    │   ├── 1: Rates Info (voicemail-like)
    │   ├── 2: Application Status
    │   │   ├── 1: Online instructions
    │   │   ├── 2: Transfer to human
    │   │   └── 3: Callback request
    │   ├── 3: Tour Scheduling
    │   │   ├── 1: Self-guided info
    │   │   ├── 2: Transfer to human
    │   │   └── "virtual": Virtual tour info
    │   └── 4: Transfer to Human ← CORRECT PATH
    │
    ├── 2: Current Residents (TRAP!)
    │   ├── 1: Rent payment
    │   ├── 2: Lease renewal (NOT new leasing!)
    │   ├── 3: Maintenance
    │   └── 4: Resident services
    │
    ├── 3: Maintenance → Voicemail
    │
    └── 0: Operator → Hold → Human
    """)
    
    print("\n🔗 MAIN MENU URL (configure on your Twilio number):")
    if bins.get('main'):
        print(f"   {bins['main']}")
    
    print("\n📱 CORRECT PATH TO LEASING HUMAN: Press 1 → Press 4")
    
    return bins


if __name__ == "__main__":
    # Check for credentials
    if not account_sid or not auth_token:
        print("❌ Missing TWILIO_ACCOUNT_SID or TWILIO_AUTH_TOKEN in .env")
        exit(1)
    
    print(f"🔑 Using account: {account_sid}")
    
    # Build the tree
    bins = build_complex_tree()









