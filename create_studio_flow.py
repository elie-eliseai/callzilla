#!/usr/bin/env python3
"""
Create a complex call tree using Twilio Studio Flow API
This creates flows programmatically - much faster than manual!
"""

import os
import json
from twilio.rest import Client
from dotenv import load_dotenv

load_dotenv()

account_sid = os.getenv('TWILIO_ACCOUNT_SID')
auth_token = os.getenv('TWILIO_AUTH_TOKEN')
client = Client(account_sid, auth_token)

HUMAN_NUMBER = "+12022158237"

def create_complex_flow():
    """Create a complex multi-layer call tree as a Studio Flow"""
    
    # Studio Flow Definition (JSON)
    # This defines a complex call tree with multiple layers
    
    flow_definition = {
        "description": "Complex Test Call Tree",
        "states": [
            # Initial trigger
            {
                "name": "Trigger",
                "type": "trigger",
                "transitions": [
                    {"event": "incomingMessage", "next": "main_menu"},
                    {"event": "incomingCall", "next": "main_menu"},
                    {"event": "incomingConversationMessage", "next": "main_menu"},
                    {"event": "incomingRequest", "next": "main_menu"}
                ],
                "properties": {
                    "offset": {"x": 0, "y": 0}
                }
            },
            
            # ========== LAYER 1: MAIN MENU ==========
            {
                "name": "main_menu",
                "type": "gather-input-on-call",
                "transitions": [
                    {"event": "keypress", "next": "main_menu_router"},
                    {"event": "speech", "next": "main_menu_router"},
                    {"event": "timeout", "next": "main_menu"}
                ],
                "properties": {
                    "voice": "Polly.Joanna",
                    "speech_timeout": "auto",
                    "offset": {"x": 0, "y": 200},
                    "loop": 1,
                    "hints": "leasing, residents, maintenance, operator",
                    "play": "",
                    "say": "Thank you for calling Sunset Ridge Apartments, where luxury meets convenience. Press 1 or say leasing for leasing information. Press 2 for current residents. Press 3 or say maintenance for maintenance requests. Press 0 to speak with an operator.",
                    "stop_gather": False,
                    "gather_language": "en-US",
                    "profanity_filter": "true",
                    "timeout": 10,
                    "number_of_digits": 1,
                    "finish_on_key": ""
                }
            },
            {
                "name": "main_menu_router",
                "type": "split-based-on",
                "transitions": [
                    {"event": "noMatch", "next": "main_menu"},
                    {"event": "match", "conditions": [{"friendly_name": "1_leasing", "arguments": ["{{widgets.main_menu.Digits}}"], "type": "equal_to", "value": "1"}], "next": "leasing_menu"},
                    {"event": "match", "conditions": [{"friendly_name": "2_residents", "arguments": ["{{widgets.main_menu.Digits}}"], "type": "equal_to", "value": "2"}], "next": "residents_menu"},
                    {"event": "match", "conditions": [{"friendly_name": "3_maintenance", "arguments": ["{{widgets.main_menu.Digits}}"], "type": "equal_to", "value": "3"}], "next": "maintenance_voicemail"},
                    {"event": "match", "conditions": [{"friendly_name": "0_operator", "arguments": ["{{widgets.main_menu.Digits}}"], "type": "equal_to", "value": "0"}], "next": "operator_hold"}
                ],
                "properties": {
                    "input": "{{widgets.main_menu.Digits}}",
                    "offset": {"x": 0, "y": 400}
                }
            },
            
            # ========== LAYER 2: LEASING MENU ==========
            {
                "name": "leasing_menu",
                "type": "gather-input-on-call",
                "transitions": [
                    {"event": "keypress", "next": "leasing_router"},
                    {"event": "speech", "next": "leasing_router"},
                    {"event": "timeout", "next": "leasing_menu"}
                ],
                "properties": {
                    "voice": "Polly.Joanna",
                    "speech_timeout": "auto",
                    "offset": {"x": -400, "y": 600},
                    "loop": 1,
                    "hints": "",
                    "play": "",
                    "say": "Leasing Department. Press 1 for current rental rates and special offers. Press 2 to check your application status. Press 3 to schedule a tour. Press 4 to speak with a leasing consultant right now.",
                    "stop_gather": False,
                    "gather_language": "en-US",
                    "timeout": 10,
                    "number_of_digits": 1
                }
            },
            {
                "name": "leasing_router",
                "type": "split-based-on",
                "transitions": [
                    {"event": "noMatch", "next": "leasing_menu"},
                    {"event": "match", "conditions": [{"friendly_name": "1_rates", "arguments": ["{{widgets.leasing_menu.Digits}}"], "type": "equal_to", "value": "1"}], "next": "rates_info"},
                    {"event": "match", "conditions": [{"friendly_name": "2_app", "arguments": ["{{widgets.leasing_menu.Digits}}"], "type": "equal_to", "value": "2"}], "next": "application_menu"},
                    {"event": "match", "conditions": [{"friendly_name": "3_tour", "arguments": ["{{widgets.leasing_menu.Digits}}"], "type": "equal_to", "value": "3"}], "next": "tours_menu"},
                    {"event": "match", "conditions": [{"friendly_name": "4_human", "arguments": ["{{widgets.leasing_menu.Digits}}"], "type": "equal_to", "value": "4"}], "next": "transfer_human"}
                ],
                "properties": {
                    "input": "{{widgets.leasing_menu.Digits}}",
                    "offset": {"x": -400, "y": 800}
                }
            },
            
            # ========== LAYER 2: RESIDENTS MENU (TRAP!) ==========
            {
                "name": "residents_menu",
                "type": "gather-input-on-call",
                "transitions": [
                    {"event": "keypress", "next": "residents_router"},
                    {"event": "speech", "next": "residents_router"},
                    {"event": "timeout", "next": "residents_menu"}
                ],
                "properties": {
                    "voice": "Polly.Joanna",
                    "offset": {"x": 0, "y": 600},
                    "say": "Current Residents Menu. Press 1 for rent payment options. Press 2 for lease renewal - this is NOT for new leases. Press 3 for maintenance. Press 4 for resident services.",
                    "timeout": 10,
                    "number_of_digits": 1
                }
            },
            {
                "name": "residents_router",
                "type": "split-based-on",
                "transitions": [
                    {"event": "noMatch", "next": "residents_menu"},
                    {"event": "match", "conditions": [{"friendly_name": "2_renewal", "arguments": ["{{widgets.residents_menu.Digits}}"], "type": "equal_to", "value": "2"}], "next": "ai_assistant"}
                ],
                "properties": {
                    "input": "{{widgets.residents_menu.Digits}}",
                    "offset": {"x": 0, "y": 800}
                }
            },
            
            # ========== LAYER 3: APPLICATION MENU ==========
            {
                "name": "application_menu",
                "type": "gather-input-on-call",
                "transitions": [
                    {"event": "keypress", "next": "application_router"},
                    {"event": "timeout", "next": "application_menu"}
                ],
                "properties": {
                    "voice": "Polly.Joanna",
                    "offset": {"x": -600, "y": 1000},
                    "say": "Application Status. Press 1 to check your status online at our website. Press 2 to speak with the application processing team.",
                    "timeout": 10,
                    "number_of_digits": 1
                }
            },
            {
                "name": "application_router",
                "type": "split-based-on",
                "transitions": [
                    {"event": "noMatch", "next": "application_menu"},
                    {"event": "match", "conditions": [{"friendly_name": "2_human", "arguments": ["{{widgets.application_menu.Digits}}"], "type": "equal_to", "value": "2"}], "next": "transfer_human"}
                ],
                "properties": {
                    "input": "{{widgets.application_menu.Digits}}",
                    "offset": {"x": -600, "y": 1200}
                }
            },
            
            # ========== LAYER 3: TOURS MENU ==========
            {
                "name": "tours_menu",
                "type": "gather-input-on-call",
                "transitions": [
                    {"event": "keypress", "next": "tours_router"},
                    {"event": "timeout", "next": "tours_menu"}
                ],
                "properties": {
                    "voice": "Polly.Joanna",
                    "offset": {"x": -200, "y": 1000},
                    "say": "Tour Scheduling. Press 1 for self-guided tour information. Press 2 to schedule an in-person tour with a leasing agent.",
                    "timeout": 10,
                    "number_of_digits": 1
                }
            },
            {
                "name": "tours_router",
                "type": "split-based-on",
                "transitions": [
                    {"event": "noMatch", "next": "tours_menu"},
                    {"event": "match", "conditions": [{"friendly_name": "2_human", "arguments": ["{{widgets.tours_menu.Digits}}"], "type": "equal_to", "value": "2"}], "next": "transfer_human"}
                ],
                "properties": {
                    "input": "{{widgets.tours_menu.Digits}}",
                    "offset": {"x": -200, "y": 1200}
                }
            },
            
            # ========== ENDPOINTS ==========
            
            # Rates Info (voicemail-like)
            {
                "name": "rates_info",
                "type": "say-play",
                "transitions": [
                    {"event": "audioComplete", "next": "leasing_menu"}
                ],
                "properties": {
                    "voice": "Polly.Joanna",
                    "offset": {"x": -800, "y": 1000},
                    "say": "Our current rental rates are as follows. Studios start at $1,200 per month. One bedrooms range from $1,450 to $1,650. Two bedrooms start at $1,850. Three bedroom townhomes begin at $2,400. Rates vary by floor plan and move-in date. For current specials, press 4 to speak with a leasing consultant."
                }
            },
            
            # Transfer to Human
            {
                "name": "transfer_human",
                "type": "connect-call-to",
                "transitions": [
                    {"event": "callCompleted"}
                ],
                "properties": {
                    "offset": {"x": -400, "y": 1400},
                    "caller_id": "{{contact.channel.address}}",
                    "noun": "number",
                    "to": HUMAN_NUMBER,
                    "timeout": 30
                }
            },
            
            # Maintenance Voicemail
            {
                "name": "maintenance_voicemail",
                "type": "say-play",
                "transitions": [
                    {"event": "audioComplete", "next": "record_vm"}
                ],
                "properties": {
                    "voice": "Polly.Joanna",
                    "offset": {"x": 400, "y": 600},
                    "say": "You've reached the maintenance department. Our technicians are currently assisting other residents. Please leave your name, unit number, and a detailed description of the issue after the tone. We will return your call within 24 hours."
                }
            },
            {
                "name": "record_vm",
                "type": "record-voicemail",
                "transitions": [
                    {"event": "recordingComplete"},
                    {"event": "timeout"}
                ],
                "properties": {
                    "offset": {"x": 400, "y": 800},
                    "max_length": 120,
                    "transcribe": False,
                    "play_beep": "true",
                    "timeout": 5
                }
            },
            
            # Operator Hold
            {
                "name": "operator_hold",
                "type": "say-play",
                "transitions": [
                    {"event": "audioComplete", "next": "transfer_human"}
                ],
                "properties": {
                    "voice": "Polly.Joanna",
                    "offset": {"x": 400, "y": 400},
                    "say": "Please hold while we connect you to the next available representative. Your call is important to us."
                }
            },
            
            # AI Assistant
            {
                "name": "ai_assistant",
                "type": "say-play",
                "transitions": [
                    {"event": "audioComplete", "next": "ai_wait"}
                ],
                "properties": {
                    "voice": "Polly.Joanna",
                    "offset": {"x": 200, "y": 1000},
                    "say": "Hi! I'm Mia, your Virtual Leasing Assistant powered by EliseAI. I can help answer questions about pricing, availability, amenities, and more. How can I help you today?"
                }
            },
            {
                "name": "ai_wait",
                "type": "gather-input-on-call",
                "transitions": [
                    {"event": "keypress", "next": "transfer_human"},
                    {"event": "speech", "next": "transfer_human"},
                    {"event": "timeout", "next": "ai_timeout"}
                ],
                "properties": {
                    "voice": "Polly.Joanna",
                    "offset": {"x": 200, "y": 1200},
                    "say": "",
                    "timeout": 5,
                    "number_of_digits": 1
                }
            },
            {
                "name": "ai_timeout",
                "type": "say-play",
                "transitions": [
                    {"event": "audioComplete", "next": "transfer_human"}
                ],
                "properties": {
                    "voice": "Polly.Joanna",
                    "offset": {"x": 200, "y": 1400},
                    "say": "I didn't catch that. Let me connect you with a team member."
                }
            }
        ],
        "initial_state": "Trigger",
        "flags": {
            "allow_concurrent_calls": True
        }
    }
    
    return flow_definition


def main():
    print("\n" + "="*70)
    print("🌳 Creating Complex Studio Flow via API")
    print("="*70 + "\n")
    
    flow_def = create_complex_flow()
    
    try:
        # Create the flow
        flow = client.studio.v2.flows.create(
            friendly_name="Complex Test Call Tree",
            status="published",
            definition=flow_def
        )
        
        print(f"✅ Flow created successfully!")
        print(f"   Flow SID: {flow.sid}")
        print(f"   Status: {flow.status}")
        print(f"\n📋 STRUCTURE:")
        print("""
    MAIN MENU (Layer 1)
    ├── 1: Leasing → Layer 2
    │   ├── 1: Rates Info (voicemail-like message)
    │   ├── 2: Application Status → Layer 3
    │   │   └── 2: Transfer to Human
    │   ├── 3: Tour Scheduling → Layer 3
    │   │   └── 2: Transfer to Human
    │   └── 4: Transfer to Human ← DIRECT PATH
    │
    ├── 2: Current Residents (TRAP - not leasing!)
    │   └── 2: "Lease Renewal" → AI Assistant (EliseAI!)
    │
    ├── 3: Maintenance → Voicemail
    │
    └── 0: Operator → Hold → Human
        """)
        print(f"\n🔗 To use this flow:")
        print(f"   1. Go to Twilio Console → Phone Numbers")
        print(f"   2. Select your test number")
        print(f"   3. Set 'A Call Comes In' to 'Studio Flow'")
        print(f"   4. Select 'Complex Test Call Tree'")
        print(f"\n📱 CORRECT PATH: 1 → 4")
        print(f"📱 AI ASSISTANT PATH: 2 → 2")
        
    except Exception as e:
        print(f"❌ Error creating flow: {e}")
        print(f"\n💡 You can also import the flow manually:")
        print(f"   1. Go to Twilio Console → Studio → Create Flow")
        print(f"   2. Choose 'Import from JSON'")
        print(f"   3. Paste the JSON below:\n")
        print(json.dumps(flow_def, indent=2)[:2000] + "\n... (truncated)")


if __name__ == "__main__":
    if not account_sid or not auth_token:
        print("❌ Missing credentials in .env")
        exit(1)
    
    main()









