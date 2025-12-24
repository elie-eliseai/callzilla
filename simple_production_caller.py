#!/usr/bin/env python3
"""
Simple Production Caller - Automated voice calling system for property phone verification.

This module handles the core calling logic:
- Making calls via Twilio
- Navigating phone trees
- Analyzing call recordings
- Managing retry logic for humans/call trees

Helper modules:
- gpt_analysis.py: GPT-based call classification
- twiml_generator.py: TwiML generation for calls
- csv_utils.py: CSV loading and phone number handling
- logging_utils.py: Logging utilities
"""

import sys
import os
import time
import logging
import requests
from datetime import datetime
from twilio.rest import Client

# Suppress verbose Twilio HTTP logging
logging.getLogger('twilio.http_client').setLevel(logging.WARNING)

# Local imports
from config import Config
from database import CallDatabase
from audio_analyzer import AudioAnalyzer, find_phrase_timing
from logging_utils import TeeLogger
from csv_utils import (
    load_properties_from_csv, 
    get_completed_properties,
    save_scraped_phones,
    SCRAPER_AVAILABLE
)
from twiml_generator import (
    create_exploration_twiml,
    create_button_sequence_twiml
)
from gpt_analysis import (
    analyze_call_recording,
    validate_call_result,
    detect_if_human,
    is_call_tree,
    determine_leasing_button,
    analyze_call_tree
)


class SimpleProductionCaller:
    """
    Main caller class - handles making calls and analyzing results.
    
    Flow:
    1. Make call to identify phone system type
    2. If call tree: press buttons and call again
    3. If human: wait and retry to reach voicemail
    4. If machine (voicemail/AI): analyze for EliseAI disclaimer
    """
    
    def __init__(self):
        Config.validate()
        self.client = Client(Config.TWILIO_ACCOUNT_SID, Config.TWILIO_AUTH_TOKEN)
        self.db = CallDatabase(Config.RESULTS_FILE)
        self.analyzer = AudioAnalyzer()
    
    # =========================================================================
    # HELPER METHODS
    # =========================================================================
    
    def _fetch_call_status(self, call_sid):
        """Fetch call status from Twilio. Returns (status, duration) or raises on error."""
        try:
            call = self.client.calls(call_sid).fetch()
            status = call.status
            duration = int(call.duration) if call.duration else 0
            print(f"   📊 Call status: {status}, duration: {duration}s")
            return status, duration
        except Exception as e:
            print(f"   ⚠️  Could not fetch call status: {str(e)}")
            return 'unknown', 0
    
    def _fetch_recordings(self, call_sid, max_attempts=15):
        """Wait for and fetch recordings. Returns list of (recording, duration) tuples."""
        print(f"   📼 Fetching recordings...")
        
        for attempt in range(max_attempts):
            time.sleep(3 if attempt > 0 else 2)
            recordings = list(self.client.recordings.list(call_sid=call_sid, limit=10))
            
            if not recordings:
                if attempt < max_attempts - 1:
                    print(".", end="", flush=True)
                continue
            
            # Check if any recordings are still processing
            still_processing = [r for r in recordings if getattr(r, 'status', '') == 'processing']
            if still_processing and attempt < max_attempts - 1:
                print(f"⏳", end="", flush=True)
                continue
            
            break
        else:
            print(f"\n   ⚠️ No recording found after retries")
            return []
        
        # Parse recordings with durations
        all_recordings = []
        print(f"   📋 Found {len(recordings)} recording(s):")
        
        for rec in recordings:
            duration = self._parse_recording_duration(rec)
            print(f"      - Recording {rec.sid}: duration={rec.duration} (parsed: {duration}s), status={getattr(rec, 'status', 'unknown')}")
            if duration >= 0:
                all_recordings.append((rec, duration))
        
        return all_recordings
    
    def _parse_recording_duration(self, recording):
        """Parse recording duration, handling edge cases."""
        duration_str = str(recording.duration) if recording.duration is not None else '0'
        try:
            if duration_str in ['-1', '', 'None']:
                return 0
            return int(float(duration_str))
        except (ValueError, TypeError):
            return 0
    
    def _select_stereo_recording(self, recordings):
        """Select the stereo call-level recording (channels=2) from a list of recordings."""
        for rec in recordings:
            channels = getattr(rec, 'channels', 1)
            if channels == 2:
                return rec
        # Fallback to first if no stereo found
        if recordings:
            print(f"   ⚠️  No stereo recording found, using first available")
            return recordings[0]
        return None
    
    def _print_transcription(self, transcription, immediate_info):
        """Print transcription with formatting."""
        first_200 = transcription[:200] if transcription else ""
        print(f"\n   📄 TRANSCRIPTION (Full length: {len(transcription)} chars):")
        print(f"   {'-'*66}")
        
        has_immediate = immediate_info.get('has_immediate_message', False)
        behavior = immediate_info.get('call_behavior', 'unknown')
        
        if has_immediate:
            print(f"   ⚠️  IMMEDIATE AUTOMATED MESSAGE DETECTED:")
            print(f"   Behavior: {behavior}")
            print(f"   First 5 seconds: {immediate_info.get('immediate_message_text', '')}...")
            if immediate_info.get('has_immediate_disclaimer'):
                print(f"   ⚠️  ⚠️  IMMEDIATE DISCLAIMER FOUND AT START! ⚠️  ⚠️")
            print(f"   {'-'*66}")
        elif behavior in ['normal_ringing', 'normal_ringing_or_immediate_connection']:
            print(f"   📞 Call behavior: {behavior.replace('_', ' ').title()}")
            print(f"   {'-'*66}")
        
        print(f"   🔍 FIRST 200 CHARS: {first_200}...")
        print(f"   {'-'*66}")
        for line in transcription.split('. '):
            if line.strip():
                print(f"   {line.strip()}")
        print(f"   {'-'*66}\n")
    
    def _verify_tts_played(self, recording_url, auth):
        """Verify if our TTS message was played to the human."""
        try:
            response = requests.get(recording_url, auth=auth)
            if response.status_code == 200:
                result = self.analyzer.verify_tts_played(response.content, Config.HUMAN_MESSAGE)
                if result:
                    print(f"   ✅ TTS CONFIRMED: Human heard our message")
                elif result is False:
                    print(f"   ⚠️  TTS NOT CONFIRMED: Human may not have heard message")
                else:
                    print(f"   ❓ TTS UNKNOWN: Could not verify if message played")
                return result
        except Exception as e:
            print(f"   ⚠️  Could not verify TTS: {str(e)}")
        return None
    
    def _print_disclaimer_result(self, property_name, disclaimer_found, classification=None):
        """Print disclaimer result message."""
        if disclaimer_found:
            print(f"   ✅ EliseAI DISCLAIMER FOUND!")
            print(f"   {property_name} IS using EliseAI!\n")
        elif classification == 'ai_assistant':
            print(f"   ⚠️  AI detected but NO EliseAI disclaimer")
            print(f"   {property_name} has AI but NOT EliseAI\n")
        else:
            print(f"   ❌ EliseAI disclaimer NOT found")
            print(f"   {property_name} is NOT using EliseAI\n")
    
    # =========================================================================
    # MAIN CALL METHODS
    # =========================================================================
    
    def make_call(self, phone_number, property_name, button_sequence=None):
        """
        Make a call to the phone system.
        If button_sequence is provided, press those buttons with timing.
        Otherwise, just listen and record.
        """
        max_retries = 3
        retry_delay = 5
        
        for attempt in range(max_retries):
            try:
                if button_sequence:
                    print(f"\n📞 Calling {property_name}: {phone_number}")
                    print(f"   🔢 Button sequence: {[s['press'] for s in button_sequence]}")
                    # Pass webhook URL for speech detection (if configured)
                    webhook_url = Config.BASE_URL if Config.BASE_URL != 'http://localhost:5000' else None
                    twiml = create_button_sequence_twiml(button_sequence, webhook_base_url=webhook_url)
                else:
                    print(f"\n📞 Exploring {property_name}: {phone_number}")
                    print(f"   🔍 Listening to identify phone system type...")
                    webhook_url = Config.BASE_URL if Config.BASE_URL != 'http://localhost:5000' else None
                    twiml = create_exploration_twiml(webhook_base_url=webhook_url)
                
                call = self.client.calls.create(
                    to=phone_number,
                    from_=Config.TWILIO_PHONE_NUMBER,
                    twiml=twiml,
                    record=True,
                    recording_status_callback='',
                    recording_channels='dual'
                )
                
                print(f"   ✅ Call SID: {call.sid}")
                return call.sid
                
            except Exception as e:
                error_msg = str(e)
                print(f"   ❌ Error: {error_msg}")
                
                is_network_error = any(keyword in error_msg.lower() for keyword in [
                    'connection', 'network', 'resolve', 'dns', 'timeout', 
                    'max retries', 'nodename', 'servname'
                ])
                
                if is_network_error and attempt < max_retries - 1:
                    print(f"   ⏳ Network error, waiting {retry_delay}s before retry...")
                    time.sleep(retry_delay)
                    retry_delay *= 2
                    continue
                else:
                    return None
        
        return None
    
    def wait_for_call_completion(self, call_sid, max_wait=300):
        """Wait for call to complete"""
        print(f"   ⏳ Waiting for call to complete", end="", flush=True)
        
        start_time = time.time()
        while time.time() - start_time < max_wait:
            time.sleep(2)
            print(".", end="", flush=True)
            
            try:
                call = self.client.calls(call_sid).fetch()
                if call.status in ['completed', 'failed', 'busy', 'no-answer', 'canceled']:
                    duration = call.duration if call.duration else 0
                    print(f"\n   ✓ Call {call.status} ({duration}s)")
                    return call
            except Exception:
                pass
        
        print(f"\n   ⏱️ Timeout after {max_wait}s")
        return None
    
    def analyze_call(self, call_sid, property_name, phone_number, attempt_number=1, 
                     button_sequence=None, previous_transcriptions=None):
        """
        Analyze the FULL call recording.
        
        Returns a dict with:
          - 'call_type': 'human', 'machine', 'call_tree', 'out_of_service', or 'error'
          - 'human_detected': bool
          - 'disclaimer_found': bool
          - 'transcription': str
          - 'menu_duration': int (seconds)
          - 'suggested_button': str or None (if call_tree)
        """
        previous_transcriptions = previous_transcriptions or []
        
        # STEP 0: Check call status
        call_status, call_duration = self._fetch_call_status(call_sid)
        
        if call_status in ['failed', 'busy', 'no-answer']:
            print(f"   ❌ Call {call_status} - number may be out of service")
            return {
                'call_type': 'out_of_service',
                'human_detected': False,
                'disclaimer_found': False,
                'transcription': f"Call {call_status}",
                'menu_duration': 0,
                'suggested_button': None
            }
        
        if call_duration < 3 and call_status == 'completed':
            print(f"   ⚠️  Very short call ({call_duration}s) - possible instant hangup")
        
        # STEP 1: Wait for recordings
        print(f"   📼 Fetching recordings...")
        recordings = None
        max_attempts = 15
        
        for attempt in range(max_attempts):
            time.sleep(3 if attempt > 0 else 2)
            recordings = list(self.client.recordings.list(call_sid=call_sid, limit=10))
            
            if not recordings:
                if attempt < max_attempts - 1:
                    print(".", end="", flush=True)
                continue
            
            still_processing = [r for r in recordings if getattr(r, 'status', '') == 'processing']
            if still_processing and attempt < max_attempts - 1:
                print(f"⏳", end="", flush=True)
                continue
            break
        
        if not recordings:
            print(f"\n   ⚠️ No recording found after retries")
            return {'call_type': 'error', 'human_detected': False, 'disclaimer_found': False}
        
        # STEP 2: Select stereo recording
        recording = self._select_stereo_recording(recordings)
        if not recording:
            return {'call_type': 'error', 'human_detected': False, 'disclaimer_found': False}
        
        duration = self._parse_recording_duration(recording)
        print(f"   ✅ Recording: {duration}s (SID: {recording.sid})")
        
        recording_url = f"https://api.twilio.com{recording.uri.replace('.json', '.wav')}"
        auth = (Config.TWILIO_ACCOUNT_SID, Config.TWILIO_AUTH_TOKEN)
        
        # STEP 3: Calculate skip time for button sequences
        skip_seconds = 0
        if button_sequence and len(button_sequence) > 0:
            last_button_time = button_sequence[-1].get('wait', 0)
            skip_seconds = last_button_time + 1
            print(f"   ✂️  Trimming to content after {skip_seconds}s (last button + 1s)")
        
        # STEP 4: Transcribe
        print(f"   📝 Transcribing...")
        result = self.analyzer.analyze_recording(recording_url, auth, skip_seconds=skip_seconds)
        
        if not result['success']:
            print(f"   ❌ Transcription failed: {result['error']}")
            return {'call_type': 'error', 'human_detected': False, 'disclaimer_found': False}
        
        transcription = result['transcription'] or ""
        disclaimer_found = result['disclaimer_found']
        menu_duration = result.get('menu_duration', 10)
        immediate_info = result.get('immediate_message', {})
        words = result.get('words', [])  # Word-level timestamps for phrase timing
        
        has_immediate_message = immediate_info.get('has_immediate_message', False)
        has_immediate_disclaimer = immediate_info.get('has_immediate_disclaimer', False)
        
        # Check for short call = likely human hangup
        if len(transcription.strip()) < 10 and call_duration < 15:
            print(f"   ⚠️  Short call ({call_duration}s) with minimal audio - likely human hung up")
            return {
                'call_type': 'human',
                'human_detected': True,
                'disclaimer_found': False,
                'transcription': transcription,
                'menu_duration': 0,
                'suggested_button': None
            }
        
        # STEP 5: Print transcription
        self._print_transcription(transcription, immediate_info)
        
        # STEP 6: GPT Classification
        call_tree_analysis = analyze_call_recording(transcription, previous_transcriptions=previous_transcriptions)
        call_tree_detected = call_tree_analysis['is_call_tree']
        
        if call_tree_detected:
            print(f"   🌳 CALL TREE DETECTED!")
            print(f"   ⏱️  Menu duration: ~{menu_duration} seconds")
            
            suggested_button = call_tree_analysis['button']
            if suggested_button:
                print(f"   🔢 Suggested button for leasing: '{suggested_button}'")
            else:
                print(f"   ⚠️  Could not determine leasing button: {call_tree_analysis.get('reasoning', 'Unknown')}")
            
            self.db.log_call(
                property_name=property_name,
                phone_number=phone_number,
                call_sid=call_sid,
                attempt_number=attempt_number,
                status='call_tree',
                human_detected=False,
                ai_reached=False,
                disclaimer_found=disclaimer_found,
                immediate_message=has_immediate_message,
                immediate_disclaimer=has_immediate_disclaimer,
                transcription=transcription[:1000],
                recording_url=recording_url,
                classification='call_tree',
                gpt_reasoning=call_tree_analysis.get('reasoning', ''),
                button_pressed=suggested_button or '',
                button_sequence=str(button_sequence) if button_sequence else ''
            )
            
            return {
                'call_type': 'call_tree',
                'human_detected': False,
                'disclaimer_found': disclaimer_found,
                'transcription': transcription,
                'menu_duration': menu_duration,
                'suggested_button': suggested_button,
                'key_phrase': call_tree_analysis.get('key_phrase'),
                'words': words
            }
        
        # STEP 7: Handle non-call-tree classifications
        classification = call_tree_analysis.get('classification', 'unknown')
        human_detected = call_tree_analysis.get('is_human', False)
        tts_confirmed = None
        
        # DISCLAIMER OVERRIDES - if found, it's always EliseAI (not human)
        if disclaimer_found:
            classification = 'ai_assistant'
            human_detected = False
        
        if human_detected:
            print(f"   👤 HUMAN DETECTED!")
            tts_confirmed = self._verify_tts_played(recording_url, auth)
            print(f"   📞 Will call again to reach voicemail...\n")
            call_type = 'human'
        else:
            if classification == 'voicemail':
                print(f"   📫 VOICEMAIL detected")
                call_type = 'machine'
            elif classification == 'ai_assistant':
                print(f"   🤖 AI ASSISTANT detected")
                call_type = 'machine'
            elif classification == 'out_of_service':
                print(f"   ❌ NUMBER OUT OF SERVICE")
                call_type = 'out_of_service'
                print(f"   {property_name} - number is not valid\n")
            else:
                print(f"   ❓ UNKNOWN classification: {classification}")
                call_type = 'unknown'
            
            # Print EliseAI result (skip for out_of_service)
            if classification != 'out_of_service':
                self._print_disclaimer_result(property_name, disclaimer_found, classification)
        
        # Log the call
        self.db.log_call(
            property_name=property_name,
            phone_number=phone_number,
            call_sid=call_sid,
            attempt_number=attempt_number,
            status='completed',
            human_detected=human_detected,
            tts_confirmed=tts_confirmed,
            ai_reached=not human_detected,
            disclaimer_found=disclaimer_found,
            immediate_message=has_immediate_message,
            immediate_disclaimer=has_immediate_disclaimer,
            transcription=transcription[:1000],
            recording_url=recording_url,
            classification=classification,
            gpt_reasoning=call_tree_analysis.get('reasoning', ''),
            button_sequence=str(button_sequence) if button_sequence else ''
        )
        
        return {
            'call_type': call_type,
            'human_detected': human_detected,
            'disclaimer_found': disclaimer_found,
            'transcription': transcription,
            'menu_duration': menu_duration,
            'suggested_button': None
        }
    
    def process_property(self, property_info):
        """
        Process a single property with smart call tree navigation.
        
        Flow:
        1. Make initial call (listen to menu)
        2. Analyze result:
           - CALL_TREE: Determine button, add to sequence, call again
           - HUMAN: Wait, call again to reach voicemail
           - MACHINE (voicemail/AI): Done, check for disclaimer
        3. Repeat until we reach a non-call-tree endpoint
        """
        property_name = property_info['name']
        phone_number = property_info['phone']
        
        print(f"\n{'='*70}")
        print(f"🏢 {property_name}")
        print(f"📞 {phone_number}")
        print(f"{'='*70}")
        
        button_sequence = []
        previous_transcriptions = []
        max_call_tree_depth = 5
        max_human_retries = 3
        
        attempt_number = 1
        human_retry_count = 0
        
        while True:
            # Determine what kind of call to make
            if button_sequence:
                print(f"\n   🔄 Attempt {attempt_number}: Navigating through call tree")
                print(f"   🔢 Using button sequence: {[s['press'] for s in button_sequence]}")
                print(f"   ⏱️  Timing: {[(s['wait'], s['press']) for s in button_sequence]}")
                call_sid = self.make_call(phone_number, property_name, button_sequence)
            else:
                print(f"\n   🔍 Attempt {attempt_number}: Listening to menu (no buttons)")
                call_sid = self.make_call(phone_number, property_name, None)
            
            if not call_sid:
                print(f"   ❌ Failed to make call, skipping property")
                return
            
            call = self.wait_for_call_completion(call_sid)
            
            if not call:
                print(f"   ⚠️  Call timed out, checking for recordings anyway...")
            
            analysis = self.analyze_call(call_sid, property_name, phone_number, 
                                         attempt_number, button_sequence, previous_transcriptions)
            
            current_transcription = analysis.get('transcription', '')
            if current_transcription:
                previous_transcriptions.append(current_transcription)
            
            if analysis.get('call_type') == 'error':
                print(f"   ❌ Analysis failed, skipping property")
                return
            
            call_type = analysis.get('call_type', 'machine')
            
            # Handle based on call type
            if call_type == 'call_tree':
                suggested_button = analysis.get('suggested_button')
                menu_duration = analysis.get('menu_duration', 10)
                
                # Check for "HOLD" flag
                if suggested_button and suggested_button.upper() == 'HOLD':
                    print(f"   ⚠️  'Stay on hold' detected - this needs MANUAL REVIEW")
                    print(f"   📋 System says to hold for representative, we can't detect when human picks up")
                    self.db.log_call(
                        property_name=property_name,
                        phone_number=phone_number,
                        call_sid=call_sid,
                        attempt_number=attempt_number,
                        status='needs_manual_review',
                        classification='hold_for_rep',
                        gpt_reasoning='System says to stay on hold for representative - cannot auto-detect human pickup',
                        transcription=analysis.get('transcription', '')[:1000]
                    )
                    return
                
                if not suggested_button:
                    print(f"   ⚠️  Could not determine which button to press")
                    print(f"   🔢 Defaulting to '1' for leasing")
                    suggested_button = '1'
                
                # Calculate precise timing using phrase-based approach
                key_phrase = analysis.get('key_phrase')
                words = analysis.get('words', [])
                
                # Calculate skip_seconds (where trimmed audio starts)
                if button_sequence:
                    skip_seconds = button_sequence[-1]['wait'] + 1
                else:
                    skip_seconds = 0
                
                # Use phrase-based timing
                if key_phrase and words:
                    phrase_end_time = find_phrase_timing(words, key_phrase)  # Will raise if not found
                    cumulative_time = skip_seconds + phrase_end_time + 1  # +1 buffer
                    print(f"   🎯 Phrase \"{key_phrase}\" ends at {phrase_end_time:.1f}s")
                    print(f"   ⏱️  Will press at {cumulative_time:.1f}s from call start (skip {skip_seconds}s + phrase {phrase_end_time:.1f}s + 1s buffer)")
                else:
                    # Missing phrase data - this shouldn't happen with updated code
                    raise ValueError(f"Missing phrase timing data: key_phrase={key_phrase}, words_count={len(words)}")
                
                button_sequence.append({
                    'wait': cumulative_time,
                    'press': suggested_button
                })
                
                print(f"\n   🌳 Call tree layer {len(button_sequence)} detected")
                print(f"   📱 Updated button sequence: {[s['press'] for s in button_sequence]}")
                
                if len(button_sequence) >= max_call_tree_depth:
                    print(f"   ⚠️  Maximum call tree depth ({max_call_tree_depth}) reached")
                    print(f"   📊 Stopping navigation, using last result")
                    return
                
                print(f"   ⏳ Waiting 5 seconds before next call...")
                time.sleep(5)
                attempt_number += 1
                continue
                
            elif call_type == 'human':
                human_retry_count += 1
                
                if human_retry_count >= max_human_retries:
                    print(f"   ⚠️  Maximum human retries ({max_human_retries}) reached")
                    print(f"   📊 Could not reach voicemail, moving on")
                    return
                
                print(f"   ⏳ Waiting 10 seconds before calling again (to reach voicemail)...")
                if button_sequence:
                    print(f"   🔢 Will replay button sequence: {[s['press'] for s in button_sequence]}")
                time.sleep(10)
                attempt_number += 1
                continue
                
            elif call_type == 'machine':
                print(f"\n   ✅ Reached endpoint (voicemail/AI)")
                
                if button_sequence:
                    print(f"   🔢 Final button sequence: {[s['press'] for s in button_sequence]}")
                
                disclaimer_found = analysis.get('disclaimer_found', False)
                
                if disclaimer_found:
                    print(f"\n   🎉 SUCCESS: {property_name} IS using EliseAI!")
                else:
                    print(f"\n   ℹ️  RESULT: {property_name} is NOT using EliseAI")
                
                return
            
            else:
                print(f"   ⚠️  Unknown call type: {call_type}")
                return


def run_batch_validation(results_file):
    """
    Run validation on all completed calls in batch.
    Reads the CSV, runs GPT validation on each property, updates the CSV.
    """
    import csv
    
    print("\n" + "="*70)
    print("🔍 BATCH VALIDATION - Checking all results for issues...")
    print("="*70)
    
    try:
        with open(results_file, 'r') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            fieldnames = reader.fieldnames
        
        if not rows:
            print("   No results to validate")
            return
        
        if 'Needs Review' not in fieldnames:
            fieldnames = list(fieldnames) + ['Needs Review', 'Review Issues', 'Review Reasoning']
        
        properties = {}
        for i, row in enumerate(rows):
            prop_name = row.get('Property Name', 'Unknown')
            properties[prop_name] = (i, row)
        
        validated_count = 0
        flagged_count = 0
        
        for prop_name, (idx, row) in properties.items():
            transcription = row.get('Transcription', '')
            classification = row.get('Classification', 'unknown')
            
            if row.get('Needs Review') or not transcription or len(transcription) < 20:
                continue
            
            print(f"   Validating: {prop_name}...", end=" ", flush=True)
            
            validation = validate_call_result(prop_name, transcription, classification)
            
            needs_review = validation.get('needs_review', False)
            review_issues = ', '.join(validation.get('issues', []))
            review_reasoning = validation.get('reasoning', '')
            
            rows[idx]['Needs Review'] = str(needs_review)
            rows[idx]['Review Issues'] = review_issues
            rows[idx]['Review Reasoning'] = review_reasoning
            
            validated_count += 1
            if needs_review:
                flagged_count += 1
                print(f"⚠️  {review_issues}")
            else:
                print("✅")
        
        with open(results_file, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        
        print(f"\n   ✅ Validated {validated_count} properties, {flagged_count} flagged for review")
        
    except Exception as e:
        print(f"   ❌ Validation error: {str(e)}")


def print_summary(results_file):
    """Print summary of call results from CSV."""
    import csv
    
    try:
        with open(results_file, 'r') as f:
            reader = csv.DictReader(f)
            results = list(reader)
        
        if not results:
            return
        
        print("\n" + "="*70)
        print("📋 RESULTS SUMMARY")
        print("="*70)
        
        # Group by property (take final result for each)
        properties_seen = {}
        for row in results:
            prop_name = row.get('Property Name', 'Unknown')
            properties_seen[prop_name] = row
        
        elise_count = 0
        not_elise_count = 0
        needs_review_count = 0
        
        for prop_name, row in properties_seen.items():
            classification = row.get('Classification', 'unknown')
            disclaimer = row.get('Disclaimer Found', 'False') == 'True'
            needs_review = row.get('Needs Review', 'False') == 'True'
            review_issues = row.get('Review Issues', '')
            tts_confirmed = row.get('TTS Confirmed', '')
            
            if disclaimer:
                status = "✅ EliseAI"
                elise_count += 1
            else:
                status = "❌ Not EliseAI"
                not_elise_count += 1
            
            review_flag = ""
            if needs_review:
                review_flag = f" ⚠️ REVIEW: {review_issues}"
                needs_review_count += 1
            
            tts_flag = ""
            if classification == 'human' and tts_confirmed:
                tts_flag = f" [TTS: {'✓' if tts_confirmed == 'True' else '✗'}]"
            
            print(f"  {prop_name}: {status} ({classification}){tts_flag}{review_flag}")
        
        print("-"*70)
        print(f"  📊 TOTALS: {elise_count} EliseAI | {not_elise_count} Not EliseAI | {needs_review_count} Need Review")
        print("="*70 + "\n")
        
    except Exception as e:
        print(f"\n⚠️  Could not print summary: {str(e)}\n")


def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Voice Automation - Scrape phone numbers and/or make calls',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Scrape only - get phone numbers, save to CSV for review
  python3 simple_production_caller.py properties.csv --scrape-only
  
  # Call only - use existing phone numbers in CSV
  python3 simple_production_caller.py properties.csv --call-only
  
  # Both (default) - scrape missing phones, then call all
  python3 simple_production_caller.py properties.csv
  
  # Start from specific property
  python3 simple_production_caller.py properties.csv --start "Smith Flats"
        """
    )
    parser.add_argument('csv_file', help='Path to CSV file with properties')
    parser.add_argument('--scrape-only', action='store_true', 
                        help='Only scrape phone numbers, save to CSV, don\'t call')
    parser.add_argument('--call-only', action='store_true',
                        help='Only make calls, don\'t scrape (requires phone column)')
    parser.add_argument('--start', metavar='PROPERTY', 
                        help='Start from specific property name')
    parser.add_argument('--output', metavar='FILE',
                        help='Output CSV for scraped phones (default: scraped_phones.csv)')
    parser.add_argument('--caller-id', metavar='PHONE',
                        help='Override caller ID with a verified Twilio number (temporary)')
    
    args = parser.parse_args()
    
    # Validate conflicting options
    if args.scrape_only and args.call_only:
        print("❌ Cannot use --scrape-only and --call-only together")
        sys.exit(1)
    
    # Override caller ID if specified
    if args.caller_id:
        Config.TWILIO_PHONE_NUMBER = args.caller_id
        print(f"📞 Using override caller ID: {args.caller_id}")
    
    # Set up logging to file
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = f"call_log_{timestamp}.txt"
    logger = TeeLogger(log_file)
    sys.stdout = logger
    
    # Mode banner
    if args.scrape_only:
        print("\n" + "="*70)
        print("🔍 SCRAPE MODE - Finding phone numbers only")
        print("="*70)
    elif args.call_only:
        print("\n" + "="*70)
        print("📞 CALL MODE - Making calls only (no scraping)")
        print("="*70)
    else:
        print("\n" + "="*70)
        print("🚀 FULL MODE - Scrape + Call")
        print("="*70)
    
    print(f"📝 Log file: {log_file}")
    print("="*70)
    
    csv_path = args.csv_file
    start_from = args.start
    
    if not os.path.exists(csv_path):
        print(f"\n❌ File not found: {csv_path}\n")
        sys.exit(1)
    
    # For call-only mode, temporarily disable scraper
    import csv_utils
    if args.call_only:
        original_scraper = csv_utils.SCRAPER_AVAILABLE
        csv_utils.SCRAPER_AVAILABLE = False
    
    properties = load_properties_from_csv(csv_path, start_from_property=start_from)
    
    if args.call_only:
        csv_utils.SCRAPER_AVAILABLE = original_scraper
    
    if not properties:
        print("\n❌ Failed to load properties\n")
        sys.exit(1)
    
    # SCRAPE-ONLY MODE
    if args.scrape_only:
        output_file = args.output or "scraped_phones.csv"
        save_scraped_phones(properties, output_file)
        print("="*70 + "\n")
        sys.stdout = logger.terminal
        logger.close()
        sys.exit(0)
    
    # CALL MODE
    print(f"🎯 Target disclaimer: '{Config.TARGET_DISCLAIMER}'")
    print(f"📊 Processing {len(properties)} properties...\n")
    print("🚀 Starting calls automatically...\n")
    
    caller = SimpleProductionCaller()
    
    for i, prop in enumerate(properties, 1):
        print(f"\n[{i}/{len(properties)}]")
        caller.process_property(prop)
        
        if i < len(properties):
            wait_time = 5
            print(f"\n⏳ Waiting {wait_time} seconds before next call...")
            time.sleep(wait_time)
    
    print("\n" + "="*70)
    print("✅ All calls complete!")
    print(f"📊 Results saved to: {Config.RESULTS_FILE}")
    print("="*70)
    
    # Run batch validation
    run_batch_validation(Config.RESULTS_FILE)
    
    # Print summary
    print_summary(Config.RESULTS_FILE)
    
    # Archive results
    from archive import append_to_archive
    print(append_to_archive(Config.RESULTS_FILE))
    
    # Close logger
    print(f"📝 Full log saved to: {log_file}")
    sys.stdout = logger.terminal
    logger.close()


if __name__ == '__main__':
    main()
