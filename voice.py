#!/usr/bin/env python3
"""
Smart caller that TALKS to people when they pick up!
Uses Twilio TTS to speak naturally
"""
import pandas as pd
from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse, Say, Pause
from config import Config
from audio_analyzer import AudioAnalyzer
import time
def get_human_response_twiml():
    """TwiML that TALKS to the person when they pick up"""
    response = VoiceResponse()
    # Pause briefly so they hear us
    response.pause(length=1)
    # Speak naturally to them
    response.say(
        "Hello! This is an automated test call. "
        "Please don't hang up. "
        "This is a test call from Elise A I. "
        "We are testing our system. "
        "I will call again in a moment. "
        "Please let it go to voicemail next time. "
        "Thank you for your patience. "
        "Goodbye!",
        voice='Polly.Joanna',  # Natural female voice
        language='en-US'
    )
    # Pause before hanging up
    response.pause(length=1)
    response.hangup()
    return str(response)
def get_recording_twiml():
    """TwiML that records the voicemail"""
    response = VoiceResponse()
    # Record from the start
    response.record(
        max_length=120,
        timeout=15,
        transcribe=False,
        play_beep=False
    )
    response.hangup()
    return str(response)
def make_call_with_amd(client, phone_number, attempt=1):
    """Make a call with answering machine detection"""
    print(f"   :telephone_receiver: Attempt {attempt}: Calling {phone_number}...")
    try:
        if attempt == 1:
            # First call: Use AMD to detect human
            call = client.calls.create(
                to=phone_number,
                from_=Config.TWILIO_PHONE_NUMBER,
                url='http://twimlets.com/holdmusic?Bucket=com.twilio.music.classical',  # Placeholder
                machine_detection='DetectMessageEnd',
                machine_detection_timeout=30,
                status_callback='http://example.com/status',  # We'll poll instead
                record=True
            )
        else:
            # Second call: Just record
            call = client.calls.create(
                to=phone_number,
                from_=Config.TWILIO_PHONE_NUMBER,
                twiml=get_recording_twiml(),
                record=True
            )
        print(f"   :white_check_mark: Call SID: {call.sid}")
        return call.sid
    except Exception as e:
        print(f"   :x: Error: {str(e)}")
        return None
def wait_and_check_call(client, call_sid, max_wait=60):
    """Wait for call and check if human answered"""
    print(f"   :hourglass_flowing_sand: Monitoring call...", end="", flush=True)
    for i in range(max_wait):
        time.sleep(1)
        if i % 3 == 0:
            print(".", end="", flush=True)
        try:
            call = client.calls(call_sid).fetch()
            # Check if human answered
            if hasattr(call, 'answered_by'):
                answered_by = call.answered_by
                if answered_by in ['human', 'unknown'] and call.status == 'in-progress':
                    print(f"\n   :bust_in_silhouette: HUMAN DETECTED!")
                    # Update the call to speak to them!
                    print(f"   :speaking_head_in_silhouette:  Talking to them...")
                    client.calls(call_sid).update(
                        twiml=get_human_response_twiml()
                    )
                    # Wait for call to finish
                    while call.status not in ['completed', 'failed']:
                        time.sleep(1)
                        call = client.calls(call_sid).fetch()
                    print(f"   ✓ Message delivered!")
                    return 'human', call
                elif answered_by in ['machine_end_beep', 'machine_end_silence', 'machine_end_other']:
                    print(f"\n   :robot_face: Machine detected: {answered_by}")
                    # Let it finish recording
                    while call.status not in ['completed', 'failed']:
                        time.sleep(1)
                        call = client.calls(call_sid).fetch()
                    return 'machine', call
            # Check if call ended
            if call.status in ['completed', 'failed', 'busy', 'no-answer']:
                print(f"\n   ✓ Call {call.status}")
                return call.status, call
        except Exception as e:
            print(f"\n   :warning: Error checking call: {str(e)}")
            break
    print(f"\n   :stopwatch: Timeout")
    return 'timeout', None
def analyze_recording(client, analyzer, call_sid, phone_number):
    """Analyze the recording for disclaimer"""
    print(f"   :vhs: Fetching recording...")
    # Wait a bit for recording to be processed
    time.sleep(5)
    recordings = client.recordings.list(call_sid=call_sid, limit=5)
    if not recordings:
        print(f"   :warning: No recording found")
        return None
    recording = recordings[0]
    print(f"   :white_check_mark: Recording: {recording.duration} seconds")
    if recording.duration < 5:
        print(f"   :warning: Recording too short, skipping analysis")
        return {'disclaimer_found': False, 'transcription': 'Recording too short'}
    print(f"   :memo: Transcribing...")
    recording_url = f"https://api.twilio.com{recording.uri.replace('.json', '.wav')}"
    auth = (Config.TWILIO_ACCOUNT_SID, Config.TWILIO_AUTH_TOKEN)
    result = analyzer.analyze_recording(recording_url, auth)
    if result['success']:
        print(f"   ✓ Transcription complete")
        return result
    else:
        print(f"   ✗ Transcription failed: {result['error']}")
        return None
def test_number(phone_number, name="Test"):
    """Test a single phone number with full logic"""
    print(f"\n{'='*70}")
    print(f":office: {name}")
    print(f":telephone_receiver: {phone_number}")
    print(f"{'='*70}\n")
    client = Client(Config.TWILIO_ACCOUNT_SID, Config.TWILIO_AUTH_TOKEN)
    analyzer = AudioAnalyzer()
    # First call attempt
    call_sid = make_call_with_amd(client, phone_number, attempt=1)
    if not call_sid:
        return
    # Monitor the call
    result_type, call_info = wait_and_check_call(client, call_sid)
    # If human answered, make second call
    if result_type == 'human':
        print(f"\n   :stopwatch: Waiting 10 seconds before calling again...")
        time.sleep(10)
        print(f"\n   :telephone_receiver: Second attempt (should go to voicemail)...")
        call_sid_2 = make_call_with_amd(client, phone_number, attempt=2)
        if call_sid_2:
            result_type_2, call_info_2 = wait_and_check_call(client, call_sid_2)
            if call_info_2:
                # Analyze second call
                result = analyze_recording(client, analyzer, call_sid_2, phone_number)
                if result:
                    print_results(result, name, phone_number)
    elif result_type == 'machine':
        # Analyze first call
        result = analyze_recording(client, analyzer, call_sid, phone_number)
        if result:
            print_results(result, name, phone_number)
    print(f"\n{'='*70}\n")
def print_results(result, name, phone_number):
    """Print analysis results"""
    print(f"\n   :page_facing_up: TRANSCRIPTION:")
    print(f"   {'-'*66}")
    for line in result['transcription'].split('. '):
        if line.strip():
            print(f"   {line.strip()}")
    print(f"   {'-'*66}\n")
    if result['disclaimer_found']:
        print(f"   :white_check_mark: :white_check_mark: :white_check_mark: EliseAI DISCLAIMER FOUND! :white_check_mark: :white_check_mark: :white_check_mark:")
        print(f"   :tada: {name} IS using EliseAI!")
    else:
        print(f"   :x: EliseAI disclaimer NOT found")
        print(f"   :information_source:  {name} is NOT using EliseAI")
def main():
    import sys
    if len(sys.argv) > 1:
        # Test a specific number from command line
        phone_number = sys.argv[1]
        # Clean phone number
        phone_number = ''.join(filter(str.isdigit, phone_number))
        if not phone_number.startswith('+'):
            phone_number = '+1' + phone_number if not phone_number.startswith('1') else '+' + phone_number
        test_number(phone_number, "Test Property")
    else:
        # Test from CSV
        print("\n:rocket: Smart Caller - With Human Interaction!\n")
        print(":speech_balloon: If someone picks up, the system will TALK to them")
        print(":stopwatch:  Then call back 10 seconds later to get voicemail\n")
        df = pd.read_csv('properties.csv')
        for index, row in df.iterrows():
            property_name = row['Property Name']
            phone_number = str(row['Phone Number'])
            # Clean phone number
            phone_number = ''.join(filter(str.isdigit, phone_number))
            if not phone_number.startswith('+'):
                phone_number = '+1' + phone_number if not phone_number.startswith('1') else '+' + phone_number
            test_number(phone_number, property_name)
            # Wait between properties
            if index < len(df) - 1:
                print(":hourglass_flowing_sand: Waiting 5 seconds before next property...\n")
                time.sleep(5)
        print("\n:white_check_mark: All tests complete!\n")
if __name__ == '__main__':
    main()