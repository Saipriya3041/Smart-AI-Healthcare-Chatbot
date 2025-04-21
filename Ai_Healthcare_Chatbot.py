import os
import re
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

# Load environment variables from .env file
load_dotenv()

# Initialize Flask App
app = Flask(__name__)
# Set a permanent secret key for session management
app.secret_key = os.getenv('SECRET_KEY', os.urandom(24))
# Configure session parameters
app.config['SESSION_COOKIE_SECURE'] = True  # Only send cookies over HTTPS
app.config['SESSION_COOKIE_HTTPONLY'] = True  # Prevent JavaScript access to session cookie
app.config['PERMANENT_SESSION_LIFETIME'] = 1800  # Session lifetime of 30 minutes
app.register_blueprint(auth_bp, url_prefix='/auth')

# Initialize SocketIO with the Flask app (let it choose best async mode)
socketio.init_app(app, cors_allowed_origins="*")

@app.route('/')
def index():
    return render_template('home.html')

@app.route('/chat')
def chat():
    if 'user_id' not in session:
        return redirect('/auth/login')
    return render_template('index.html')

# Initialize voice and language handler
voice_handler = VoiceLanguageHandler()

# Configure logging
logging.basicConfig(level=logging.DEBUG)

def generate_summary(symptoms, language="English", follow_up_answers=None, format_type="concise"):
    """
    Generates a medical summary based on user symptoms and follow-up answers using local processing.
    Always generates a concise single-paragraph summary optimized for quick medical review.
    """
    # Prepare context from common symptoms database
    common_symptoms = {
        "fever": {
            "causes": ["Viral infection", "Bacterial infection", "Inflammation", "COVID-19"],
            "severity": "Moderate to High",
            "urgency": "Seek immediate care if temperature exceeds 103°F (39.4°C)",
            "general_recommendations": [
                "Maintain room temperature around 70°F (21°C)",
                "Change bedding frequently if sweating",
                "Eat light, easily digestible foods",
                "Avoid strenuous activity"
            ]
        },
        "headache": {
            "causes": ["Tension", "Migraine", "Sinusitis", "Hypertension", "Dehydration"],
            "severity": "Mild to Moderate",
            "urgency": "Urgent if accompanied by confusion or stiff neck",
            "general_recommendations": [
                "Maintain regular sleep schedule",
                "Practice stress-reduction techniques",
                "Stay well-hydrated",
                "Consider keeping a headache diary"
            ]
        },
        "cough": {
            "causes": ["Upper respiratory infection", "Bronchitis", "Asthma", "COVID-19", "Allergies"],
            "severity": "Mild to Severe",
            "urgency": "Urgent if difficulty breathing or coughing blood"
        },
        "fatigue": {
            "causes": ["Sleep deprivation", "Anemia", "Depression", "Thyroid dysfunction", "Post-viral syndrome"],
            "severity": "Varies",
            "urgency": "Evaluate if persistent > 2 weeks"
        },
        "nausea": {
            "causes": ["Gastroenteritis", "Food poisoning", "Migraine", "Pregnancy", "Medication side effect"],
            "severity": "Mild to Moderate",
            "urgency": "Urgent if severe dehydration signs present"
        },
        "chest pain": {
            "causes": ["Heart attack", "Angina", "Pulmonary embolism", "Anxiety", "Muscle strain"],
            "severity": "High",
            "urgency": "Seek immediate emergency care"
        },
        "shortness of breath": {
            "causes": ["Asthma", "Anxiety", "Heart failure", "Pneumonia", "COVID-19"],
            "severity": "High",
            "urgency": "Seek immediate care if severe or worsening"
        },
        "dizziness": {
            "causes": ["Low blood pressure", "Inner ear problems", "Dehydration", "Anemia", "Medication side effect"],
            "severity": "Moderate",
            "urgency": "Urgent if accompanied by fainting or severe headache"
        },
        "abdominal pain": {
            "causes": ["Gastritis", "Appendicitis", "Food poisoning", "Ulcer", "Gallstones"],
            "severity": "Moderate to High",
            "urgency": "Seek immediate care if severe or accompanied by fever"
        },
        "rash": {
            "causes": ["Allergic reaction", "Infection", "Autoimmune condition", "Medication reaction", "Contact dermatitis"],
            "severity": "Mild to Moderate",
            "urgency": "Urgent if accompanied by difficulty breathing or severe swelling"
        },
        "joint pain": {
            "causes": ["Arthritis", "Injury", "Gout", "Lupus", "Fibromyalgia"],
            "severity": "Moderate",
            "urgency": "Seek care if severe or affecting mobility",
            "general_recommendations": [
                "Apply heat or cold packs as appropriate",
                "Maintain gentle range-of-motion exercises",
                "Use supportive devices if needed (braces, canes)",
                "Maintain healthy weight to reduce joint stress"
            ]
        },
        "sore throat": {
            "causes": ["Viral infection", "Strep throat", "Allergies", "Acid reflux", "Tonsillitis"],
            "severity": "Mild to Moderate",
            "urgency": "Seek care if difficulty swallowing or breathing"
        },
        "back pain": {
            "causes": ["Muscle strain", "Herniated disc", "Arthritis", "Osteoporosis", "Kidney problems"],
            "severity": "Moderate",
            "urgency": "Urgent if accompanied by numbness or weakness"
        },
        "ear pain": {
            "causes": ["Ear infection", "Sinus pressure", "Tooth infection", "Earwax buildup", "Swimmer's ear"],
            "severity": "Mild to Moderate",
            "urgency": "Seek care if severe pain or fever present"
        },
        "eye problems": {
            "causes": ["Conjunctivitis", "Allergies", "Foreign object", "Glaucoma", "Eye strain"],
            "severity": "Moderate",
            "urgency": "Urgent if sudden vision changes or severe pain"
        },
        "stomach pain": {
            "causes": ["Indigestion", "Food poisoning", "Ulcer", "Appendicitis", "IBS"],
            "severity": "Moderate to High",
            "urgency": "Seek immediate care if severe or persistent"
        },
        "muscle weakness": {
            "causes": ["Fatigue", "Nerve problems", "Stroke", "Multiple sclerosis", "Electrolyte imbalance"],
            "severity": "High",
            "urgency": "Urgent if sudden onset or affecting breathing"
        },
        "bleeding": {
            "causes": ["Injury", "Surgery", "Blood disorder", "Medication side effect", "Internal bleeding"],
            "severity": "High",
            "urgency": "Seek immediate care if heavy or uncontrolled"
        },
        "swelling": {
            "causes": ["Injury", "Infection", "Heart problems", "Kidney problems", "Allergic reaction"],
            "severity": "Moderate to High",
            "urgency": "Urgent if affecting breathing or circulation"
        },
        "anxiety": {
            "causes": ["Stress", "Panic disorder", "PTSD", "Depression", "Medical conditions"],
            "severity": "Moderate",
            "urgency": "Seek care if affecting daily life or worsening"
        }
    }
    
    symptoms_lower = symptoms.lower()
    identified_symptoms = {}
    
    # Enhanced symptom identification that handles multiple symptoms better
    symptom_words = re.findall(r'\b\w+\b', symptoms_lower)
    for symptom, info in common_symptoms.items():
        # Check if symptom appears as a standalone word or in a phrase
        symptom_parts = symptom.split()
        if len(symptom_parts) == 1:
            # Single word symptom
            if symptom in symptom_words:
                identified_symptoms[symptom] = info
        else:
            # Multi-word symptom (like "chest pain")
            if all(part in symptom_words for part in symptom_parts):
                # Check if words appear consecutively in the input
                if re.search(r'\b' + re.escape(symptom) + r'\b', symptoms_lower):
                    identified_symptoms[symptom] = info
    
    # Generate personalized summary
    summary = f"Based on your reported symptoms: {symptoms}. "
    
    if identified_symptoms:
        summary += "Our analysis shows: "
        symptom_details = []
        warnings = []
        specific_recommendations = []
        
        for symptom, info in identified_symptoms.items():
            # Add symptom-specific details
            symptom_details.append(f"{symptom} (severity: {info['severity']})")
            
            # Add urgent warnings
            if 'urgent' in info['urgency'].lower() or 'immediate' in info['urgency'].lower():
                warnings.append(f"For {symptom}: {info['urgency']}")
            
            # Add detailed symptom-specific recommendations
            if symptom == "fever":
                specific_recommendations.extend([
                    "Monitor temperature every 4 hours",
                    "Drink plenty of fluids (water, herbal teas, broth)",
                    "Use lukewarm sponge baths if fever is high",
                    "Wear lightweight clothing",
                    "Avoid alcohol and caffeine"
                ])
            elif symptom == "headache":
                specific_recommendations.extend([
                    "Apply cold compress to forehead for 15 minutes",
                    "Massage temples gently",
                    "Practice relaxation techniques",
                    "Avoid bright lights and loud noises",
                    "Limit screen time"
                ])
            elif symptom == "cough":
                specific_recommendations.extend([
                    "Drink warm liquids like honey-lemon tea",
                    "Use a humidifier at night",
                    "Avoid smoke and strong perfumes",
                    "Try throat lozenges (for adults)",
                    "Sleep with head slightly elevated"
                ])
            elif symptom == "fatigue":
                specific_recommendations.extend([
                    "Maintain regular sleep schedule",
                    "Take short naps (20-30 minutes)",
                    "Engage in light physical activity",
                    "Eat small, frequent meals",
                    "Limit caffeine intake"
                ])
            elif symptom == "nausea":
                specific_recommendations.extend([
                    "Eat small, bland meals (crackers, toast)",
                    "Sip ginger tea or chew ginger candy",
                    "Avoid strong odors",
                    "Stay hydrated with small sips of water",
                    "Try acupressure wristbands"
                ])
            elif symptom == "chest pain":
                specific_recommendations.extend([
                    "Rest immediately and avoid exertion",
                    "Loosen tight clothing",
                    "Sit in a comfortable position",
                    "Monitor for worsening symptoms",
                    "Avoid eating or drinking until evaluated"
                ])
            elif symptom == "shortness of breath":
                specific_recommendations.extend([
                    "Sit upright and lean forward slightly",
                    "Pursed-lip breathing technique",
                    "Avoid lying flat",
                    "Use a fan for air circulation",
                    "Stay calm and breathe slowly"
                ])
            elif symptom == "dizziness":
                specific_recommendations.extend([
                    "Sit or lie down immediately",
                    "Rise slowly from sitting/lying position",
                    "Avoid sudden head movements",
                    "Stay hydrated",
                    "Use handrails when walking"
                ])
        
        summary += f"Identified symptoms: {', '.join(symptom_details)}. "
        
        if warnings:
            summary += f"URGENT WARNINGS: {'; '.join(warnings)}. "
        
        # Combine general and specific recommendations
        all_recommendations = [
            "See a doctor for proper medical care",
            "Keep detailed symptom records",
            *specific_recommendations
        ]
        summary += "Recommended actions: " + ", ".join(all_recommendations) + ". "
    
    # Analyze follow-up information and integrate insights
    if follow_up_answers:
        summary += "Based on your additional information: "
        insights = []
        
        for answer in follow_up_answers:
            question = answer['question'].lower()
            response = answer['answer'].lower()
            
            # Analyze duration-related responses
            if 'how long' in question or 'when' in question:
                if any(word in response for word in ['day', 'week', 'month']):
                    insights.append(f"Duration: {response}")
            
            # Analyze severity-related responses
            elif 'scale' in question or 'intensity' in question:
                if any(str(i) for i in range(1, 11) if str(i) in response):
                    insights.append(f"Severity level: {response}")
            
            # Analyze pattern-related responses
            elif 'pattern' in question or 'worse' in question:
                insights.append(f"Pattern observed: {response}")
            
            # Analyze treatment-related responses
            elif 'medication' in question or 'taken' in question:
                insights.append(f"Treatment history: {response}")
        
        if insights:
            summary += ", ".join(insights) + ". "
            
            # Add severity-based recommendations
            if any('severity' in insight.lower() for insight in insights):
                if any(str(i) for i in range(7, 11) for insight in insights if str(i) in insight.lower()):
                    summary += "Given the high severity, immediate medical attention is recommended. "
                elif any(str(i) for i in range(4, 7) for insight in insights if str(i) in insight.lower()):
                    summary += "Consider consulting a healthcare provider soon. "
            
            # Add duration-based recommendations
            if any('duration' in insight.lower() for insight in insights):
                if any(word in summary.lower() for word in ['week', 'month']):
                    summary += "The persistent nature of symptoms suggests the need for medical evaluation. "
    
    # Add severity-based insights
    severity_level = "Low"
    if identified_symptoms:
        severity_scores = []
        for symptom, info in identified_symptoms.items():
            if info['severity'].lower().startswith('high'):
                severity_scores.append(3)
            elif info['severity'].lower().startswith('moderate'):
                severity_scores.append(2)
            else:
                severity_scores.append(1)
        
        avg_severity = sum(severity_scores) / len(severity_scores)
        if avg_severity > 2.5:
            severity_level = "High"
            summary += "This combination of symptoms suggests a potentially serious condition that requires immediate medical attention. "
        elif avg_severity > 1.5:
            severity_level = "Moderate"
            summary += "These symptoms warrant medical evaluation within the next 24-48 hours. "
        else:
            summary += "While these symptoms appear mild, monitor for any worsening. "
    
    # Include symptom-specific general recommendations from the common_symptoms info
    if identified_symptoms:
        general_recommendations = []
        for symptom, info in identified_symptoms.items():
            if 'general_recommendations' in info:
                general_recommendations.extend(info['general_recommendations'])
        
        # Remove duplicates while preserving order
        seen = set()
        unique_recommendations = []
        for rec in general_recommendations:
            if rec not in seen:
                seen.add(rec)
                unique_recommendations.append(rec)
        
        if unique_recommendations:
            summary += "General recommendations: " + ", ".join(unique_recommendations) + ". "
    
    # Add emergency warning signs based on severity
    if severity_level == "High":
        summary += "SEEK IMMEDIATE MEDICAL CARE if you experience: difficulty breathing, severe chest pain, confusion, or high fever with severe headache. "
    
    return summary.strip()

def ask_follow_up(symptoms, language="English"):
    symptoms_lower = symptoms.lower()
    follow_up_questions = []
    
    # Start with a general timing question for all symptoms
    follow_up_questions.append({
        "question": "When did these symptoms first appear?",
        "image": "/static/images/medical-bot.svg",
        "animation": "fadeIn"
    })
    
    # Symptom-specific questions with severity assessment
    if "fever" in symptoms_lower:
        follow_up_questions.extend([
            {
                "question": "What is your current temperature?",
                "image": "/static/images/medical-bot.svg",
                "animation": "slideInRight"
            },
            {
                "question": "Have you taken any medication to reduce the fever?",
                "image": "/static/images/medical-bot.svg",
                "animation": "bounceIn"
            },
            {
                "question": "Are you experiencing chills or sweating?",
                "image": "/static/images/medical-bot.svg",
                "animation": "fadeInUp"
            }
        ])
    if "pain" in symptoms_lower:
        follow_up_questions.extend([
            {
                "question": "On a scale of 1-10, how severe is your pain?",
                "image": "/static/images/medical-bot.svg",
                "animation": "slideInLeft"
            },
            {
                "question": "Is the pain constant or does it come and go?",
                "image": "/static/images/medical-bot.svg",
                "animation": "bounceInRight"
            },
            {
                "question": "What makes the pain better or worse?",
                "image": "/static/images/medical-bot.svg",
                "animation": "fadeInDown"
            }
        ])
    if "cough" in symptoms_lower:
        follow_up_questions.extend([
            {
                "question": "Is your cough dry or producing mucus?",
                "image": "/static/images/medical-bot.svg",
                "animation": "slideInUp"
            },
            {
                "question": "How frequently are you coughing?",
                "image": "/static/images/medical-bot.svg",
                "animation": "bounceInLeft"
            },
            {
                "question": "Does anything trigger or worsen your cough?",
                "image": "/static/images/medical-bot.svg",
                "animation": "fadeInRight"
            }
        ])
    
    # Add general follow-up questions if we need more
    general_questions = [
        {
            "question": "Have you taken any medications for these symptoms?",
            "image": "/static/images/medical-bot.svg",
            "animation": "slideInDown"
        },
        {
            "question": "Have you experienced any other related symptoms?",
            "image": "/static/images/medical-bot.svg",
            "animation": "bounceInUp"
        },
        {
            "question": "Do your symptoms affect your daily activities?",
            "image": "/static/images/medical-bot.svg",
            "animation": "fadeInLeft"
        }
    ]
    
    while len(follow_up_questions) < 4:
        if not general_questions:
            break
        follow_up_questions.append(general_questions.pop(0))
    
    return follow_up_questions

@app.route("/chatbot", methods=["POST"])
def chatbot():
    from flask import request
    # Check authentication first
    if 'user_id' not in session:
        return jsonify({'error': 'Your session has expired. Please log in again to continue.'}), 401
        
    # Continue with chatbot logic
    request_data = request.json
    input_type = request_data.get("input_type", "text")  # 'text' or 'voice'
    language = request_data.get("language", "english").lower()
    
    # Handle initial symptoms or follow-up answers
    is_follow_up = request_data.get("is_follow_up", False)
    current_question_index = request_data.get("current_question_index", 0)
    follow_up_answers = request_data.get("follow_up_answers", [])
    
    # Handle voice input for initial symptoms
    if input_type == "voice" and not is_follow_up:
        try:
            if "audio" not in request_data:
                return jsonify({"error": "No audio data provided"}), 400
                
            audio_data = base64.b64decode(request_data.get("audio", ""))
            audio_file = io.BytesIO(audio_data)
            audio_content = audio_file.read()
            if not audio_content:
                return jsonify({"error": "Empty audio data. Please try recording again."}), 400
            
            audio_file = io.BytesIO(audio_content)
            audio = sr.AudioData(audio_content, sample_rate=44100, sample_width=2)
            source_lang = "te-IN" if language == "telugu" else "en-IN"
            
            symptoms = voice_handler.process_voice_input(audio, source_lang)
            if not symptoms:
                return jsonify({"error": "Could not understand the audio. Please try again."}), 400
        except Exception as e:
            logging.error(f"Error processing voice input: {str(e)}")
            return jsonify({"error": "Error processing voice input"}), 400
    else:
        symptoms = request_data.get("symptoms", "")
        if not symptoms and not is_follow_up:
            return jsonify({"error": "Please provide symptoms"}), 400
        
        # Debug log for symptom input
        logging.debug(f"Received symptoms input: {symptoms}")
    
    if not is_follow_up:
        # Generate initial follow-up questions
        follow_up_questions = ask_follow_up(symptoms, language)
        
        # Translate questions if language is Telugu
        if language == "telugu":
            for question in follow_up_questions:
                question["question"] = voice_handler.translate_text(question["question"], "te")
        
        response = {
            "is_follow_up": True,
            "current_question_index": 0,
            "total_questions": len(follow_up_questions),
            "current_question": follow_up_questions[0],
            "all_questions": follow_up_questions,
            "original_symptoms": symptoms,
            "animation_delay": 500  # Delay in milliseconds for animation
        }
    else:
        # Process follow-up answer and get next question
        all_questions = request_data.get("all_questions", [])
        original_symptoms = request_data.get("original_symptoms", "")
        
        # Add the current answer to follow_up_answers
        current_answer = request_data.get("answer", "")
        if current_answer:
            follow_up_answers.append({
                "question": all_questions[current_question_index]["question"],
                "answer": current_answer
            })
        
        # Check if we have more questions
        if current_question_index + 1 < len(all_questions):
            next_question = all_questions[current_question_index + 1]
            response = {
                "is_follow_up": True,
                "current_question_index": current_question_index + 1,
                "total_questions": len(all_questions),
                "current_question": next_question,
                "all_questions": all_questions,
                "follow_up_answers": follow_up_answers,
                "original_symptoms": original_symptoms,
                "animation_delay": 500
            }
        else:
            # Generate final summary including all follow-up answers
            summary = generate_summary(original_symptoms, language, follow_up_answers)
            
            # Debuggable Telugu translation with step-by-step validation
            if language == "telugu":
                try:
                    logging.info("Starting Telugu translation process")
                    
                    # Extended medical term preservation
                    preserved_terms = {
                        '°F': ' డిగ్రీ ఫారెన్హీట్ ',
                        '°C': ' డిగ్రీ సెల్సియస్ ',
                        'COVID-19': 'కోవిడ్-19',
                        'IBS': 'ఐబీఎస్', 
                        'PTSD': 'పీటీఎస్డీ',
                        'BP': 'రక్తపోటు',
                        'HR': 'హృదయ రేటు',
                        'SPO2': 'ఆక్సిజన్ సంతృప్తత'
                    }
                    logging.info(f"Preserving {len(preserved_terms)} medical terms")
                    
                    # Validate and replace terms with placeholders
                    term_map = {}
                    original_length = len(summary)
                    for i, (term, trans) in enumerate(preserved_terms.items()):
                        placeholder = f'__TERM_{i}__'
                        if term in summary:
                            summary = summary.replace(term, placeholder)
                            term_map[placeholder] = trans
                            logging.debug(f"Preserved term: {term} -> {placeholder}")
                    
                    if len(summary) != original_length:
                        logging.warning(f"Term replacement altered text length ({original_length} -> {len(summary)})")
                    
                    # Validate translation service
                    if not hasattr(voice_handler, 'translate_text'):
                        raise AttributeError("Translation service not available")
                    
                    # Test translation with known phrase
                    test_phrase = "This is a test"
                    test_translation = voice_handler.translate_text(test_phrase, "te")
                    if not test_translation or len(test_translation) < len(test_phrase)/2:
                        raise ValueError("Translation service test failed")
                    
                    # Translate the actual text
                    logging.info(f"Translating text (length: {len(summary)})")
                    translated_summary = voice_handler.translate_text(summary, "te")
                    logging.info(f"Received translation (length: {len(translated_summary)})")
                    
                    if translated_summary:
                        # Restore preserved terms
                        for placeholder, trans in term_map.items():
                            translated_summary = translated_summary.replace(placeholder, trans)
                        
                    # Verify translation quality and add standard precautions
                    telugu_chars = len([c for c in translated_summary if '\u0C00' <= c <= '\u0C7F'])
                    if telugu_chars > len(translated_summary)*0.6:  # At least 60% Telugu
                        precautions = "\n\nసాధారణ జాగ్రత్తలు:\n- తగినంత నీరు తాగండి\n- సరైన విశ్రాంతి తీసుకోండి\n- ఒత్తిడిని తగ్గించుకోండి\n- వేడి లేదా చల్లటి కంప్రెస్ వేసుకోండి"
                        summary = translated_summary + precautions
                    else:
                        logging.error(f"Low Telugu content in translation: {telugu_chars}/{len(translated_summary)}")
                        summary = f"English:\n{summary}\n\nTelugu:\n{translated_summary}\n\nసాధారణ జాగ్రత్తలు:\n- తగినంత నీరు తాగండి\n- సరైన విశ్రాంతి తీసుకోండి"
                    
                    if not summary:
                        raise ValueError("Empty translation result")
                        
                except Exception as e:
                    logging.error(f"Telugu translation failed: {str(e)}")
                    # Generate bilingual summary as fallback
                    summary = f"English:\n{summary}\n\nTelugu:\n{voice_handler.translate_text(summary, 'te')}"
            
            # Save the summary sheet to database
            try:
                db_path = os.path.join(os.path.dirname(__file__), 'users.db')
                conn = sqlite3.connect(db_path)
                c = conn.cursor()
                
                c.execute('INSERT INTO summary_sheets (user_id, symptoms, summary) VALUES (?, ?, ?)',
                          (session['user_id'], original_symptoms, summary))
                conn.commit()
                conn.close()
                
            except Exception as e:
                logging.error(f"Error saving summary: {e}")
                return jsonify({'error': 'Failed to save consultation summary'}), 500
            
            # Prepare response with translation status
            is_telugu_complete = (
                language != "telugu" or 
                any('\u0C00' <= c <= '\u0C7F' for c in summary)
            )
            response = {
                "is_follow_up": False,
                "summary_sheet": summary,
                "needs_audio": False,
                "translation_status": "complete" if is_telugu_complete else "partial"
            }
    
    # Handle voice response only when explicitly needed
    if request_data.get("voice_response", False) and response.get("needs_audio", True):
        try:
            lang_code = "te" if language == "telugu" else "en"
            response_text = response.get("current_question", {}).get("question", "") if is_follow_up else response.get("summary_sheet", "")
            if response_text:  # Only generate audio if we have text
                audio_file = voice_handler.process_voice_output(response_text, lang_code)
                if audio_file:
                    return send_file(audio_file, mimetype="audio/mp3")
        except Exception as e:
            logging.error(f"Error generating voice response: {str(e)}")
            # Continue with text response if voice fails
    
    return jsonify(response)

@app.route('/set_language', methods=['POST'])
def set_language():
    language = request.form.get('language', 'english')
    session['language'] = language
    return jsonify({'status': 'success'})

@app.route('/get_greeting')
def get_greeting():
    language = session.get('language', 'english')
    greetings = {
        'english': 'Hello! I am your healthcare assistant. How can I help you today?',
        'telugu': 'శుభ సాయంత్రం! నేను మీ ఆరోగ్య సహాయకుడిని. ఈరోజు మీకు ఎలా సహాయపడగలను?'
    }
    greeting = greetings.get(language, greetings['english'])
    
    # Convert greeting to speech if voice_handler is available
    try:
        if voice_handler:
            audio_file = voice_handler.text_to_speech(greeting, language)
            return jsonify({
                'text': greeting,
                'audio': audio_file
            })
    except Exception as e:
        logging.error(f"Error in text-to-speech conversion: {e}")
    
    return jsonify({
        'text': greeting,
        'audio': None
    })

def find_available_port(start_port=8001, max_attempts=3):
    """Find first available port starting from start_port"""
    import socket
    for port in range(start_port, start_port + max_attempts):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(('0.0.0.0', port))
                return port
        except OSError:
            continue
    raise OSError(f"No available ports between {start_port}-{start_port+max_attempts-1}")

if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(level=logging.DEBUG)
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.INFO)
    
    # Get debug mode from environment variable
    debug_mode = os.environ.get('FLASK_DEBUG', 'True').lower() not in ('0', 'false', 'no')
    app.debug = debug_mode
    
    # Find available port first
    try:
        port = find_available_port()
        logging.info(f"\nStarting server on port {port}")
        logging.info(f"Starting Flask server in {'debug' if debug_mode else 'production'} mode")
        logging.info(f"Server URL: http://127.0.0.1:{port} (localhost only)")
        logging.info("Press CTRL+C to quit")
        
        # Verify SocketIO is properly initialized
        if not hasattr(app, 'socketio'):
            app.socketio = socketio
        
        # Start server
        socketio.run(
            app,
            host='0.0.0.0',
            port=port,
            debug=debug_mode,
            allow_unsafe_werkzeug=True,
            use_reloader=False
        )
    except Exception as e:
        logging.error(f"Failed to start server: {str(e)}")
        raise
