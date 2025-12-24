#!/usr/bin/env python3
"""
Flask web application for Twilio Automated Calling System
"""

import os
import json
import threading
import time
from flask import Flask, render_template, request, jsonify, send_file, Response
from werkzeug.utils import secure_filename
from twilio.twiml.voice_response import VoiceResponse
from simple_production_caller import SimpleProductionCaller, load_properties_from_csv
from config import Config

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size
app.config['SECRET_KEY'] = os.urandom(24)

# Ensure upload directory exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Global job state
job_state = {
    'status': 'idle',  # idle, running, completed, error
    'progress': {
        'current': 0,
        'total': 0,
        'current_property': None,
        'status_message': ''
    },
    'results_file': None,
    'error': None
}

job_lock = threading.Lock()
job_thread = None

def allowed_file(filename):
    """Check if file extension is allowed"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() == 'csv'

def run_calls_job(csv_path):
    """Run calls in background thread"""
    global job_state
    
    try:
        with job_lock:
            job_state['status'] = 'running'
            job_state['error'] = None
            job_state['progress'] = {
                'current': 0,
                'total': 0,
                'current_property': None,
                'status_message': 'Loading properties...'
            }
        
        # Load properties
        properties = load_properties_from_csv(csv_path)
        
        if not properties:
            with job_lock:
                job_state['status'] = 'error'
                job_state['error'] = 'Failed to load properties from CSV'
            return
        
        with job_lock:
            job_state['progress']['total'] = len(properties)
            job_state['progress']['status_message'] = f'Starting calls for {len(properties)} properties...'
        
        # Initialize caller
        caller = SimpleProductionCaller()
        
        # Process each property
        for i, prop in enumerate(properties, 1):
            with job_lock:
                job_state['progress']['current'] = i
                job_state['progress']['current_property'] = prop['name']
                job_state['progress']['status_message'] = f'Processing {prop["name"]} ({i}/{len(properties)})'
            
            caller.process_property(prop)
            
            # Wait between calls (except for last one)
            if i < len(properties):
                time.sleep(5)
        
        with job_lock:
            job_state['status'] = 'completed'
            job_state['progress']['current'] = len(properties)
            job_state['progress']['status_message'] = 'All calls completed!'
            job_state['results_file'] = Config.RESULTS_FILE
            
    except Exception as e:
        with job_lock:
            job_state['status'] = 'error'
            job_state['error'] = str(e)

@app.route('/')
def index():
    """Main page"""
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    """Handle CSV file upload and start processing"""
    global job_thread, job_state
    
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    
    file = request.files['file']
    
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    if not allowed_file(file.filename):
        return jsonify({'error': 'Only CSV files are allowed'}), 400
    
    # Check if job is already running
    with job_lock:
        if job_state['status'] == 'running':
            return jsonify({'error': 'A job is already running'}), 400
    
    # Save uploaded file
    filename = secure_filename(file.filename)
    csv_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(csv_path)
    
    # Start background job
    job_thread = threading.Thread(target=run_calls_job, args=(csv_path,), daemon=True)
    job_thread.start()
    
    return jsonify({
        'success': True,
        'message': 'File uploaded and processing started'
    })

@app.route('/status', methods=['GET'])
def get_status():
    """Get current job status"""
    with job_lock:
        return jsonify({
            'status': job_state['status'],
            'progress': job_state['progress'],
            'error': job_state['error'],
            'results_file': job_state['results_file']
        })

@app.route('/results', methods=['GET'])
def get_results():
    """Get results CSV file"""
    results_file = Config.RESULTS_FILE
    if os.path.exists(results_file):
        return send_file(results_file, mimetype='text/csv', as_attachment=True)
    return jsonify({'error': 'Results file not found'}), 404

@app.route('/results-json', methods=['GET'])
def get_results_json():
    """Get results as JSON"""
    import pandas as pd
    results_file = Config.RESULTS_FILE
    if not os.path.exists(results_file):
        return jsonify({'error': 'Results file not found'}), 404
    
    try:
        df = pd.read_csv(results_file)
        return jsonify({
            'success': True,
            'data': df.to_dict('records'),
            'total': len(df)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/reset', methods=['POST'])
def reset_job():
    """Reset job state"""
    global job_state
    with job_lock:
        if job_state['status'] == 'running':
            return jsonify({'error': 'Cannot reset while job is running'}), 400
        job_state = {
            'status': 'idle',
            'progress': {
                'current': 0,
                'total': 0,
                'current_property': None,
                'status_message': ''
            },
            'results_file': None,
            'error': None
        }
    return jsonify({'success': True})


# =============================================================================
# TWILIO WEBHOOKS - For live speech detection
# =============================================================================

@app.route('/voice/speech-detected', methods=['POST'])
def speech_detected():
    """
    Webhook called by Twilio when speech is detected after button presses.
    This means someone answered - play the TTS message and keep recording.
    """
    print(f"\n🗣️ WEBHOOK HIT: /voice/speech-detected")
    print(f"   📞 Playing TTS message and continuing to record...")
    
    response = VoiceResponse()
    
    # Play TTS message - human/AI will hear this!
    response.say(
        Config.HUMAN_MESSAGE,
        voice='Polly.Joanna',
        language='en-US'
    )
    
    # Keep recording the conversation (don't hang up!)
    # timeout=30: stop after 30s of silence
    # max_length=120: max 2 minutes of recording
    response.record(timeout=30, max_length=120, play_beep=False)
    
    print(f"   ✅ TTS + Record TwiML returned to Twilio")
    return Response(str(response), mimetype='text/xml')


@app.route('/voice/no-speech', methods=['POST'])
def no_speech():
    """
    Webhook called when no speech detected (timeout).
    Might be voicemail, AI, or another call tree.
    Keep recording to capture whatever plays.
    """
    print(f"\n🔇 WEBHOOK HIT: /voice/no-speech")
    print(f"   📼 No speech detected, continuing to record...")
    
    response = VoiceResponse()
    
    # No speech detected - might be voicemail/AI greeting
    # Keep recording to capture it
    response.record(timeout=30, max_length=120, play_beep=False)
    
    return Response(str(response), mimetype='text/xml')


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



if __name__ == '__main__':
    Config.validate()
    app.run(debug=True, host='0.0.0.0', port=Config.FLASK_PORT)

