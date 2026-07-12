from flask import Flask, render_template, request, send_file, abort, jsonify, session, redirect, url_for
from flask_cors import CORS
from functools import wraps
import os
import json
import tempfile
import logging
import re
from datetime import datetime
from ftplib import FTP, error_perm
import secrets

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', secrets.token_hex(32))
CORS(app)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration
FTP_HOST = os.getenv('FTP_HOST', 'your-ftp-server.com')
FTP_PORT = int(os.getenv('FTP_PORT', 21))
FTP_USER = os.getenv('FTP_USER', 'anonymous')
FTP_PASS = os.getenv('FTP_PASS', '')
USERS_FILE = "users.json"
ADMIN_TOKEN = os.getenv('ADMIN_TOKEN', 'admin123')

# ===== MOVIE CATEGORIES =====
MOVIE_CATEGORIES = [
    # Regular categories
    {'id': 'action', 'name': 'Action', 'icon': '🎬'},
    {'id': 'comedy', 'name': 'Comedy', 'icon': '😄'},
    {'id': 'drama', 'name': 'Drama', 'icon': '🎭'},
    {'id': 'horror', 'name': 'Horror', 'icon': '👻'},
    {'id': 'sci-fi', 'name': 'Sci-Fi', 'icon': '🚀'},
    {'id': 'romance', 'name': 'Romance', 'icon': '❤️'},
    {'id': 'documentary', 'name': 'Documentary', 'icon': '📹'},
    {'id': 'anime', 'name': 'Anime', 'icon': '🎌'},
    
    # Adult category - JUST ONE
    {'id': 'adult', 'name': 'Adult 18+', 'icon': '🔞'},
]

# ===== USER MANAGEMENT =====

def load_users():
    if not os.path.exists(USERS_FILE):
        default_users = {
            "admin": {
                "password": ADMIN_TOKEN,
                "role": "admin",
                "created_at": datetime.now().isoformat()
            }
        }
        save_users(default_users)
        return default_users
    with open(USERS_FILE, 'r') as f:
        return json.load(f)

def save_users(users):
    with open(USERS_FILE, 'w') as f:
        json.dump(users, f, indent=2)

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session:
            return jsonify({'error': 'Unauthorized'}), 401
        users = load_users()
        if session['username'] not in users or users[session['username']].get('role') != 'admin':
            return jsonify({'error': 'Admin access required'}), 403
        return f(*args, **kwargs)
    return decorated_function

# ===== FTP FUNCTIONS =====

def get_ftp_connection():
    ftp = FTP()
    ftp.connect(FTP_HOST, FTP_PORT)
    ftp.login(FTP_USER, FTP_PASS)
    ftp.set_pasv(True)
    return ftp

# ===== MOCK DATA =====
MOCK_MOVIES = {
    'action': [
        {'title': 'The Dark Knight', 'year': 2008, 'size': '2.1 GB', 'format': 'MKV', 'rating': '9.0', 'poster': '🎬'},
        {'title': 'Inception', 'year': 2010, 'size': '1.8 GB', 'format': 'MP4', 'rating': '8.8', 'poster': '🧠'},
        {'title': 'Mad Max Fury Road', 'year': 2015, 'size': '2.4 GB', 'format': 'MKV', 'rating': '8.1', 'poster': '🔥'},
        {'title': 'John Wick', 'year': 2014, 'size': '1.9 GB', 'format': 'MP4', 'rating': '7.4', 'poster': '🔫'},
        {'title': 'Gladiator', 'year': 2000, 'size': '2.2 GB', 'format': 'MKV', 'rating': '8.5', 'poster': '⚔️'},
        {'title': 'Die Hard', 'year': 1988, 'size': '1.8 GB', 'format': 'MKV', 'rating': '8.2', 'poster': '💥'},
        {'title': 'The Equalizer', 'year': 2014, 'size': '2.0 GB', 'format': 'MP4', 'rating': '7.2', 'poster': '🎯'},
    ],
    'comedy': [
        {'title': 'Superbad', 'year': 2007, 'size': '1.5 GB', 'format': 'MP4', 'rating': '7.6', 'poster': '😄'},
        {'title': 'The Hangover', 'year': 2009, 'size': '1.7 GB', 'format': 'MKV', 'rating': '7.7', 'poster': '🍺'},
        {'title': 'Bridesmaids', 'year': 2011, 'size': '1.6 GB', 'format': 'MP4', 'rating': '6.8', 'poster': '💒'},
    ],
    'drama': [
        {'title': 'The Shawshank Redemption', 'year': 1994, 'size': '2.3 GB', 'format': 'MKV', 'rating': '9.3', 'poster': '🏛️'},
        {'title': 'The Godfather', 'year': 1972, 'size': '2.1 GB', 'format': 'MP4', 'rating': '9.2', 'poster': '🍷'},
        {'title': 'Forrest Gump', 'year': 1994, 'size': '2.0 GB', 'format': 'MKV', 'rating': '8.8', 'poster': '🏃'},
    ],
    'horror': [
        {'title': 'The Conjuring', 'year': 2013, 'size': '1.8 GB', 'format': 'MKV', 'rating': '7.5', 'poster': '👻'},
        {'title': 'Hereditary', 'year': 2018, 'size': '2.0 GB', 'format': 'MP4', 'rating': '7.3', 'poster': '😱'},
        {'title': 'Get Out', 'year': 2017, 'size': '1.7 GB', 'format': 'MKV', 'rating': '7.8', 'poster': '🧠'},
    ],
    'sci-fi': [
        {'title': 'Interstellar', 'year': 2014, 'size': '2.6 GB', 'format': 'MKV', 'rating': '8.6', 'poster': '🌌'},
        {'title': 'The Matrix', 'year': 1999, 'size': '1.9 GB', 'format': 'MP4', 'rating': '8.7', 'poster': '💊'},
        {'title': 'Dune', 'year': 2021, 'size': '3.2 GB', 'format': 'MKV', 'rating': '8.0', 'poster': '🏜️'},
    ],
    'romance': [
        {'title': 'The Notebook', 'year': 2004, 'size': '1.6 GB', 'format': 'MP4', 'rating': '7.8', 'poster': '📖'},
        {'title': 'Titanic', 'year': 1997, 'size': '2.4 GB', 'format': 'MKV', 'rating': '7.9', 'poster': '🚢'},
    ],
    'documentary': [
        {'title': 'Planet Earth II', 'year': 2016, 'size': '4.5 GB', 'format': 'MKV', 'rating': '9.5', 'poster': '🌍'},
        {'title': 'Our Planet', 'year': 2019, 'size': '3.8 GB', 'format': 'MP4', 'rating': '9.3', 'poster': '🌿'},
    ],
    'anime': [
        {'title': 'Spirited Away', 'year': 2001, 'size': '1.7 GB', 'format': 'MKV', 'rating': '8.6', 'poster': '🏮'},
        {'title': 'Your Name', 'year': 2016, 'size': '1.5 GB', 'format': 'MP4', 'rating': '8.4', 'poster': '✨'},
        {'title': 'Demon Slayer', 'year': 2020, 'size': '2.0 GB', 'format': 'MKV', 'rating': '8.6', 'poster': '⚔️'},
    ],
    'adult': [
        {'title': 'Adult Collection Vol 1', 'year': 2024, 'size': '3.2 GB', 'format': 'MKV', 'rating': '🔞', 'poster': '🔞'},
        {'title': 'Adult Collection Vol 2', 'year': 2024, 'size': '3.5 GB', 'format': 'MP4', 'rating': '🔞', 'poster': '🔞'},
        {'title': 'Adult Film 1', 'year': 2023, 'size': '2.8 GB', 'format': 'MKV', 'rating': '🔞', 'poster': '🔞'},
    ],
}

def get_movie_listing(category):
    """Get movie listing - tries FTP first, falls back to mock data"""
    try:
        movies = []
        ftp = get_ftp_connection()
        remote_path = f'/movies/{category}'
        try:
            ftp.cwd(remote_path)
        except:
            ftp.quit()
            return MOCK_MOVIES.get(category, [])
        
        files = []
        try:
            files = list(ftp.mlsd())
        except:
            def parse_line(line):
                parts = line.split()
                if len(parts) >= 9:
                    filename = ' '.join(parts[8:])
                    size = parts[4]
                    is_dir = line.startswith('d')
                    return {'filename': filename, 'size': size, 'type': 'directory' if is_dir else 'file'}
            ftp.dir(lambda line: files.append(parse_line(line)))
        
        ftp.quit()
        video_ext = {'.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.webm', '.m4v'}
        for file in files:
            if isinstance(file, dict) and file.get('type') == 'file':
                filename = file['filename']
                ext = os.path.splitext(filename)[1].lower()
                if ext in video_ext:
                    year = ''
                    year_match = re.search(r'\((\d{4})\)', filename) or re.search(r'\.(\d{4})\.', filename)
                    if year_match:
                        year = year_match.group(1)
                    display_name = re.sub(r'[._]', ' ', filename)
                    display_name = re.sub(r'\s+', ' ', display_name).strip()
                    display_name = re.sub(r'\s*\(\d{4}\)\s*', '', display_name)
                    display_name = os.path.splitext(display_name)[0]
                    size_bytes = int(file.get('size', 0))
                    if size_bytes < 1024*1024:
                        size_str = f"{size_bytes/1024:.1f} KB"
                    elif size_bytes < 1024*1024*1024:
                        size_str = f"{size_bytes/(1024*1024):.1f} MB"
                    else:
                        size_str = f"{size_bytes/(1024*1024*1024):.2f} GB"
                    movies.append({
                        'title': display_name,
                        'filename': filename,
                        'year': year,
                        'size': size_str,
                        'format': ext.upper().replace('.', ''),
                        'rating': '⭐',
                        'poster': '🎬'
                    })
        movies.sort(key=lambda x: x['title'])
        return movies if movies else MOCK_MOVIES.get(category, [])
    except Exception as e:
        logger.error(f"Error getting movies for {category}: {e}")
        return MOCK_MOVIES.get(category, [])

def upload_file_to_ftp(local_path, remote_path):
    try:
        ftp = get_ftp_connection()
        remote_dir = os.path.dirname(remote_path)
        try:
            ftp.cwd(remote_dir)
        except:
            ftp.mkd(remote_dir)
            ftp.cwd(remote_dir)
        with open(local_path, 'rb') as f:
            ftp.storbinary(f'STOR {remote_path}', f)
        ftp.quit()
        return True
    except Exception as e:
        logger.error(f"Upload error: {e}")
        return False

# ===== ROUTES =====

@app.route('/')
def index():
    # Get featured movies (first 5 from action)
    featured = MOCK_MOVIES.get('action', [])[:5]
    return render_template('index.html', 
                         categories=MOVIE_CATEGORIES,
                         featured=featured,
                         logged_in='username' in session)

@app.route('/category/<category_id>')
def category_movies(category_id):
    category = next((c for c in MOVIE_CATEGORIES if c['id'] == category_id), None)
    if not category:
        abort(404)
    movies = get_movie_listing(category_id)
    return render_template('category.html', 
                         category=category,
                         movies=movies,
                         categories=MOVIE_CATEGORIES,
                         logged_in='username' in session)

@app.route('/stream/<category>/<filename>')
def stream_movie(category, filename):
    try:
        ftp = get_ftp_connection()
        remote_path = f'/movies/{category}/{filename}'
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(filename)[1])
        temp_path = temp_file.name
        temp_file.close()
        with open(temp_path, 'wb') as f:
            ftp.retrbinary(f'RETR {remote_path}', f.write)
        ftp.quit()
        return send_file(temp_path, mimetype='video/mp4', conditional=True)
    except Exception as e:
        logger.error(f"Stream error: {e}")
        return jsonify({'error': 'File not found'}), 404

@app.route('/download/<category>/<filename>')
def download_movie(category, filename):
    try:
        ftp = get_ftp_connection()
        remote_path = f'/movies/{category}/{filename}'
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(filename)[1])
        temp_path = temp_file.name
        temp_file.close()
        with open(temp_path, 'wb') as f:
            ftp.retrbinary(f'RETR {remote_path}', f.write)
        ftp.quit()
        return send_file(temp_path, as_attachment=True, download_name=filename)
    except Exception as e:
        logger.error(f"Download error: {e}")
        return jsonify({'error': 'File not found'}), 404

@app.route('/search')
def search_movies():
    query = request.args.get('q', '').strip().lower()
    results = []
    if query:
        for category in MOVIE_CATEGORIES:
            movies = get_movie_listing(category['id'])
            for movie in movies:
                if query in movie['title'].lower():
                    results.append({**movie, 'category': category['id'], 'category_name': category['name']})
    return render_template('search.html', 
                         query=query, 
                         results=results,
                         categories=MOVIE_CATEGORIES,
                         logged_in='username' in session)

# ===== AUTH ROUTES (Hidden - Only for Upload) =====

@app.route('/api/login', methods=['POST'])
def api_login():
    """Hidden login API - only for upload modal"""
    data = request.json
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()
    users = load_users()
    
    if username not in users or users[username].get('password') != password:
        return jsonify({'error': 'Invalid credentials'}), 401
    
    session['username'] = username
    session['role'] = users[username].get('role', 'user')
    return jsonify({'success': True, 'username': username, 'role': session['role']})

@app.route('/api/logout', methods=['POST'])
def api_logout():
    session.clear()
    return jsonify({'success': True})

@app.route('/api/check-auth', methods=['GET'])
def check_auth():
    if 'username' in session:
        return jsonify({'logged_in': True, 'username': session['username'], 'role': session.get('role', 'user')})
    return jsonify({'logged_in': False})

# ===== ADMIN UPLOAD ROUTE =====

@app.route('/api/upload', methods=['POST'])
def api_upload():
    """Upload movie - requires admin login"""
    if 'username' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    users = load_users()
    if session['username'] not in users or users[session['username']].get('role') != 'admin':
        return jsonify({'error': 'Admin access required'}), 403
    
    if 'movie_file' not in request.files:
        return jsonify({'error': 'No file selected'}), 400
    
    file = request.files['movie_file']
    category = request.form.get('category', '')
    
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    if not category:
        return jsonify({'error': 'Please select a category'}), 400
    
    temp_path = os.path.join(tempfile.gettempdir(), file.filename)
    file.save(temp_path)
    remote_path = f'/movies/{category}/{file.filename}'
    success = upload_file_to_ftp(temp_path, remote_path)
    os.remove(temp_path)
    
    if success:
        return jsonify({'success': True, 'message': f'Movie "{file.filename}" uploaded successfully!'})
    return jsonify({'error': 'Upload failed. Check FTP server connection.'}), 500

@app.route('/health')
def health():
    return jsonify({'status': 'healthy', 'timestamp': datetime.now().isoformat()})

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(debug=False, host='0.0.0.0', port=port)
