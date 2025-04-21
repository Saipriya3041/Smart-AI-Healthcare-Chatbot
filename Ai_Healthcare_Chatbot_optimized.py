import os
from flask import Flask, request, jsonify, send_file, session, render_template, redirect, current_app
import logging
from dotenv import load_dotenv
from voice_language_handler import VoiceLanguageHandler
import speech_recognition as sr
import base64
import io
import sqlite3
from auth import auth_bp
from websocket_handler import socketio
from functools import lru_cache
import re

# Load environment variables from .env file
load_dotenv()

# Initialize Flask App with correct template path
app = Flask(__name__, template_folder=os.path.join(os.path.dirname(__file__), 'templates'))
# Set a permanent secret key for session management
app.secret_key = os.getenv('SECRET_KEY', os.urandom(24))
# Configure session parameters
app.config['SESSION_COOKIE_SECURE'] = True
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['PERMANENT_SESSION_LIFETIME'] = 1800
app.register_blueprint(auth_bp, url_prefix='/auth')

# Initialize SocketIO with the Flask app
socketio.init_app(app, cors_allowed_origins="*")

@app.route('/')
def index():
    return render_template('home.html')

@app.route('/chat')
def chat():
    if 'user_id' not in session:
        return redirect('/auth/login')
    return render_template('index.html')

# Common symptoms database with follow-up questions
common_symptoms = {
    "fever": {
        "causes": ["Viral infection", "Bacterial infection", "Inflammation", "COVID-19"],
        "severity": "Moderate to High",
        "urgency": "Seek immediate care if temperature exceeds 103°F (39.4°C)",
        "follow_up": {
            "english": [
                "How long have you had the fever?",
                "Is the fever continuous or intermittent?",
                "Are you experiencing chills or sweating?"
            ],
            "telugu": [
                "మీకు జ్వరం ఎంతకాలంగా ఉంది?",
                "జ్వరం నిరంతరంగా ఉందా లేక మధ్య మధ్య వస్తుందా?",
                "మీకు చలి లేక చెమటలు వస్తున్నాయా?"
            ]
        }
    },
    "headache": {
        "causes": ["Tension", "Migraine", "Sinusitis", "Hypertension", "Dehydration"],
        "severity": "Mild to Moderate",
        "urgency": "Urgent if accompanied by confusion or stiff neck"
    },
    "cough": {
        "causes": ["Upper respiratory infection", "Bronchitis", "Asthma", "COVID-19", "Allergies"],
        "severity": "Mild to Severe",
        "urgency": "Urgent if difficulty breathing or coughing blood"
    },
    # [Include all other symptoms from original file...]
    # ... rest of the symptom dictionary ...
}

# Pre-compile symptom patterns
SYMPTOM_PATTERNS = {re.compile(r'\b'+s+r'\b'): info for s, info in common_symptoms.items()}

# [Rest of the existing code...]

# Modify generate_summary() to use pre-compiled patterns with language support
def generate_summary(symptoms, language="english", follow_up_answers=None, format_type="concise"):
    symptoms_lower = symptoms.lower()
    identified_symptoms = {}
    follow_up_questions = []
    
    # Configure logging to both console and file
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    
    # File handler
    log_path = os.path.join(os.path.dirname(__file__), 'chatbot_debug.log')
    file_handler = logging.FileHandler(log_path, mode='w')
    file_handler.setLevel(logging.INFO)
    
    # Formatter
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    console_handler.setFormatter(formatter)
    file_handler.setFormatter(formatter)
    
    # Add handlers
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)
    
    for pattern, info in SYMPTOM_PATTERNS.items():
        match = pattern.search(symptoms_lower)
        if match:
            logging.info(f"Matched symptom: {pattern.pattern}")
            identified_symptoms[pattern.pattern[2:-2]] = info
            if "follow_up" in info:
                logging.info(f"Found follow-up questions for: {pattern.pattern}")
                follow_up_questions.extend(info["follow_up"][language][:2])
    
    # Add Telugu translations for responses
    if language == "telugu":
        response = {
            "summary": "మీ లక్షణాల ఆధారంగా సారాంశం",
            "advice": "వైద్య సలహా కోసం సంప్రదించండి",
            "symptoms": identified_symptoms
        }
    else:
        response = {
            "summary": "Summary based on your symptoms",
            "advice": "Consult a doctor for medical advice",
            "symptoms": identified_symptoms
        }
    
    if follow_up_questions:
        logging.info(f"Generated follow-up questions: {follow_up_questions}")
        response.update({
            "is_follow_up": True,
            "current_question": {
                "question": follow_up_questions[0],
                "index": 0
            },
            "all_questions": follow_up_questions,
            "current_question_index": 0,
            "total_questions": len(follow_up_questions)
        })
        session['pending_questions'] = follow_up_questions
        session['current_question_index'] = 0
        logging.info(f"Response with follow-up: {response}")
    
    return response

@app.route("/chatbot", methods=["POST"])
def chatbot():
    # Check authentication first
    if 'user_id' not in session:
        error_msg = 'మీ సెషన్ కాలముగిసింది. కొనసాగడానికి దయచేసి మళ్లీ లాగిన్ అవండి.' if session.get('language') == 'telugu' else 'Your session has expired. Please log in again to continue.'
        return jsonify({'error': error_msg}), 401
        
    # Get input data
    request_data = request.json
    input_type = request_data.get("input_type", "text")  # 'text' or 'voice'
    user_input = request_data.get("input", "")
    language = session.get('language', 'english').lower()

    # Handle voice input
    if input_type == "voice":
        try:
            voice_handler = VoiceLanguageHandler(language)
            user_input = voice_handler.process_voice_input(request_data['voice_data'])
        except Exception as e:
            error_msg = 'వాయిస్ ఇన్పుట్ ప్రాసెస్ చేయడంలో లోపం' if language == 'telugu' else 'Error processing voice input'
            return jsonify({'error': error_msg}), 400

    # Process input and generate response
    is_follow_up = request_data.get("is_follow_up", False)
    current_question_index = request_data.get("current_question_index", 0)
    
    if is_follow_up:
        # Handle follow-up answer
        answer = request_data.get("answer")
        all_questions = request_data.get("all_questions")
        original_symptoms = request_data.get("original_symptoms", user_input)
        
        # Store answer in session
        if 'follow_up_answers' not in session:
            session['follow_up_answers'] = {}
        session['follow_up_answers'][current_question_index] = answer
        
        # Check if there are more questions
        next_index = current_question_index + 1
        if next_index < len(all_questions):
            response = {
                "is_follow_up": True,
                "current_question": {
                    "question": all_questions[next_index],
                    "index": next_index
                },
                "all_questions": all_questions,
                "current_question_index": next_index,
                "total_questions": len(all_questions),
                "original_symptoms": original_symptoms
            }
        else:
            # All questions answered - generate final summary
            response = generate_summary(original_symptoms, language, session.get('follow_up_answers'))
    else:
        # Initial symptom input
        response = generate_summary(user_input, language)
    
    logging.info(f"Sending final response: {response}")
    return jsonify(response)

# [Add the new optimized configurations...]

if __name__ == "__main__":
    import argparse
    
    # Set up command line argument parsing
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=5001,
                       help='Port to run the application on')
    parser.add_argument('--debug', action='store_true',
                       help='Enable debug mode')
    args = parser.parse_args()

    # Production-optimized configuration
    app.config.update(
        DEBUG=False,
        TEMPLATES_AUTO_RELOAD=False,
        JSONIFY_PRETTYPRINT_REGULAR=False,
        SEND_FILE_MAX_AGE_DEFAULT=3600
    )
    
    # Run with appropriate settings
    try:
        print(f"Attempting to start server on port {args.port}...")
        socketio.run(app, host='0.0.0.0', port=args.port, 
                    debug=args.debug, 
                    allow_unsafe_werkzeug=args.debug,
                    log_output=args.debug)
    except Exception as e:
        print(f"Failed to start server: {str(e)}")
        import traceback
        traceback.print_exc()
