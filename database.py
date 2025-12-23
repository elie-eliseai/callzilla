import csv
import os
from datetime import datetime
from threading import Lock

class CallDatabase:
    """Simple CSV-based database for tracking call results"""
    
    def __init__(self, results_file='call_results.csv'):
        self.results_file = results_file
        self.lock = Lock()
        self._initialize_results_file()
    
    def _initialize_results_file(self):
        """Initialize the results CSV file with headers if it doesn't exist or update if needed"""
        if not os.path.exists(self.results_file):
            with open(self.results_file, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([
                    'Property Name',
                    'Phone Number',
                    'Call SID',
                    'Attempt Number',
                    'Status',
                    'Classification',
                    'GPT Reasoning',
                    'Button Pressed',
                    'Button Sequence',
                    'Human Detected',
                    'TTS Confirmed',
                    'AI Reached',
                    'Disclaimer Found',
                    'Needs Review',
                    'Review Issues',
                    'Review Reasoning',
                    'Immediate Message',
                    'Immediate Disclaimer',
                    'Transcription',
                    'Timestamp',
                    'Recording URL'
                ])
        else:
            # Check if file needs to be updated with new columns
            with open(self.results_file, 'r') as f:
                reader = csv.reader(f)
                headers = next(reader, None)
                if headers and 'Immediate Message' not in headers:
                    # Need to add new columns - read all data and rewrite
                    f.seek(0)
                    rows = list(csv.reader(f))
                    if rows:
                        # Update headers
                        old_headers = rows[0]
                        new_headers = old_headers.copy()
                        # Insert new columns before Transcription
                        if 'Transcription' in new_headers:
                            idx = new_headers.index('Transcription')
                            new_headers.insert(idx, 'Immediate Disclaimer')
                            new_headers.insert(idx, 'Immediate Message')
                        else:
                            new_headers.extend(['Immediate Message', 'Immediate Disclaimer'])
                        
                        # Update all rows with empty values for new columns
                        updated_rows = [new_headers]
                        for row in rows[1:]:
                            if 'Transcription' in old_headers:
                                idx = old_headers.index('Transcription')
                                row.insert(idx, 'False')  # Immediate Disclaimer
                                row.insert(idx, 'False')  # Immediate Message
                            else:
                                row.extend(['False', 'False'])
                            updated_rows.append(row)
                        
                        # Write back
                        with open(self.results_file, 'w', newline='') as f:
                            writer = csv.writer(f)
                            writer.writerows(updated_rows)
    
    def log_call(self, property_name, phone_number, call_sid, attempt_number, 
                 status, human_detected=False, tts_confirmed=None, ai_reached=False, 
                 disclaimer_found=False, immediate_message=False, 
                 immediate_disclaimer=False, transcription='', recording_url='',
                 classification='', gpt_reasoning='', button_pressed='', button_sequence='',
                 needs_review=False, review_issues='', review_reasoning=''):
        """Log a call result to the CSV file"""
        with self.lock:
            with open(self.results_file, 'a', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([
                    property_name,
                    phone_number,
                    call_sid,
                    attempt_number,
                    status,
                    classification,
                    gpt_reasoning,
                    button_pressed,
                    button_sequence,
                    human_detected,
                    tts_confirmed if tts_confirmed is not None else '',
                    ai_reached,
                    disclaimer_found,
                    needs_review,
                    review_issues,
                    review_reasoning,
                    immediate_message,
                    immediate_disclaimer,
                    transcription,
                    datetime.now().isoformat(),
                    recording_url
                ])
    
    def get_call_state(self, phone_number):
        """Get the current state of calls for a phone number"""
        if not os.path.exists(self.results_file):
            return None
        
        with self.lock:
            with open(self.results_file, 'r') as f:
                reader = csv.DictReader(f)
                calls = [row for row in reader if row['Phone Number'] == phone_number]
                return calls if calls else None
    
    def needs_second_attempt(self, phone_number):
        """Check if a phone number needs a second attempt"""
        calls = self.get_call_state(phone_number)
        if not calls:
            return False
        
        # Check if first attempt detected a human and second attempt hasn't been made
        for call in calls:
            if call['Attempt Number'] == '1' and call['Human Detected'] == 'True':
                # Check if there's already a second attempt
                second_attempts = [c for c in calls if c['Attempt Number'] == '2']
                return len(second_attempts) == 0
        
        return False
    
    def is_complete(self, phone_number):
        """Check if processing for a phone number is complete"""
        calls = self.get_call_state(phone_number)
        if not calls:
            return False
        
        # Complete if we have AI reached status or failed after retries
        for call in calls:
            if call['AI Reached'] == 'True' or call['Status'] == 'failed':
                return True
        
        return False

