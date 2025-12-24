import io
import re
import wave
import struct
import requests
from openai import OpenAI
from config import Config


def normalize_for_matching(text):
    """
    Normalize text for phrase matching.
    Handles: case, number words, punctuation, whitespace.
    """
    text = text.lower()
    
    # Number words to digits
    number_words = {
        'zero': '0', 'one': '1', 'two': '2', 'three': '3', 'four': '4',
        'five': '5', 'six': '6', 'seven': '7', 'eight': '8', 'nine': '9'
    }
    for word, digit in number_words.items():
        text = re.sub(rf'\b{word}\b', digit, text)
    
    # Remove punctuation
    text = re.sub(r'[,.\-!?\'"]', '', text)
    
    # Normalize whitespace
    return ' '.join(text.split())


def find_phrase_timing(words, key_phrase):
    """
    Find exact timing for a phrase in word-level timestamps.
    Returns end time of the phrase (when to press button).
    
    Args:
        words: List of dicts with 'word', 'start', 'end' from Whisper
        key_phrase: Exact phrase to find (e.g., "For leasing, press 1")
    
    Returns:
        End time (float) of the last word in the phrase
        
    Raises:
        ValueError if phrase not found (no fallbacks - fix root cause)
    """
    if not words:
        raise ValueError("No word timestamps provided")
    
    if not key_phrase:
        raise ValueError("No key phrase provided")
    
    # Normalize the phrase and split into words
    normalized_phrase = normalize_for_matching(key_phrase)
    phrase_words = normalized_phrase.split()
    
    if not phrase_words:
        raise ValueError(f"Key phrase '{key_phrase}' normalized to empty")
    
    # Normalize all words from transcript
    normalized_word_list = [normalize_for_matching(w['word']) for w in words]
    
    # Find ALL occurrences for debugging
    all_matches = []
    for i in range(len(words) - len(phrase_words) + 1):
        window = normalized_word_list[i:i + len(phrase_words)]
        if window == phrase_words:
            last_word_idx = i + len(phrase_words) - 1
            end_time = words[last_word_idx]['end']
            all_matches.append((i, end_time))
    
    if all_matches:
        # Debug: show all matches
        print(f"   🔍 DEBUG: Found {len(all_matches)} occurrence(s) of phrase:")
        for idx, (word_idx, end_time) in enumerate(all_matches):
            print(f"      [{idx+1}] at word index {word_idx}, ends at {end_time:.1f}s")
            # Show surrounding words for context
            start_ctx = max(0, word_idx - 2)
            end_ctx = min(len(words), word_idx + len(phrase_words) + 2)
            context_words = [f"{words[j]['word']}({words[j]['end']:.1f}s)" for j in range(start_ctx, end_ctx)]
            print(f"          Context: {' '.join(context_words)}")
        
        # Return FIRST match
        return all_matches[0][1]
    
    # Not found - fail loudly
    raise ValueError(f"Phrase '{key_phrase}' not found in transcript. "
                     f"Normalized: '{normalized_phrase}'. "
                     f"Available words: {normalized_word_list[:20]}...")


class AudioAnalyzer:
    """Analyze call recordings for specific disclaimers"""
    
    def __init__(self):
        self.client = OpenAI(api_key=Config.OPENAI_API_KEY) if Config.OPENAI_API_KEY else None
    
    def download_recording(self, recording_url, auth):
        """Download recording from Twilio"""
        try:
            # Twilio returns .wav format by default
            response = requests.get(recording_url, auth=auth)
            response.raise_for_status()
            return response.content
        except Exception as e:
            print(f"Error downloading recording: {str(e)}")
            return None
    
    def trim_audio_start(self, audio_data, skip_seconds):
        """
        Trim the beginning of the audio, skipping the first N seconds.
        Used to skip past menu navigation and only analyze what comes after button presses.
        """
        if skip_seconds <= 0:
            return audio_data
        
        try:
            import io
            import wave
            
            audio_io = io.BytesIO(audio_data)
            with wave.open(audio_io, 'rb') as wav_file:
                sample_rate = wav_file.getframerate()
                channels = wav_file.getnchannels()
                sample_width = wav_file.getsampwidth()
                n_frames = wav_file.getnframes()
                
                # Calculate frames to skip
                frames_to_skip = int(sample_rate * skip_seconds)
                if frames_to_skip >= n_frames:
                    print(f"   ⚠️  Skip time ({skip_seconds}s) exceeds recording length")
                    return audio_data
                
                # Skip to the position after button presses
                wav_file.setpos(frames_to_skip)
                remaining_frames = n_frames - frames_to_skip
                audio_after = wav_file.readframes(remaining_frames)
                
                # Create new WAV with trimmed audio
                output_io = io.BytesIO()
                with wave.open(output_io, 'wb') as out_wav:
                    out_wav.setnchannels(channels)
                    out_wav.setsampwidth(sample_width)
                    out_wav.setframerate(sample_rate)
                    out_wav.writeframes(audio_after)
                
                print(f"   ✂️  Trimmed first {skip_seconds}s - analyzing audio after button presses")
                return output_io.getvalue()
                
        except Exception as e:
            print(f"   ⚠️  Error trimming audio: {str(e)}")
            return audio_data
    
    def extract_inbound_channel(self, audio_data):
        """
        Extract only the inbound (their) channel from a stereo recording.
        
        Twilio dual-channel recordings:
        - Channel 0 (left): Their audio (call tree, voicemail, etc.)
        - Channel 1 (right): Our TTS message
        
        Returns mono audio with only Channel 0 (their audio).
        """
        try:
            import io
            import wave
            import struct
            
            # Read the stereo WAV file
            audio_io = io.BytesIO(audio_data)
            with wave.open(audio_io, 'rb') as wav_file:
                channels = wav_file.getnchannels()
                sample_width = wav_file.getsampwidth()
                sample_rate = wav_file.getframerate()
                n_frames = wav_file.getnframes()
                
                # If already mono, return as-is
                if channels == 1:
                    print("   ℹ️  Recording is mono, using as-is")
                    return audio_data
                
                print(f"   🔊 Stereo recording detected - extracting Channel 0 (their audio)")
                
                # Read all frames
                raw_data = wav_file.readframes(n_frames)
            
            # Determine format string based on sample width
            if sample_width == 1:
                fmt = 'B'  # unsigned char
            elif sample_width == 2:
                fmt = 'h'  # signed short
            elif sample_width == 4:
                fmt = 'i'  # signed int
            else:
                print(f"   ⚠️  Unsupported sample width: {sample_width}")
                return audio_data
            
            # Unpack all samples
            total_samples = n_frames * channels
            all_samples = struct.unpack(f'<{total_samples}{fmt}', raw_data)
            
            # Extract Channel 0 (left channel = their audio)
            # In stereo, samples are interleaved: [L0, R0, L1, R1, L2, R2, ...]
            channel_0_samples = all_samples[0::2]  # Even indices = left channel
            
            # Create mono WAV with Channel 0
            channel_0_data = struct.pack(f'<{len(channel_0_samples)}{fmt}', *channel_0_samples)
            output_io = io.BytesIO()
            with wave.open(output_io, 'wb') as out_wav:
                out_wav.setnchannels(1)
                out_wav.setsampwidth(sample_width)
                out_wav.setframerate(sample_rate)
                out_wav.writeframes(channel_0_data)
            
            print(f"   ✅ Extracted their audio (Channel 0)")
            return output_io.getvalue()
            
        except Exception as e:
            print(f"   ⚠️  Error extracting channel: {str(e)}")
            print(f"   ℹ️  Falling back to full recording")
            return audio_data
    
    def extract_our_audio(self, audio_data):
        """
        Extract Channel 1 (our audio/TTS) from stereo recording.
        Used to verify TTS was played to caller.
        """
        try:
            audio_io = io.BytesIO(audio_data)
            with wave.open(audio_io, 'rb') as wav_file:
                channels = wav_file.getnchannels()
                sample_width = wav_file.getsampwidth()
                sample_rate = wav_file.getframerate()
                n_frames = wav_file.getnframes()
                
                if channels == 1:
                    return None  # Mono, can't extract our channel
                
                raw_data = wav_file.readframes(n_frames)
            
            if sample_width == 1:
                fmt = 'B'
            elif sample_width == 2:
                fmt = 'h'
            elif sample_width == 4:
                fmt = 'i'
            else:
                return None
            
            total_samples = n_frames * channels
            all_samples = struct.unpack(f'<{total_samples}{fmt}', raw_data)
            
            # Extract Channel 1 (right channel = our audio)
            channel_1_samples = all_samples[1::2]  # Odd indices = right channel
            
            channel_1_data = struct.pack(f'<{len(channel_1_samples)}{fmt}', *channel_1_samples)
            output_io = io.BytesIO()
            with wave.open(output_io, 'wb') as out_wav:
                out_wav.setnchannels(1)
                out_wav.setsampwidth(sample_width)
                out_wav.setframerate(sample_rate)
                out_wav.writeframes(channel_1_data)
            
            return output_io.getvalue()
            
        except Exception as e:
            print(f"   ⚠️  Error extracting our audio: {str(e)}")
            return None
    
    def verify_tts_played(self, audio_data, tts_message):
        """
        Verify that our TTS message was played by checking Channel 1.
        Returns: True if TTS found, False if not, None if couldn't check
        """
        our_audio = self.extract_our_audio(audio_data)
        if not our_audio:
            return None  # Couldn't extract our channel
        
        # Transcribe our channel
        transcription = self.transcribe_audio(our_audio)
        if not transcription:
            return None  # Couldn't transcribe
        
        # Check if key phrases from our TTS are present
        transcription_lower = transcription.lower()
        tts_lower = tts_message.lower()
        
        # Check for key words from TTS message
        tts_words = set(tts_lower.split())
        found_words = sum(1 for word in tts_words if word in transcription_lower)
        
        # If we find more than 50% of the words, TTS likely played
        match_ratio = found_words / len(tts_words) if tts_words else 0
        
        print(f"   🔍 TTS verification: {found_words}/{len(tts_words)} words found ({match_ratio:.0%})")
        
        return match_ratio > 0.5
    
    def transcribe_audio(self, audio_data):
        """
        Transcribe audio using OpenAI Whisper API
        Whisper is one of the best STT models available, with high accuracy
        for phone call audio and various accents/background noise
        """
        if not self.client:
            print("OpenAI API key not configured")
            return None
        
        try:
            # Save audio to temporary file
            temp_file = 'temp_recording.wav'
            with open(temp_file, 'wb') as f:
                f.write(audio_data)
            
            # Transcribe using Whisper with optimal settings for phone calls
            with open(temp_file, 'rb') as audio_file:
                transcript = self.client.audio.transcriptions.create(
                    model="whisper-1",  # Best available model
                    file=audio_file,
                    response_format="verbose_json",  # Get more details
                    language="en"  # Optimize for English (change if needed)
                )
            
            # Extract text from verbose response
            return transcript.text if hasattr(transcript, 'text') else str(transcript)
        except Exception as e:
            print(f"Error transcribing audio: {str(e)}")
            return None
    
    def transcribe_audio_with_timing(self, audio_data):
        """
        Transcribe audio and return both text and timing information.
        Returns: dict with 'text', 'duration', and 'segments' (with timestamps)
        """
        if not self.client:
            print("OpenAI API key not configured")
            return None
        
        try:
            # Save audio to temporary file
            temp_file = 'temp_recording.wav'
            with open(temp_file, 'wb') as f:
                f.write(audio_data)
            
            # Transcribe using Whisper with verbose output for timestamps
            # Include word-level timestamps for precise button timing
            with open(temp_file, 'rb') as audio_file:
                transcript = self.client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    response_format="verbose_json",
                    language="en",
                    timestamp_granularities=["word", "segment"]
                )
            
            # Extract timing info from segments
            text = transcript.text if hasattr(transcript, 'text') else str(transcript)
            segments = []
            total_duration = 0
            
            if hasattr(transcript, 'segments') and transcript.segments:
                for seg in transcript.segments:
                    segments.append({
                        'start': seg.get('start', 0) if isinstance(seg, dict) else getattr(seg, 'start', 0),
                        'end': seg.get('end', 0) if isinstance(seg, dict) else getattr(seg, 'end', 0),
                        'text': seg.get('text', '') if isinstance(seg, dict) else getattr(seg, 'text', '')
                    })
                # Get total duration from last segment
                if segments:
                    total_duration = segments[-1]['end']
            
            # Also try to get duration from the response directly
            if hasattr(transcript, 'duration'):
                total_duration = transcript.duration
            
            # Extract word-level timestamps for precise button timing
            words = []
            if hasattr(transcript, 'words') and transcript.words:
                for word in transcript.words:
                    words.append({
                        'word': word.get('word', '') if isinstance(word, dict) else getattr(word, 'word', ''),
                        'start': word.get('start', 0) if isinstance(word, dict) else getattr(word, 'start', 0),
                        'end': word.get('end', 0) if isinstance(word, dict) else getattr(word, 'end', 0)
                    })
            
            return {
                'text': text,
                'duration': total_duration,
                'segments': segments,
                'words': words
            }
            
        except Exception as e:
            print(f"Error transcribing audio with timing: {str(e)}")
            return None
    
    def get_menu_duration(self, transcription_result):
        """
        Get total duration of the transcription.
        Used for legacy timing fallback - phrase-based timing is preferred.
        """
        if not transcription_result:
            raise ValueError("No transcription result - cannot determine duration")
        
        # If we have actual duration from Whisper
        if isinstance(transcription_result, dict) and 'duration' in transcription_result:
            duration = transcription_result['duration']
            if duration and duration > 0:
                return int(duration)
        
        # No duration available - fail loudly instead of guessing
        raise ValueError("No duration in transcription result - check Whisper call")
    
    def check_for_disclaimer(self, transcription, target_disclaimer):
        """Check if the target disclaimer is present in the transcription"""
        if not transcription:
            return False
        
        # Convert to lowercase for case-insensitive comparison
        transcription_lower = transcription.lower()
        
        # STRONG INDICATORS: If we see "Virtual Leasing Agent", it's definitely EliseAI
        # This is the most reliable indicator - if they say this, they're using EliseAI
        strong_indicators = [
            "virtual leasing agent",
            "virtual agent",
            "this is virtual leasing agent",
            "hi, this is virtual leasing agent",
            "hi this is virtual leasing agent"
        ]
        
        for indicator in strong_indicators:
            if indicator in transcription_lower:
                return True  # Definitely EliseAI if we see this
        
        # AI ASSISTANT PATTERNS: These phrases strongly indicate an AI assistant
        # If we see multiple of these, it's almost certainly EliseAI (even without exact disclaimer)
        ai_patterns = [
            "are you still there",
            "are you still with me",
            "are you still on the line",
            "if you need help finding an apartment",
            "if you'd like help with",
            "i'm here to help",
            "i'm here for you",
            "let me know how i can assist",
            "how can i assist you",
            "how can i help you",
            "if you have any questions",
            "just let me know",
            "i'm ready to help",
            "if you'd like to continue"
        ]
        
        # Count how many AI patterns we see
        pattern_matches = sum(1 for pattern in ai_patterns if pattern in transcription_lower)
        
        # If we see 3+ AI patterns, it's very likely an AI assistant (probably EliseAI)
        # These repetitive, helpful phrases are characteristic of AI leasing agents
        if pattern_matches >= 3:
            print(f"   🤖 Detected {pattern_matches} AI assistant patterns - likely EliseAI")
            return True
        
        # If no target disclaimer provided, only check strong indicators
        if not target_disclaimer:
            return False
        
        target_lower = target_disclaimer.lower()
        
        # Check for exact phrase match
        if target_lower in transcription_lower:
            return True
        
        # Also check for the policy part if it exists
        policy_phrase = "policy is at eliseai.com/policy"
        if policy_phrase in transcription_lower:
            return True
        
        # Check for key phrases that indicate the disclaimer
        # "recorded and used by a third party" is the key part
        key_phrases = [
            "recorded and used by a third party",
            "recorded and used by third party",
            "may be recorded and used",
            "recorded and used"
        ]
        
        for phrase in key_phrases:
            if phrase in transcription_lower:
                return True
        
        # Check for fuzzy match (at least 70% of key words present)
        # Lowered threshold to catch more variations
        target_words = set(target_lower.split())
        transcription_words = set(transcription_lower.split())
        
        if len(target_words) == 0:
            return False
        
        matching_words = target_words.intersection(transcription_words)
        match_ratio = len(matching_words) / len(target_words)
        
        # Also check if we have the critical words: "recorded", "third", "party"
        critical_words = ["recorded", "third", "party"]
        critical_found = sum(1 for word in critical_words if word in transcription_lower)
        
        if critical_found >= 2:  # At least 2 of 3 critical words
            return True
        
        return match_ratio >= 0.7  # Lowered from 0.8 to 0.7
    
    def transcribe_first_seconds(self, audio_data, seconds=10):
        """Transcribe just the first N seconds of audio to detect immediate messages"""
        if not self.client:
            return None
        
        try:
            import io
            import wave
            
            # Read the WAV file
            audio_io = io.BytesIO(audio_data)
            with wave.open(audio_io, 'rb') as wav_file:
                frames = wav_file.getnframes()
                sample_rate = wav_file.getframerate()
                channels = wav_file.getnchannels()
                sample_width = wav_file.getsampwidth()
                
                # Calculate frames for first N seconds
                frames_to_read = int(sample_rate * seconds)
                if frames_to_read > frames:
                    frames_to_read = frames
                
                # Read first N seconds
                wav_file.setpos(0)
                audio_data_first = wav_file.readframes(frames_to_read)
                
                # Create new WAV file with just first N seconds
                temp_file = 'temp_first_seconds.wav'
                with wave.open(temp_file, 'wb') as out_wav:
                    out_wav.setnchannels(channels)
                    out_wav.setsampwidth(sample_width)
                    out_wav.setframerate(sample_rate)
                    out_wav.writeframes(audio_data_first)
            
            # Transcribe
            with open(temp_file, 'rb') as audio_file:
                transcript = self.client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    response_format="verbose_json",
                    language="en"
                )
            
            return transcript.text if hasattr(transcript, 'text') else str(transcript)
        except Exception as e:
            print(f"Error transcribing first seconds: {str(e)}")
            return None
    
    def detect_immediate_message(self, audio_data, full_transcription):
        """Detect if there's an immediate automated message/disclaimer RIGHT AFTER dialing (before our message plays)"""
        if not audio_data:
            return {
                'has_immediate_message': False,
                'has_immediate_disclaimer': False,
                'immediate_message_text': '',
                'call_behavior': 'unknown'
            }
        
        # Transcribe just the FIRST 5 seconds to see what happens immediately when call connects
        first_5_seconds = self.transcribe_first_seconds(audio_data, seconds=5)
        
        if not first_5_seconds:
            return {
                'has_immediate_message': False,
                'has_immediate_disclaimer': False,
                'immediate_message_text': '',
                'call_behavior': 'no_audio_detected'
            }
        
        first_5_lower = first_5_seconds.lower()
        
        # Our message indicators - if we see these in first 5 seconds, it means our message started immediately
        # (no immediate message from them)
        our_message_indicators = [
            'test call from elise',
            'test call from elysia',
            'test call from a leasing',
            'please don\'t hang up',
            'we are testing out your phone'
        ]
        
        # Check if our message is in the first 5 seconds (means no immediate message from them)
        has_our_message = any(indicator in first_5_lower for indicator in our_message_indicators)
        
        # Ringing indicators (beep beep beep, etc.) - this means normal ringing, not immediate message
        ringing_indicators = [
            'beep',
            'ring',
            'tone',
            'busy signal'
        ]
        has_ringing = any(indicator in first_5_lower for indicator in ringing_indicators)
        
        # If we see our message or ringing, there's no immediate automated message
        if has_our_message:
            return {
                'has_immediate_message': False,
                'has_immediate_disclaimer': False,
                'immediate_message_text': '',
                'call_behavior': 'normal_ringing_or_immediate_connection'
            }
        
        if has_ringing:
            return {
                'has_immediate_message': False,
                'has_immediate_disclaimer': False,
                'immediate_message_text': first_5_seconds[:200],
                'call_behavior': 'normal_ringing'
            }
        
        # If we have substantial text in first 5 seconds that's NOT our message and NOT ringing,
        # it's an immediate automated message
        has_immediate = len(first_5_seconds.strip()) > 15  # More than 15 chars of actual speech
        
        has_disclaimer = False
        if has_immediate:
            # Check if it contains disclaimer
            disclaimer_indicators = [
                'recorded and used by a third party',
                'recorded and used by third party',
                'this call may be recorded',
                'call may be monitored',
                'recorded for quality',
                'virtual leasing agent',
                'virtual agent'
            ]
            has_disclaimer = any(indicator in first_5_lower for indicator in disclaimer_indicators)
            
            # Also check for common automated greetings
            automated_greeting_indicators = [
                'thank you for calling',
                'welcome to',
                'you have reached',
                'please listen carefully',
                'for english press',
                'para español',
                'press 1 for',
                'to speak with'
            ]
            has_automated_greeting = any(indicator in first_5_lower for indicator in automated_greeting_indicators)
            
            if has_automated_greeting or has_disclaimer:
                return {
                    'has_immediate_message': True,
                    'has_immediate_disclaimer': has_disclaimer,
                    'immediate_message_text': first_5_seconds[:200],
                    'call_behavior': 'immediate_automated_message'
                }
        
        # If we have some text but it's unclear, still report it
        if len(first_5_seconds.strip()) > 10:
            return {
                'has_immediate_message': True,
                'has_immediate_disclaimer': has_disclaimer,
                'immediate_message_text': first_5_seconds[:200],
                'call_behavior': 'possible_immediate_message'
            }
        
        return {
            'has_immediate_message': False,
            'has_immediate_disclaimer': False,
            'immediate_message_text': first_5_seconds[:200] if first_5_seconds else '',
            'call_behavior': 'silence_or_unclear'
        }
    
    def analyze_recording(self, recording_url, auth, skip_seconds=0):
        """
        Download, transcribe, and analyze a recording for the disclaimer.
        
        Args:
            recording_url: Twilio recording URL
            auth: Twilio auth tuple
            skip_seconds: Skip the first N seconds (to skip past menu navigation)
        """
        # Download the recording
        audio_data = self.download_recording(recording_url, auth)
        if not audio_data:
            return {
                'success': False,
                'transcription': None,
                'disclaimer_found': False,
                'immediate_message': None,
                'menu_duration': 10,
                'error': 'Failed to download recording'
            }
        
        # Extract only the INBOUND channel (their audio) from stereo recording
        # This removes our TTS message and only keeps what they said
        inbound_audio = self.extract_inbound_channel(audio_data)
        
        # If we have button presses, skip past the menus we already navigated
        if skip_seconds > 0:
            inbound_audio = self.trim_audio_start(inbound_audio, skip_seconds)
        
        # Check for immediate message at the start (FIRST 5 SECONDS ONLY)
        # This detects what happens RIGHT AFTER dialing, before our message plays
        immediate_info = self.detect_immediate_message(inbound_audio, None)
        
        # Transcribe the INBOUND audio with timing info (their voice only)
        transcription_result = self.transcribe_audio_with_timing(inbound_audio)
        if not transcription_result:
            return {
                'success': False,
                'transcription': None,
                'disclaimer_found': False,
                'immediate_message': immediate_info,
                'menu_duration': 10,
                'error': 'Failed to transcribe audio'
            }
        
        transcription = transcription_result['text']
        menu_duration = self.get_menu_duration(transcription_result)
        words = transcription_result.get('words', [])
        
        # Check for disclaimer in full transcription
        disclaimer_found = self.check_for_disclaimer(transcription, Config.TARGET_DISCLAIMER)
        
        return {
            'success': True,
            'transcription': transcription,
            'disclaimer_found': disclaimer_found,
            'immediate_message': immediate_info,
            'menu_duration': menu_duration,
            'words': words,
            'error': None
        }

