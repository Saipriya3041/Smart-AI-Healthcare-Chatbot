from flask import Blueprint, request, jsonify, session, render_template
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import sqlite3
import os

auth_bp = Blueprint('auth', __name__)

# Initialize SQLite database
def init_db():
    db_path = os.path.join(os.path.dirname(__file__), 'users.db')
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    
    # Create users table
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Create summary_sheets table
    c.execute('''
        CREATE TABLE IF NOT EXISTS summary_sheets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            symptoms TEXT NOT NULL,
            summary TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    
    conn.commit()
    conn.close()

# Initialize database on startup
init_db()

@auth_bp.route('/signup', methods=['GET'])
def signup_page():
    return render_template('signup.html')

@auth_bp.route('/login', methods=['GET'])
def login_page():
    return render_template('login.html')

@auth_bp.route('/profile')
def profile_page():
    if 'user_id' not in session:
        return redirect('/auth/login')
    return render_template('profile.html')

@auth_bp.route('/signup', methods=['POST'])
def signup():
    data = request.json
    username = data.get('username')
    password = data.get('password')
    
    if not username or not password:
        return jsonify({'error': 'Username and password are required'}), 400
    
    try:
        db_path = os.path.join(os.path.dirname(__file__), 'users.db')
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        
        # Check if username already exists
        c.execute('SELECT id FROM users WHERE username = ?', (username,))
        if c.fetchone() is not None:
            return jsonify({'error': 'Username already exists'}), 400
        
        # Hash password and store user
        password_hash = generate_password_hash(password)
        c.execute('INSERT INTO users (username, password_hash) VALUES (?, ?)',
                  (username, password_hash))
        conn.commit()
        
        return jsonify({'message': 'User created successfully'}), 201
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

@auth_bp.route('/login', methods=['POST'])
def login():
    data = request.json
    username = data.get('username')
    password = data.get('password')
    
    if not username or not password:
        return jsonify({'error': 'Username and password are required'}), 400
    
    try:
        db_path = os.path.join(os.path.dirname(__file__), 'users.db')
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        
        # Get user from database
        c.execute('SELECT id, password_hash FROM users WHERE username = ?', (username,))
        user = c.fetchone()
        
        if user is None:
            return jsonify({'error': 'Invalid username or password'}), 401
        
        # Verify password
        if not check_password_hash(user[1], password):
            return jsonify({'error': 'Invalid username or password'}), 401
        
        # Set session
        session['user_id'] = user[0]
        session['username'] = username
        
        return jsonify({
            'message': 'Login successful',
            'username': username,
            'redirect_url': '/chat'
        }), 200
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

@auth_bp.route('/logout')
def logout():
    session.clear()
    return jsonify({'message': 'Logged out successfully'}), 200

@auth_bp.route('/profile/update', methods=['POST'])
def update_profile():
    if 'user_id' not in session:
        return jsonify({'error': 'Authentication required'}), 401
    
    data = request.json
    new_username = data.get('username')
    new_password = data.get('password')
    
    if not new_username and not new_password:
        return jsonify({'error': 'No changes provided'}), 400
    
    try:
        db_path = os.path.join(os.path.dirname(__file__), 'users.db')
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        
        if new_username:
            # Check if new username already exists
            c.execute('SELECT id FROM users WHERE username = ? AND id != ?', 
                      (new_username, session['user_id']))
            if c.fetchone() is not None:
                return jsonify({'error': 'Username already exists'}), 400
            
            # Update username
            c.execute('UPDATE users SET username = ? WHERE id = ?',
                      (new_username, session['user_id']))
            session['username'] = new_username
        
        if new_password:
            # Update password
            password_hash = generate_password_hash(new_password)
            c.execute('UPDATE users SET password_hash = ? WHERE id = ?',
                      (password_hash, session['user_id']))
        
        conn.commit()
        return jsonify({'message': 'Profile updated successfully'}), 200
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

@auth_bp.route('/profile/data', methods=['GET'])
def get_profile_data():
    if 'user_id' not in session:
        return jsonify({'error': 'Authentication required'}), 401
    
    try:
        db_path = os.path.join(os.path.dirname(__file__), 'users.db')
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        
        # Get user data
        c.execute('SELECT username FROM users WHERE id = ?', (session['user_id'],))
        user = c.fetchone()
        
        # Get summaries
        c.execute('SELECT symptoms, summary, created_at FROM summary_sheets WHERE user_id = ? ORDER BY created_at DESC', (session['user_id'],))
        summaries = [{
            'symptoms': row[0],
            'summary': row[1],
            'date': row[2]
        } for row in c.fetchall()]
        
        return jsonify({
            'username': user[0] if user else '',
            'summary_count': len(summaries),
            'last_consultation': summaries[0]['date'] if summaries else None,
            'summaries': summaries
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

@auth_bp.route('/update-password', methods=['POST'])
def update_password():
    if 'user_id' not in session:
        return jsonify({'error': 'Authentication required'}), 401
    
    data = request.json
    new_password = data.get('password')
    
    if not new_password:
        return jsonify({'error': 'New password is required'}), 400
    
    try:
        db_path = os.path.join(os.path.dirname(__file__), 'users.db')
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        
        # Update password with proper hashing
        password_hash = generate_password_hash(new_password)
        c.execute('UPDATE users SET password_hash = ? WHERE id = ?',
                  (password_hash, session['user_id']))
        conn.commit()
        
        return jsonify({'message': 'Password updated successfully'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

@auth_bp.route('/summary/save', methods=['POST'])
def save_summary():
    if 'user_id' not in session:
        return jsonify({'error': 'Authentication required'}), 401
    
    data = request.json
    symptoms = data.get('symptoms')
    summary = data.get('summary')
    
    if not symptoms or not summary:
        return jsonify({'error': 'Symptoms and summary are required'}), 400
    
    try:
        db_path = os.path.join(os.path.dirname(__file__), 'users.db')
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        
        c.execute('INSERT INTO summary_sheets (user_id, symptoms, summary) VALUES (?, ?, ?)',
                  (session['user_id'], symptoms, summary))
        conn.commit()
        
        return jsonify({'message': 'Summary saved successfully'}), 201
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

@auth_bp.route('/summary/history')
def get_summary_history():
    if 'user_id' not in session:
        return jsonify({'error': 'Authentication required'}), 401
    
    try:
        db_path = os.path.join(os.path.dirname(__file__), 'users.db')
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        
        c.execute('''
            SELECT symptoms, summary, created_at 
            FROM summary_sheets 
            WHERE user_id = ? 
            ORDER BY created_at DESC
        ''', (session['user_id'],))
        
        summaries = [{
            'symptoms': row[0],
            'summary': row[1],
            'created_at': row[2]
        } for row in c.fetchall()]
        
        return jsonify({'summaries': summaries}), 200
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

@auth_bp.route('/check-auth')
def check_auth():
    if 'user_id' in session:
        return jsonify({
            'authenticated': True,
            'username': session.get('username')
        })
    return jsonify({'authenticated': False}), 401