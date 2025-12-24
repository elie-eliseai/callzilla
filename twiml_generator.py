"""
TwiML Generator Module - All Twilio Markup Language generation functions.

This module creates TwiML for different call scenarios:
- Exploration calls (listening to identify phone system type)
- Button sequence navigation (pressing through call trees)
- Legacy phone tree navigation
"""

from twilio.twiml.voice_response import VoiceResponse
from config import Config


def estimate_tts_duration(text):
    """
    Estimate how long the TTS message takes to speak.
    Average speaking rate is about 150 words per minute (2.5 words per second).
    """
    word_count = len(text.split())
    estimated_seconds = word_count / 2.5
    # Add a small buffer
    return int(estimated_seconds) + 2


def create_exploration_twiml(webhook_base_url=None):
    """
    Create TwiML that listens to explore what the phone system says.
    
    Uses speech detection to wait for 1 sec of silence before playing TTS.
    Falls back to <Record> to keep call alive after TTS plays.
    """
    response = VoiceResponse()
    
    if webhook_base_url:
        # Use speech detection - wait for them to finish talking + 1 sec silence
        gather = response.gather(
            input='speech',
            timeout=15,
            action=f'{webhook_base_url}/voice/speech-detected',
            method='POST',
            speech_timeout=1
        )
        gather.pause(length=15)
        response.redirect(f'{webhook_base_url}/voice/no-speech', method='POST')
    else:
        # Fallback: fixed timing if no webhook
        response.pause(length=1.5)
        response.say(Config.HUMAN_MESSAGE, voice='Polly.Joanna', language='en-US')
        response.record(timeout=10, max_length=90, play_beep=False)
        response.hangup()
    
    return str(response)


def create_button_sequence_twiml(button_sequence, webhook_base_url=None):
    """
    Create TwiML that presses a sequence of buttons with proper timing.
    
    Args:
        button_sequence: list of dicts like [{'wait': 10, 'press': '1'}, {'wait': 8, 'press': '2'}]
        webhook_base_url: Base URL for webhooks (e.g., https://abc123.ngrok.io)
    
    Timing logic:
    - We stay SILENT during menu navigation
    - Button presses happen at calculated times from call start
    - After buttons, we use <Gather> to detect speech
    - When speech detected → webhook triggers TTS (human hears it!)
    """
    response = VoiceResponse()
    
    # Brief pause for connection
    response.pause(length=1)
    elapsed_time = 1
    
    # Execute the button sequence with proper timing (SILENT - no TTS yet)
    for step in button_sequence:
        target_time = step.get('wait', 8)  # When button should be pressed from call start
        button = step.get('press', '1')
        
        # Calculate how long to wait after current position
        wait_after_current = max(0, target_time - elapsed_time)
        
        print(f"   📱 TwiML: Button '{button}' target={target_time}s, elapsed={elapsed_time}s, wait={wait_after_current}s")
        
        # Wait until it's time to press
        if wait_after_current > 0:
            response.pause(length=wait_after_current)
        
        # Press the button
        response.play(digits=button)
        
        # Update elapsed time: we waited + button press takes ~1 second
        elapsed_time = target_time + 1
    
    # Now we've navigated through the call tree
    # Use <Gather> to detect when human answers (speech detection)
    if webhook_base_url:
        print(f"   🎤 Using speech detection webhook: {webhook_base_url}")
        gather = response.gather(
            input='speech',
            timeout=15,  # Wait up to 15s for speech
            action=f'{webhook_base_url}/voice/speech-detected',
            method='POST',
            speech_timeout=1  # Trigger 1s after they stop talking - faster response
        )
        # While gathering, just be silent (human says "Hello?")
        gather.pause(length=15)
        
        # If no speech detected (timeout), go to no-speech handler
        response.redirect(f'{webhook_base_url}/voice/no-speech', method='POST')
    else:
        # Fallback: No webhook, use fixed timing
        print(f"   📢 No webhook URL - using fixed 10s pause before TTS")
        response.pause(length=10)
        response.say(
            Config.HUMAN_MESSAGE,
            voice='Polly.Joanna',
            language='en-US'
        )
        # Record to keep call alive after TTS
        response.record(timeout=10, max_length=90, play_beep=False)
        # Keep call alive to capture response
        response.pause(length=30)
        response.hangup()
    
    return str(response)
