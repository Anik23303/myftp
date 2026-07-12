from flask import Flask, render_template, request, send_file, abort, jsonify, session, redirect, url_for, flash
from flask_cors import CORS
from functools import wraps
import os
import json
import tempfile
import logging
import re
from datetime import datetime, timedelta
from ftplib import FTP, error_perm
import secrets

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', secrets.token_hex(32))
CORS(app)

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration from environment
FTP_HOST = os.getenv('FTP_HOST', 'your-ftp-server.com')
FTP_PORT = int(os.getenv('FTP_PORT', 21))
FTP_USER = os.getenv('FTP_USER', 'anonymous')
FTP_PASS = os.getenv('FTP_PASS', '')
USERS_FILE = "users.json"
ADMIN_TOKEN = os.getenv('ADMIN_TOKEN', 'admin123')  # CHANGE THIS!

# Movie Categories
MOVIE_CATEGORIES = [
    {'id': 'action', 'name': '🔥 Action', 'icon': '🎬'},
    {'id': 'comedy', 'name': '😂 Comedy', 'icon': '😄'},
    {'id': 'drama', 'name': '🎭 Drama', 'icon': '🎪'},
    {'id': 'horror', 'name': '👻 Horror', 'icon': '🧛'},
    {'id': 'sci-fi', 'name': '🚀 Sci-Fi', 'icon': '👾'},
    {'id': 'romance', 'name': '💕 Romance', 'icon': '🌹'},
    {'id': 'documentary', 'name': '📹 Documentary', 'icon': '🎥'},
    {'id': 'anime', 'name': '🗾 Anime', 'icon': '🎌'},
]

# ===== USER MANAGEMENT =====

def load_users():
    """Load users from JSON file"""
    if not os.path.exists(USERS_FILE):
        # Create default admin if no users file exists
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
    """Save users to JSON file"""
    with open(USERS_FILE, 'w') as f:
        json.dump(users, f, indent=2)

def login_required(f):
    """Decorator to require login"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session:
            flash('Please login first', 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    """Decorator to require admin role"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session:
            flash('Please login first', 'error')
            return redirect(url_for('login'))
        users = load_users()
        if session['username'] not in users or users[session['username']].get('role') != 'admin':
            flash('Admin access required', 'error')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

# ===== FTP FUNCTIONS =====

def get_ftp_connection():
    """Get FTP connection"""
    ftp = FTP()
    ftp.connect(FTP_HOST, FTP_PORT)
    ftp.login(FTP_USER, FTP_PASS)
    ftp.set_pasv(True)
    return ftp

def get_movie_listing(category):
    """Get list of movies from FTP folder"""
    movies = []
    try:
        ftp = get_ftp_connection()
        remote_path = f'/movies/{category}'
        
        try:
            ftp.cwd(remote_path)
        except:
            ftp.quit()
            return []
        
        # Get file list
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
        
        # Filter video files
        video_ext = {'.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.webm', '.m4v'}
        for file in files:
            if isinstance(file, dict) and file.get('type') == 'file':
                filename = file['filename']
                ext = os.path.splitext(filename)[1].lower()
                if ext in video_ext:
                    # Extract year
                    year = ''
                    year_match = re.search(r'\((\d{4})\)', filename) or re.search(r'\.(\d{4})\.', filename)
                    if year_match:
                        year = year_match.group(1)
                    
                    # Clean display name
                    display_name = re.sub(r'[._]', ' ', filename)
                    display_name = re.sub(r'\s+', ' ', display_name).strip()
                    display_name = re.sub(r'\s*\(\d{4}\)\s*', '', display_name)
                    display_name = os.path.splitext(display_name)[0]
                    
                    # Format size
                    size_bytes = int(file.get('size', 0))
                    if size_bytes < 1024:
                        size_str = f"{size_bytes} B"
                    elif size_bytes < 1024*1024:
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
                        'size_bytes': size_bytes,
                        'format': ext.upper().replace('.', '')
                    })
        
        movies.sort(key=lambda x: x['title'])
        
    except Exception as e:
        logger.error(f"Error getting movies for {category}: {e}")
    
    return movies

def upload_file_to_ftp(local_path, remote_path):
    """Upload a file to FTP server"""
    try:
        ftp = get_ftp_connection()
        
        # Ensure directory exists
        remote_dir = os.path.dirname(remote_path)
        try:
            ftp.cwd(remote_dir)
        except:
            # Create directory if it doesn't exist
            ftp.mkd(remote_dir)
            ftp.cwd(remote_dir)
        
        # Upload file
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
    """Homepage with movie categories"""
    return render_template('index.html', 
                         categories=MOVIE_CATEGORIES,
                         logged_in='username' in session)

@app.route('/category/<category_id>')
def category_movies(category_id):
    """List movies in a category"""
    category = next((c for c in MOVIE_CATEGORIES if c['id'] == category_id), None)
    if not category:
        abort(404)
    
    movies = get_movie_listing(category_id)
    
    return render_template('movies.html', 
                         category=category_id,
                         category_name=category['name'],
                         category_icon=category['icon'],
                         movies=movies,
                         categories=MOVIE_CATEGORIES,
                         logged_in='username' in session)

@app.route('/stream/<category>/<filename>')
def stream_movie(category, filename):
    """Stream movie"""
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
    """Download movie"""
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
    """Search movies"""
    query = request.args.get('q', '').strip().lower()
    results = []
    
    if query:
        for category in MOVIE_CATEGORIES:
            movies = get_movie_listing(category['id'])
            for movie in movies:
                if query in movie['title'].lower():
                    results.append({
                        **movie,
                        'category': category['id'],
                        'category_name': category['name']
                    })
    
    return render_template('search_results.html', 
                         query=query, 
                         results=results,
                         categories=MOVIE_CATEGORIES,
                         logged_in='username' in session)

# ===== AUTH ROUTES =====

@app.route('/register', methods=['GET', 'POST'])
def register():
    """User registration - only for uploading movies"""
    if request.method == 'GET':
        return render_template('register.html', logged_in='username' in session)
    
    # POST - Register new user
    data = request.form
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()
    
    # Validation
    if not username or not password:
        flash('Username and password required', 'error')
        return redirect(url_for('register'))
    
    if len(username) < 3 or len(password) < 6:
        flash('Username must be 3+ chars, password 6+ chars', 'error')
        return redirect(url_for('register'))
    
    if not username.isalnum():
        flash('Username must be alphanumeric', 'error')
        return redirect(url_for('register'))
    
    users = load_users()
    if username in users:
        flash('Username already exists', 'error')
        return redirect(url_for('register'))
    
    # Save user
    users[username] = {
        "password": password,
        "role": "user",
        "created_at": datetime.now().isoformat()
    }
    save_users(users)
    
    flash('Registration successful! Please login.', 'success')
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    """User login"""
    if request.method == 'GET':
        return render_template('login.html', logged_in='username' in session)
    
    # POST - Login
    data = request.form
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()
    
    users = load_users()
    
    if username not in users or users[username].get('password') != password:
        flash('Invalid username or password', 'error')
        return redirect(url_for('login'))
    
    session['username'] = username
    session['role'] = users[username].get('role', 'user')
    
    flash(f'Welcome back, {username}!', 'success')
    
    # Redirect admin to admin panel, users to home
    if session['role'] == 'admin':
        return redirect(url_for('admin_panel'))
    return redirect(url_for('index'))

@app.route('/logout')
def logout():
    """User logout"""
    session.clear()
    flash('Logged out successfully', 'success')
    return redirect(url_for('index'))

# ===== ADMIN ROUTES =====

@app.route('/admin')
@admin_required
def admin_panel():
    """Admin panel for uploading movies"""
    users = load_users()
    return render_template('admin.html', 
                         users=users,
                         categories=MOVIE_CATEGORIES,
                         logged_in=True,
                         username=session['username'])

@app.route('/admin/upload', methods=['POST'])
@admin_required
def admin_upload():
    """Upload movie via admin panel"""
    if 'movie_file' not in request.files:
        flash('No file selected', 'error')
        return redirect(url_for('admin_panel'))
    
    file = request.files['movie_file']
    category = request.form.get('category', '')
    title = request.form.get('title', '')
    
    if file.filename == '':
        flash('No file selected', 'error')
        return redirect(url_for('admin_panel'))
    
    if not category:
        flash('Please select a category', 'error')
        return redirect(url_for('admin_panel'))
    
    # Save file temporarily
    temp_path = os.path.join(tempfile.gettempdir(), file.filename)
    file.save(temp_path)
    
    # Upload to FTP
    remote_path = f'/movies/{category}/{file.filename}'
    success = upload_file_to_ftp(temp_path, remote_path)
    
    # Clean up temp file
    os.remove(temp_path)
    
    if success:
        flash(f'Movie "{file.filename}" uploaded successfully!', 'success')
    else:
        flash('Upload failed. Check FTP server connection.', 'error')
    
    return redirect(url_for('admin_panel'))

@app.route('/admin/users')
@admin_required
def admin_users():
    """List all users"""
    users = load_users()
    return render_template('admin_users.html', 
                         users=users,
                         logged_in=True,
                         username=session['username'])

@app.route('/admin/delete-user/<username>')
@admin_required
def admin_delete_user(username):
    """Delete a user"""
    if username == 'admin':
        flash('Cannot delete admin user', 'error')
        return redirect(url_for('admin_users'))
    
    users = load_users()
    if username in users:
        del users[username]
        save_users(users)
        flash(f'User {username} deleted', 'success')
    else:
        flash('User not found', 'error')
    
    return redirect(url_for('admin_users'))

@app.route('/admin/change-password', methods=['POST'])
@admin_required
def admin_change_password():
    """Change user password"""
    data = request.form
    username = data.get('username', '')
    new_password = data.get('new_password', '')
    
    if not username or not new_password or len(new_password) < 6:
        flash('Invalid password (must be 6+ chars)', 'error')
        return redirect(url_for('admin_users'))
    
    users = load_users()
    if username not in users:
        flash('User not found', 'error')
        return redirect(url_for('admin_users'))
    
    users[username]['password'] = new_password
    save_users(users)
    flash(f'Password changed for {username}', 'success')
    return redirect(url_for('admin_users'))

@app.route('/health')
def health():
    """Health check"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'users': len(load_users())
    })

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(debug=False, host='0.0.0.0', port=port)
