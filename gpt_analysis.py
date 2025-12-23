"""
GPT Analysis Module - All GPT-based classification and validation functions.

This module contains:
- analyze_call_recording(): Main classifier for call types
- validate_call_result(): QA validation for call results
- detect_if_human(): Human vs machine detection
"""

from config import Config


def analyze_call_recording(transcription, previous_transcriptions=None):
    """
    GPT analysis of a phone call recording using example-based prompt.
    
    Returns: dict with 'classification', 'button', 'reasoning'
    
    Classifications:
    - 'call_tree': IVR routing menu (need to press button)
    - 'human': Real person answered
    - 'voicemail': Voicemail system
    - 'ai_assistant': AI/virtual leasing agent
    - 'out_of_service': Number disconnected/invalid
    """
    if not transcription or len(transcription) < 5:
        return {
            'classification': 'unknown',
            'is_call_tree': False,
            'is_human': False,
            'is_voicemail': False,
            'is_ai_assistant': False,
            'is_out_of_service': False,
            'button': None,
            'reasoning': 'Transcription too short'
        }
    
    try:
        from openai import OpenAI
        client = OpenAI(api_key=Config.OPENAI_API_KEY)
        
        prompt = f"""You are an expert at analyzing phone calls to apartment leasing offices.

We called an apartment property's phone number. Classify what answered.

## THE 5 CATEGORIES

### 1. VOICEMAIL
A pre-recorded message that provides information but doesn't invite live conversation.

**Example 1 - Office Info Message:**
"Thank you for calling Arizona Commons. Our address is 3653 East 2nd Street, Tucson, Arizona 85716. Our office hours are Monday through Friday, 8:30 to 5. Have a great day!"

**Why voicemail:** Scripted info dump. Ends with sign-off. No invitation to interact. Plays the same for every caller.

**Example 2 - Voicemail with menu (LOOKS like call tree but ISN'T):**
"You have reached the leasing office. No one is available to take your call. To leave a message, press 1. To page the on-call agent, press 2."

**Why voicemail, NOT call tree:** The options manage the VOICEMAIL (leave message, page) - they don't ROUTE to different departments like leasing/maintenance/billing.

**Example 3 - Carrier voicemail:**
"The subscriber you have dialed is not available. Please leave a message after the tone."

**Example 4 - After-hours message:**
"Our office is currently closed. Our hours are Monday through Friday, 9 AM to 6 PM. Please call back during business hours. Goodbye."

**Why voicemail:** Pre-recorded, provides hours, says goodbye. No live presence.

**Key insight:** The message ENDS. It provides info and concludes. No one is waiting for your response.

**Intent test:** Ask "If I said something right now, would it change what happens next?" For voicemail, the answer is NO - the message plays the same regardless of the caller.

Other indicators: "Please leave a message", "after the tone", "we're unable to take your call", "no one is available"

---

### 2. HUMAN
A real person who answered live and is present on the call.

**Example 1 - Informal greeting:**
"Hello? ... Hello? Anyone there?"

**Why human:** Informal, repeated, waiting for response. Machines don't pause and repeat "hello."

**Example 2 - Professional receptionist:**
"Good afternoon, Parkview Apartments, this is Jessica, how can I help you?"

**Why human:** Ends with a question inviting response. A live person is waiting for the caller to speak.

**Example 3 - Quick confused response:**
"Yeah? ... Who is this?"

**Why human:** Casual, reactive, confused. Shows real-time awareness.

**Example 4 - Short/empty transcript (hung up quickly):**
"Hello? ... [silence/end]"

**Why human:** Person picked up, heard our message, hung up. Machines don't hang up - they play their full message.

**Example 5 - Professional but reactive:**
"Sunset Apartments, please hold... okay, how can I help you?"

**Why human:** Dynamic response. They put someone on hold, came back, asked a question.

**Key insight:** They're PRESENT. They wait, they react, they ask questions, they get confused by silence. If the transcript shows awareness of the caller or waiting-for-response behavior, it's human.

**Intent test:** Ask "If I said something right now, would it change what happens next?" For a human, the answer is YES - they would respond to what you said.

---

### 3. CALL_TREE
An automated routing menu with explicit button or voice options.

**CRITICAL: Must have "press X" or "say X" options. No options = not a call tree.**

**Example:**
"Thank you for calling Sunset Apartments. Press 1 for leasing, press 2 for current residents, press 3 for maintenance."

**Why call tree:** Explicitly offers numbered ROUTING options to different departments.

**Not a call tree:** Generic greetings without options, hold music, informational messages, voicemail menus.

If CALL_TREE: identify which button lets us SPEAK with leasing (we want a voice conversation). Look for: leasing, new residents, prospective residents, rental info, sales. If none of those exist, use "speak to an agent" or "representative" as fallback.

---

### 4. AI_ASSISTANT
An AI-powered virtual assistant - identifies itself as AI/virtual.

**Key indicators:**
- "Hi, I'm [Name], your virtual leasing assistant"
- "I'm an AI assistant" / "I'm a virtual agent"
- Mentions being automated but offers conversational help
- Does NOT provide numbered routing options

**Common AI names:** Mia, Lisa, Elise, Emma (often with "virtual" or "AI" mentioned)

---

### 5. OUT_OF_SERVICE
The number doesn't work.

**Indicators:** "The number you have dialed is not in service", "This number has been disconnected", carrier error messages.

---

## THE KEY DISTINCTION: BROADCAST vs CONVERSATION

**Voicemails BROADCAST.** They transmit information one-way and end themselves. The caller is just a recipient.

**Humans CONVERSE.** They open a two-way channel and wait for the caller to participate. The caller is a participant.

| Signal | Voicemail | Human |
|--------|-----------|-------|
| Turn-taking | No turn expected from caller | "Your turn now" |
| Acknowledges caller | Plays regardless of who called | "Is someone there?" |
| Would change if you spoke | No, same message every time | Yes, would respond |
| Structure | Closed - ends with sign-off | Open - waits for response |
| Information flow | One-way TO caller | Two-way exchange |

---

## HOW TO DECIDE

Ask yourself:
1. Is there a live person present who's aware of and reactive to the caller? → HUMAN
2. Is it a scripted message that plays information and ends without inviting response? → VOICEMAIL
3. Does it offer "press X" or "say X" routing options? → CALL_TREE
4. Does it identify as AI/virtual? → AI_ASSISTANT
5. Is the number disconnected? → OUT_OF_SERVICE

---

## TRANSCRIPTION:
"{transcription[:2500]}"

---

## RESPONSE FORMAT (exactly 3 lines):
CLASSIFICATION: call_tree OR human OR voicemail OR ai_assistant OR out_of_service
BUTTON: [digit 0-9 if call_tree, otherwise "none"]
REASONING: [One sentence explaining your classification]
"""
        
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You classify phone call recordings. Focus on whether someone is PRESENT and REACTIVE (human) vs a pre-recorded message that just plays and ends (voicemail). Be precise."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=100,
            temperature=0.1
        )
        
        result = response.choices[0].message.content.strip()
        
        # Parse the response
        lines = result.split('\n')
        classification = 'unknown'
        button = None
        reasoning = ""
        
        for line in lines:
            line_lower = line.lower().strip()
            if line_lower.startswith('classification:'):
                class_value = line.split(':', 1)[1].strip().lower()
                if class_value in ['call_tree', 'human', 'voicemail', 'ai_assistant', 'out_of_service']:
                    classification = class_value
            elif line_lower.startswith('button:'):
                button_part = line.split(':', 1)[1].strip().lower()
                if button_part != 'none':
                    for char in button_part:
                        if char.isdigit():
                            button = char
                            break
            elif line_lower.startswith('reasoning:'):
                reasoning = line.split(':', 1)[1].strip()
        
        # Map classification to emoji and display
        emoji_map = {
            'call_tree': '🌳',
            'human': '👤',
            'voicemail': '📫',
            'ai_assistant': '🤖',
            'out_of_service': '❌'
        }
        emoji = emoji_map.get(classification, '❓')
        
        print(f"   🤖 GPT Analysis:")
        print(f"      Classification: {emoji} {classification.upper()}")
        if classification == 'call_tree' and button:
            print(f"      Button for leasing: '{button}'")
        print(f"      Reasoning: {reasoning}")
        
        return {
            'classification': classification,
            'is_call_tree': classification == 'call_tree',
            'is_human': classification == 'human',
            'is_voicemail': classification == 'voicemail',
            'is_ai_assistant': classification == 'ai_assistant',
            'is_out_of_service': classification == 'out_of_service',
            'button': button,
            'reasoning': reasoning
        }
        
    except Exception as e:
        print(f"\n   ❌ CRITICAL ERROR: GPT analysis failed!")
        print(f"   Error: {str(e)}")
        print(f"   Cannot continue without GPT classification.")
        raise SystemExit(f"GPT API error: {str(e)}")


def validate_call_result(property_name, transcription, classification):
    """
    Final sanity check GPT call to catch edge cases and anomalies.
    
    This is a SEPARATE call from the main classification to keep logic simple.
    It reviews the result and flags anything suspicious.
    
    Returns: dict with 'needs_review', 'issues', 'reasoning'
    """
    if not transcription or len(transcription) < 20:
        return {'needs_review': False, 'issues': [], 'reasoning': 'Transcript too short to validate'}
    
    try:
        from openai import OpenAI
        client = OpenAI(api_key=Config.OPENAI_API_KEY)
        
        prompt = f"""You are a quality assurance reviewer for apartment leasing call verification.

## YOUR TASK
Review this phone call result and flag ANY issues or anomalies.

## PROPERTY INFO
Expected Property: {property_name}
Classification: {classification}

## TRANSCRIPT
{transcription[:2000]}

## CHECK FOR THESE ISSUES

1. **WRONG_BUSINESS**: Does the transcript mention a completely different business?
   - Example: Expected "Beaumont Apartments" but heard "Joe Malkins Ford" → WRONG_BUSINESS
   - Example: Expected "Madison East" but heard "Picky Performance Cleaning" → WRONG_BUSINESS
   - Look for: business names, industries (car, cleaning, medical, etc.)

2. **NAME_MISMATCH**: Is the property name slightly different but same industry?
   - Example: Expected "Madison West" but heard "Madison East" → NAME_MISMATCH
   - This is less severe than WRONG_BUSINESS

3. **CONFUSED_ROUTING**: Does it seem like the call got routed incorrectly?
   - Multiple different business greetings in same call
   - Transfer to unexpected department

4. **HOLD_FOR_HUMAN**: Does the call tree say to stay on hold for a person?
   - "Stay on the line for a representative"
   - "Hold for the next available agent"
   - We can't detect when someone picks up after hold

5. **SUSPICIOUS_CLASSIFICATION**: Does the classification seem wrong?
   - Classified as voicemail but sounds like call tree
   - Classified as human but sounds automated

## RESPONSE FORMAT
Respond in this EXACT JSON format:
{{
    "needs_review": true/false,
    "issues": ["ISSUE_TYPE_1", "ISSUE_TYPE_2"],
    "reasoning": "Brief explanation of what's wrong or 'No issues detected'"
}}

If everything looks correct (property matches, classification makes sense), return needs_review: false with empty issues array.
"""
        
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=300,
            temperature=0
        )
        
        result_text = response.choices[0].message.content.strip()
        
        # Parse JSON response
        import json
        import re
        
        # Try to extract JSON from response
        json_match = re.search(r'\{.*\}', result_text, re.DOTALL)
        if json_match:
            result = json.loads(json_match.group())
            return {
                'needs_review': result.get('needs_review', False),
                'issues': result.get('issues', []),
                'reasoning': result.get('reasoning', '')
            }
        else:
            return {'needs_review': False, 'issues': [], 'reasoning': 'Could not parse validation response'}
            
    except Exception as e:
        print(f"   ⚠️  Validation GPT error: {str(e)}")
        return {'needs_review': False, 'issues': [], 'reasoning': f'Validation error: {str(e)}'}


def detect_if_human(transcription):
    """Use GPT to detect if a REAL HUMAN answered (not voicemail/menu/AI assistant)"""
    if not transcription or len(transcription) < 5:
        return False
    
    try:
        from openai import OpenAI
        client = OpenAI(api_key=Config.OPENAI_API_KEY)
        
        prompt = f"""You are analyzing a phone call transcription to determine if a REAL HUMAN answered.

## RULE 1: INFORMAL SPEECH = DEFINITELY HUMAN
If you see ANY of these, it's a HUMAN (no machine talks this way):
- "Hello?" "Hello? Hello?" (casual, repeated greetings)
- "Hi" "Yeah?" "What?" "Who is this?" "Who's calling?"
- "Um", "uh", "hold on", "let me check", "one sec"
- Short, casual responses without company names
- Confused or annoyed responses
- Any unscripted, natural speech
- Repeated greetings when no one responds

## RULE 2: FORMAL SPEECH COULD BE EITHER
Formal/professional speech could be a human receptionist OR a machine.
To determine which, look for MACHINE-ONLY indicators:

**MACHINE indicators (if you see these → MACHINE):**
- Mentions AI, virtual assistant, automated system: "I'm your virtual leasing assistant"
- Menu options: "press 1", "press 2", "say leasing"
- Voicemail instructions: "leave a message", "after the tone", "record your message"
- Introduces itself as AI: "Hi, this is [Name], your AI assistant"
- Robotic/unnatural flow

**HUMAN indicators (even in formal speech):**
- Natural variations in speech
- Responds to what caller says
- Small talk or pleasantries
- "How can I help you?" without menu options
- Professional but conversational

## EXAMPLES
- "Hello? Hello? Hello?" → HUMAN (informal, repeated greeting)
- "Good afternoon, ABC Apartments, this is Sarah, how can I help you?" → HUMAN (professional but natural)
- "Hi, I'm Mia, your virtual leasing assistant. How can I help you today?" → MACHINE (mentions virtual/AI)
- "Thank you for calling. Press 1 for leasing, press 2 for maintenance." → MACHINE (menu options)
- "Please leave a message after the tone." → MACHINE (voicemail)

## TRANSCRIPTION TO ANALYZE:
"{transcription[:1000]}"

## YOUR RESPONSE
Respond with ONLY one word: "human" or "machine"
"""
        
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You detect if a REAL HUMAN answered a phone call. Informal speech like 'Hello? Hello?' is HUMAN. Formal, scripted greetings are MACHINE. Respond with only 'human' or 'machine'."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=5,
            temperature=0.1
        )
        
        result = response.choices[0].message.content.strip().lower()
        is_human = 'human' in result
        
        # Additional check: if transcription has AI assistant keywords, definitely not human
        ai_keywords = [
            'virtual leasing agent',
            'ai assistant',
            'automated assistant',
            'virtual agent',
            'this is virtual',
            'can i help you',  # Common but check context
            'press 1',
            'press 2',
            'for leasing',
            'press one'
        ]
        transcription_lower = transcription.lower()
        has_ai_keywords = any(keyword in transcription_lower for keyword in ai_keywords)
        
        # If has AI keywords and transcription is structured, it's likely AI
        if has_ai_keywords and ('hi, this is' in transcription_lower or 'hi, can i help' in transcription_lower):
            print(f"   🤖 AI assistant detected (has AI keywords)")
            return False
        
        return is_human
        
    except Exception as e:
        print(f"   ⚠️ Human detection error: {str(e)}")
        # Fallback: check for AI keywords first
        transcription_lower = transcription.lower()
        ai_keywords = ['virtual leasing agent', 'ai assistant', 'virtual agent', 'press 1', 'press 2']
        if any(keyword in transcription_lower for keyword in ai_keywords):
            return False
        # Then check for human indicators
        human_indicators = ['um', 'uh', 'let me think', 'hold on', 'one moment']
        return any(indicator in transcription_lower for indicator in human_indicators)


# Backward compatibility aliases
def is_call_tree(transcription):
    """Wrapper for backward compatibility - uses GPT-based detection"""
    result = analyze_call_recording(transcription)
    return result['is_call_tree']


def determine_leasing_button(transcription):
    """Wrapper for backward compatibility - uses GPT-based detection"""
    result = analyze_call_recording(transcription)
    if result['is_call_tree'] and result['button']:
        return result['button'], None
    elif result['is_call_tree']:
        return None, result['reasoning']
    else:
        return None, "Not a call tree"


# Alias for backwards compatibility
analyze_call_tree = analyze_call_recording

