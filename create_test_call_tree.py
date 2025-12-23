#!/usr/bin/env python3
"""
Create Ultimate Test Call Tree
Adds routes to Flask app for comprehensive call tree testing
"""

TEST_ROUTES = '''
# =============================================================================
# ULTIMATE TEST CALL TREE
# =============================================================================

HUMAN_NUMBER = '+12022158237'

@app.route('/test/main', methods=['GET', 'POST'])
def test_main_menu():
    """Layer 1 - Main Menu"""
    response = VoiceResponse()
    
    # Check if digit was pressed
    digit = request.values.get('Digits', '')
    speech = request.values.get('SpeechResult', '').lower()
    
    if digit == '1' or 'leasing' in speech:
        response.redirect('/test/leasing')
    elif digit == '2':
        response.redirect('/test/residents')
    elif digit == '3' or 'maintenance' in speech:
        response.redirect('/test/maintenance')
    elif digit == '0' or 'operator' in speech:
        response.redirect('/test/hold')
    else:
        gather = response.gather(
            input='dtmf speech',
            num_digits=1,
            timeout=10,
            action='/test/main',
            hints='leasing, maintenance, operator'
        )
        gather.say(
            "Thank you for calling Test Apartments, your luxury living destination. "
            "Press 1 or say leasing for leasing information. "
            "Press 2 for current residents. "
            "Press 3 or say maintenance for maintenance requests. "
            "Press 0 or say operator to speak with an operator.",
            voice='Polly.Joanna'
        )
        response.say("We didn't receive your selection. Please try again.", voice='Polly.Joanna')
        response.redirect('/test/main')
    
    return Response(str(response), mimetype='text/xml')


@app.route('/test/leasing', methods=['GET', 'POST'])
def test_leasing():
    """Layer 2 - Leasing Submenu"""
    response = VoiceResponse()
    digit = request.values.get('Digits', '')
    
    if digit == '1':
        response.redirect('/test/info/rates')
    elif digit == '2':
        response.redirect('/test/application')
    elif digit == '3':
        response.redirect('/test/tours')
    elif digit == '4':
        response.redirect('/test/human')
    else:
        gather = response.gather(
            input='dtmf',
            num_digits=1,
            timeout=10,
            action='/test/leasing'
        )
        gather.say(
            "Leasing department. "
            "Press 1 for rental rates and availability. "
            "Press 2 to check your application status. "
            "Press 3 to schedule a tour. "
            "Press 4 to speak directly with a leasing agent.",
            voice='Polly.Joanna'
        )
        response.say("We didn't receive your selection. Goodbye.", voice='Polly.Joanna')
        response.hangup()
    
    return Response(str(response), mimetype='text/xml')


@app.route('/test/residents', methods=['GET', 'POST'])
def test_residents():
    """Layer 2B - Current Residents (TRAP - mentions lease renewal)"""
    response = VoiceResponse()
    digit = request.values.get('Digits', '')
    
    if digit == '1':
        response.redirect('/test/info/rent')
    elif digit == '2':
        # TRAP: "Lease renewal" sounds like leasing but goes to AI assistant!
        response.redirect('/test/ai')
    else:
        gather = response.gather(
            input='dtmf',
            num_digits=1,
            timeout=10,
            action='/test/residents'
        )
        gather.say(
            "Current resident services. "
            "Press 1 to pay rent or view your account. "
            "Press 2 for lease renewal options.",
            voice='Polly.Joanna'
        )
        response.say("Returning to main menu.", voice='Polly.Joanna')
        response.redirect('/test/main')
    
    return Response(str(response), mimetype='text/xml')


@app.route('/test/application', methods=['GET', 'POST'])
def test_application():
    """Layer 3 - Application Status"""
    response = VoiceResponse()
    digit = request.values.get('Digits', '')
    
    if digit == '1':
        response.redirect('/test/human')
    elif digit == '2':
        response.redirect('/test/info/online')
    else:
        gather = response.gather(
            input='dtmf',
            num_digits=1,
            timeout=10,
            action='/test/application'
        )
        gather.say(
            "Application status options. "
            "Press 1 to check your status by phone with an agent. "
            "Press 2 to learn how to check your status online.",
            voice='Polly.Joanna'
        )
        response.redirect('/test/info/online')
    
    return Response(str(response), mimetype='text/xml')


@app.route('/test/tours', methods=['GET', 'POST'])
def test_tours():
    """Layer 3B - Tour Scheduling (with voice option)"""
    response = VoiceResponse()
    digit = request.values.get('Digits', '')
    speech = request.values.get('SpeechResult', '').lower()
    
    if digit == '1':
        response.redirect('/test/info/selfguided')
    elif digit == '2':
        response.redirect('/test/human')
    elif 'virtual' in speech:
        response.redirect('/test/info/virtual')
    else:
        gather = response.gather(
            input='dtmf speech',
            num_digits=1,
            timeout=10,
            action='/test/tours',
            hints='virtual'
        )
        gather.say(
            "Tour scheduling options. "
            "Press 1 for self-guided tour information. "
            "Press 2 to schedule an in-person tour with an agent. "
            "Or say virtual for virtual tour information.",
            voice='Polly.Joanna'
        )
        response.say("I didn't get that. Let me connect you with someone who can help.", voice='Polly.Joanna')
        response.redirect('/test/human')
    
    return Response(str(response), mimetype='text/xml')


# =============================================================================
# ENDPOINTS
# =============================================================================

@app.route('/test/human', methods=['GET', 'POST'])
def test_human():
    """Transfer to human"""
    response = VoiceResponse()
    response.say("Please hold while we connect you to a leasing agent.", voice='Polly.Joanna')
    response.dial(HUMAN_NUMBER)
    return Response(str(response), mimetype='text/xml')


@app.route('/test/maintenance', methods=['GET', 'POST'])
def test_maintenance():
    """Voicemail - Maintenance"""
    response = VoiceResponse()
    response.say(
        "You've reached the maintenance department. Our technicians are currently assisting other residents. "
        "Please leave your name, unit number, and a description of the issue after the tone. "
        "We will return your call within 24 hours. Thank you.",
        voice='Polly.Joanna'
    )
    response.pause(length=1)
    response.say("Beep!", voice='Polly.Joanna')
    response.record(max_length=30)
    return Response(str(response), mimetype='text/xml')


@app.route('/test/hold', methods=['GET', 'POST'])
def test_hold():
    """Hold for operator"""
    response = VoiceResponse()
    response.say(
        "Please hold for the next available representative. Your call is important to us.",
        voice='Polly.Joanna'
    )
    response.pause(length=10)
    response.say(
        "Thank you for holding. All of our representatives are still busy. Please continue to hold.",
        voice='Polly.Joanna'
    )
    response.dial(HUMAN_NUMBER)
    return Response(str(response), mimetype='text/xml')


@app.route('/test/ai', methods=['GET', 'POST'])
def test_ai():
    """AI Assistant simulation"""
    response = VoiceResponse()
    response.say(
        "Hi! I'm Mia, your virtual leasing assistant at Test Apartments. "
        "I can help you with questions about pricing, availability, amenities, and more. "
        "How can I assist you today?",
        voice='Polly.Joanna'
    )
    response.pause(length=5)
    response.say(
        "I'm sorry, I didn't catch that. Feel free to ask me anything about Test Apartments, "
        "or say agent to speak with a human representative.",
        voice='Polly.Joanna'
    )
    response.pause(length=5)
    response.say("I'll connect you with a team member. Please hold.", voice='Polly.Joanna')
    response.dial(HUMAN_NUMBER)
    return Response(str(response), mimetype='text/xml')


# =============================================================================
# INFO MESSAGES (Voicemail-like endpoints)
# =============================================================================

@app.route('/test/info/rates', methods=['GET', 'POST'])
def test_info_rates():
    """Info - Rental Rates"""
    response = VoiceResponse()
    response.say(
        "Thank you for your interest in Test Apartments. Our current rental rates are as follows: "
        "Studio apartments start at 1200 dollars per month. "
        "One bedroom apartments start at 1500 dollars. "
        "Two bedroom apartments start at 1900 dollars. "
        "For the most up to date availability, please visit our website at test apartments dot com. "
        "Have a great day!",
        voice='Polly.Joanna'
    )
    response.hangup()
    return Response(str(response), mimetype='text/xml')


@app.route('/test/info/rent', methods=['GET', 'POST'])
def test_info_rent():
    """Info - Pay Rent"""
    response = VoiceResponse()
    response.say(
        "To pay your rent online, please visit our resident portal at test apartments dot com slash residents. "
        "You can also drop off a check at the leasing office during business hours, Monday through Friday, 9 AM to 6 PM. "
        "If you have questions about your account, please leave a message and we will call you back. Thank you.",
        voice='Polly.Joanna'
    )
    response.hangup()
    return Response(str(response), mimetype='text/xml')


@app.route('/test/info/online', methods=['GET', 'POST'])
def test_info_online():
    """Info - Online Application Check"""
    response = VoiceResponse()
    response.say(
        "To check your application status online, please visit test apartments dot com slash apply "
        "and enter your confirmation number. Our office hours are Monday through Friday, 9 AM to 6 PM. "
        "Thank you for choosing Test Apartments. Goodbye.",
        voice='Polly.Joanna'
    )
    response.hangup()
    return Response(str(response), mimetype='text/xml')


@app.route('/test/info/selfguided', methods=['GET', 'POST'])
def test_info_selfguided():
    """Info - Self Guided Tours"""
    response = VoiceResponse()
    response.say(
        "Self-guided tours are available 7 days a week from 8 AM to 8 PM. "
        "To access a self-guided tour, download our app or visit our website to request a tour code. "
        "The code will be sent to your phone and is valid for 24 hours. "
        "Thank you for your interest. Have a wonderful day!",
        voice='Polly.Joanna'
    )
    response.hangup()
    return Response(str(response), mimetype='text/xml')


@app.route('/test/info/virtual', methods=['GET', 'POST'])
def test_info_virtual():
    """Info - Virtual Tours"""
    response = VoiceResponse()
    response.say(
        "Virtual tours are available on our website at test apartments dot com slash virtual tour. "
        "You can explore all of our floor plans in 3D from the comfort of your home. "
        "If you have questions during your virtual tour, use the chat feature to connect with a leasing agent. "
        "Thank you!",
        voice='Polly.Joanna'
    )
    response.hangup()
    return Response(str(response), mimetype='text/xml')

'''

def main():
    print("\n" + "="*70)
    print("🌳 Ultimate Test Call Tree Setup")
    print("="*70)
    
    # Read current app.py
    with open('/Users/eliesalem/Downloads/Voice_Automation/app.py', 'r') as f:
        current_content = f.read()
    
    # Check if test routes already exist
    if '/test/main' in current_content:
        print("\n⚠️  Test routes already exist in app.py!")
        print("   To reset, manually remove the test routes from app.py")
        return
    
    # Add test routes before the final if __name__ block
    if "if __name__ == '__main__':" in current_content:
        new_content = current_content.replace(
            "if __name__ == '__main__':",
            TEST_ROUTES + "\n\nif __name__ == '__main__':"
        )
    else:
        new_content = current_content + TEST_ROUTES
    
    # Write updated app.py
    with open('/Users/eliesalem/Downloads/Voice_Automation/app.py', 'w') as f:
        f.write(new_content)
    
    print("\n✅ Test routes added to app.py!")
    print("\n" + "="*70)
    print("📋 TEST CALL TREE STRUCTURE")
    print("="*70)
    print("""
LAYER 1 - Main Menu (/test/main)
├── Press 1 or say "leasing": Leasing → Layer 2
├── Press 2: Current Residents → Layer 2B (TRAP!)
├── Press 3 or say "maintenance": Maintenance Voicemail
└── Press 0 or say "operator": Hold for Operator

LAYER 2 - Leasing (/test/leasing)
├── Press 1: Rental Rates Info (voicemail-like)
├── Press 2: Application Status → Layer 3
├── Press 3: Tour Scheduling → Layer 3B
└── Press 4: Transfer to Human (+12022158237)

LAYER 2B - Current Residents (/test/residents) - TRAP!
├── Press 1: Pay Rent Info
└── Press 2: "Lease Renewal" → AI ASSISTANT (not leasing!)

LAYER 3 - Application Status (/test/application)
├── Press 1: Transfer to Human
└── Press 2: Online Check Info

LAYER 3B - Tour Scheduling (/test/tours)
├── Press 1: Self-Guided Tour Info
├── Press 2: Transfer to Human
└── Say "virtual": Virtual Tour Info

ENDPOINTS:
├── /test/human → Transfers to +12022158237
├── /test/maintenance → Voicemail message
├── /test/hold → "Please hold" then transfer
├── /test/ai → "Hi, I'm Mia, your virtual assistant..."
└── /test/info/* → Various info messages (voicemail-like)
""")
    
    print("="*70)
    print("🚀 TO USE THE TEST CALL TREE:")
    print("="*70)
    print("""
1. Restart Flask:
   cd /Users/eliesalem/Downloads/Voice_Automation && python3 app.py

2. Configure a Twilio phone number:
   - Voice URL: https://your-ngrok-url.ngrok.io/test/main
   - Method: POST

3. Call the number and test all paths!

The correct path to reach leasing is: 1 → 4 (or 1 → 3 → 2)
The TRAP path (sounds like leasing but isn't): 2 → 2 (goes to AI assistant)
""")


if __name__ == "__main__":
    main()
