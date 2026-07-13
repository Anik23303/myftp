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
import hashlib
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', secrets.token_hex(32))
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500MB max
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
VIDEOS_FILE = "videos.json"
WATCH_HISTORY_FILE = "watch_history.json"
MYLIST_FILE = "mylist.json"
ADMIN_TOKEN = os.getenv('ADMIN_TOKEN', 'admin123')
UPLOAD_FOLDER = "static/uploads"
THUMBNAIL_FOLDER = "static/thumbnails"

# Create folders if not exists
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(THUMBNAIL_FOLDER, exist_ok=True)

# ===== MOVIE CATEGORIES =====
MOVIE_CATEGORIES = [
    {'id': 'action', 'name': 'Action', 'icon': '🎬'},
    {'id': 'comedy', 'name': 'Comedy', 'icon': '😄'},
    {'id': 'drama', 'name': 'Drama', 'icon': '🎭'},
    {'id': 'horror', 'name': 'Horror', 'icon': '👻'},
    {'id': 'sci-fi', 'name': 'Sci-Fi', 'icon': '🚀'},
    {'id': 'romance', 'name': 'Romance', 'icon': '❤️'},
    {'id': 'documentary', 'name': 'Documentary', 'icon': '📹'},
    {'id': 'anime', 'name': 'Anime', 'icon': '🎌'},
    {'id': 'adult', 'name': 'Adult 18+', 'icon': '🔞'},
]

# ===== DATA MANAGEMENT =====

def load_users():
    """Load users from JSON file"""
    if not os.path.exists(USERS_FILE):
        default_users = {
            "admin": {
                "password": ADMIN_TOKEN,
                "role": "admin",
                "created_at": datetime.now().isoformat(),
                "profile_pic": "",
                "total_views": 0,
                "total_uploads": 0
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

def load_videos():
    """Load videos from JSON file"""
    if not os.path.exists(VIDEOS_FILE):
        return {}
    with open(VIDEOS_FILE, 'r') as f:
        return json.load(f)

def save_videos(videos):
    """Save videos to JSON file"""
    with open(VIDEOS_FILE, 'w') as f:
        json.dump(videos, f, indent=2)

def load_watch_history():
    """Load watch history"""
    if not os.path.exists(WATCH_HISTORY_FILE):
        return {}
    with open(WATCH_HISTORY_FILE, 'r') as f:
        return json.load(f)

def save_watch_history(history):
    """Save watch history"""
    with open(WATCH_HISTORY_FILE, 'w') as f:
        json.dump(history, f, indent=2)

def load_mylist():
    """Load My List (watch later)"""
    if not os.path.exists(MYLIST_FILE):
        return {}
    with open(MYLIST_FILE, 'r') as f:
        return json.load(f)

def save_mylist(mylist):
    """Save My List"""
    with open(MYLIST_FILE, 'w') as f:
        json.dump(mylist, f, indent=2)

def get_user_videos(username):
    """Get all videos uploaded by a user"""
    videos = load_videos()
    return {vid_id: vid for vid_id, vid in videos.items() if vid.get('uploaded_by') == username}

def get_user_total_views(username):
    """Get total views for a user's videos"""
    videos = load_videos()
    total = 0
    for vid in videos.values():
        if vid.get('uploaded_by') == username:
            total += vid.get('views', 0)
    return total

def update_user_total_views(username):
    """Update user's total views and uploads in users.json"""
    users = load_users()
    if username in users:
        videos = get_user_videos(username)
        users[username]['total_views'] = sum(v.get('views', 0) for v in videos.values())
        users[username]['total_uploads'] = len(videos)
        save_users(users)

def get_leaderboard(time_filter='all'):
    """Get top 10 users by total views with time filter"""
    users = load_users()
    videos = load_videos()
    
    user_list = []
    for username, data in users.items():
        if data.get('role') != 'admin' and username != 'admin':
            total_views = 0
            for vid in videos.values():
                if vid.get('uploaded_by') == username:
                    uploaded_at = datetime.fromisoformat(vid.get('uploaded_at', ''))
                    now = datetime.now()
                    
                    if time_filter == 'week':
                        if uploaded_at >= now - timedelta(days=7):
                            total_views += vid.get('views', 0)
                    elif time_filter == 'month':
                        if uploaded_at >= now - timedelta(days=30):
                            total_views += vid.get('views', 0)
                    else:  # 'all'
                        total_views += vid.get('views', 0)
            
            user_list.append({
                'username': username,
                'total_views': total_views,
                'profile_pic': data.get('profile_pic', ''),
                'total_uploads': data.get('total_uploads', 0)
            })
    
    user_list.sort(key=lambda x: x['total_views'], reverse=True)
    return user_list[:10]

def get_video_stats():
    """Get video statistics for admin dashboard"""
    videos = load_videos()
    users = load_users()
    
    total_videos = len(videos)
    total_views = sum(v.get('views', 0) for v in videos.values())
    total_users = len([u for u in users.values() if u.get('role') != 'admin'])
    
    category_views = {}
    for vid in videos.values():
        cat = vid.get('category', 'unknown')
        category_views[cat] = category_views.get(cat, 0) + vid.get('views', 0)
    
    most_viewed = sorted(videos.values(), key=lambda x: x.get('views', 0), reverse=True)[:10]
    
    growth = []
    for i in range(7, -1, -1):
        date = (datetime.now() - timedelta(days=i)).date().isoformat()
        count = sum(1 for u in users.values() 
                   if u.get('created_at', '').startswith(date) and u.get('role') != 'admin')
        growth.append({'date': date, 'count': count})
    
    return {
        'total_videos': total_videos,
        'total_views': total_views,
        'total_users': total_users,
        'category_views': category_views,
        'most_viewed': most_viewed,
        'growth': growth
    }

def generate_video_id():
    """Generate unique video ID"""
    return secrets.token_hex(8)

def increment_views(video_id):
    """Increment view count for a video"""
    videos = load_videos()
    if video_id in videos:
        videos[video_id]['views'] = videos[video_id].get('views', 0) + 1
        save_videos(videos)
        uploaded_by = videos[video_id].get('uploaded_by')
        if uploaded_by:
            update_user_total_views(uploaded_by)
        return True
    return False

def generate_thumbnail(filename):
    """Generate placeholder thumbnail"""
    import hashlib
    hash_val = int(hashlib.md5(filename.encode()).hexdigest()[:8], 16)
    colors = ['#e50914', '#ff6b35', '#00b4d8', '#7b2cbf', '#ffd700', '#06d6a0']
    return colors[hash_val % len(colors)]

def add_to_watch_history(username, video_id):
    """Add video to user's watch history"""
    history = load_watch_history()
    if username not in history:
        history[username] = []
    
    history[username] = [v for v in history[username] if v['video_id'] != video_id]
    
    history[username].insert(0, {
        'video_id': video_id,
        'watched_at': datetime.now().isoformat()
    })
    
    history[username] = history[username][:100]
    save_watch_history(history)

def add_to_mylist(username, video_id):
    """Add video to user's My List"""
    mylist = load_mylist()
    if username not in mylist:
        mylist[username] = []
    
    if video_id not in mylist[username]:
        mylist[username].append(video_id)
        save_mylist(mylist)
        return True
    return False

def remove_from_mylist(username, video_id):
    """Remove video from user's My List"""
    mylist = load_mylist()
    if username in mylist and video_id in mylist[username]:
        mylist[username] = [v for v in mylist[username] if v != video_id]
        save_mylist(mylist)
        return True
    return False

def is_in_mylist(username, video_id):
    """Check if video is in user's My List"""
    mylist = load_mylist()
    return username in mylist and video_id in mylist[username]

def get_user_mylist(username):
    """Get user's My List with video details"""
    mylist = load_mylist()
    videos = load_videos()
    result = []
    if username in mylist:
        for video_id in mylist[username]:
            if video_id in videos:
                result.append({**videos[video_id], 'id': video_id})
    return result

def get_user_watch_history(username):
    """Get user's watch history with video details"""
    history = load_watch_history()
    videos = load_videos()
    result = []
    if username in history:
        for entry in history[username]:
            video_id = entry['video_id']
            if video_id in videos:
                result.append({
                    **videos[video_id],
                    'id': video_id,
                    'watched_at': entry['watched_at']
                })
    return result

def get_trending_videos():
    """Get trending videos (most viewed in last 7 days)"""
    videos = load_videos()
    now = datetime.now()
    trending = []
    
    for vid_id, vid in videos.items():
        uploaded_at = datetime.fromisoformat(vid.get('uploaded_at', '2000-01-01'))
        if (now - uploaded_at).days <= 7:
            trending.append({
                **vid,
                'id': vid_id,
                'trending_score': vid.get('views', 0) / max(1, (now - uploaded_at).days + 1)
            })
    
    trending.sort(key=lambda x: x['trending_score'], reverse=True)
    return trending[:10]

# ===== ADMIN DECORATOR =====

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session:
            flash('Please login as admin', 'error')
            return redirect(url_for('admin_panel'))
        users = load_users()
        if session['username'] not in users or users[session['username']].get('role') != 'admin':
            flash('Admin access required', 'error')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session:
            flash('Please login first', 'error')
            return redirect(url_for('login_page'))
        return f(*args, **kwargs)
    return decorated_function

# ===== FTP FUNCTIONS =====

def get_ftp_connection():
    ftp = FTP()
    ftp.connect(FTP_HOST, FTP_PORT)
    ftp.login(FTP_USER, FTP_PASS)
    ftp.set_pasv(True)
    return ftp

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

# ===== MOCK DATA =====
MOCK_MOVIES = {
    'action': [
        {'title': 'The Dark Knight', 'year': 2008, 'size': '2.1 GB', 'format': 'MKV', 'rating': 9.0, 'poster': '🎬'},
        {'title': 'Inception', 'year': 2010, 'size': '1.8 GB', 'format': 'MP4', 'rating': 8.8, 'poster': '🧠'},
        {'title': 'Mad Max Fury Road', 'year': 2015, 'size': '2.4 GB', 'format': 'MKV', 'rating': 8.1, 'poster': '🔥'},
        {'title': 'John Wick', 'year': 2014, 'size': '1.9 GB', 'format': 'MP4', 'rating': 7.4, 'poster': '🔫'},
        {'title': 'Gladiator', 'year': 2000, 'size': '2.2 GB', 'format': 'MKV', 'rating': 8.5, 'poster': '⚔️'},
    ],
    'comedy': [
        {'title': 'Superbad', 'year': 2007, 'size': '1.5 GB', 'format': 'MP4', 'rating': 7.6, 'poster': '😄'},
        {'title': 'The Hangover', 'year': 2009, 'size': '1.7 GB', 'format': 'MKV', 'rating': 7.7, 'poster': '🍺'},
        {'title': 'Bridesmaids', 'year': 2011, 'size': '1.6 GB', 'format': 'MP4', 'rating': 6.8, 'poster': '💒'},
    ],
    'drama': [
        {'title': 'The Shawshank Redemption', 'year': 1994, 'size': '2.3 GB', 'format': 'MKV', 'rating': 9.3, 'poster': '🏛️'},
        {'title': 'The Godfather', 'year': 1972, 'size': '2.1 GB', 'format': 'MP4', 'rating': 9.2, 'poster': '🍷'},
        {'title': 'Forrest Gump', 'year': 1994, 'size': '2.0 GB', 'format': 'MKV', 'rating': 8.8, 'poster': '🏃'},
    ],
    'horror': [
        {'title': 'The Conjuring', 'year': 2013, 'size': '1.8 GB', 'format': 'MKV', 'rating': 7.5, 'poster': '👻'},
        {'title': 'Hereditary', 'year': 2018, 'size': '2.0 GB', 'format': 'MP4', 'rating': 7.3, 'poster': '😱'},
        {'title': 'Get Out', 'year': 2017, 'size': '1.7 GB', 'format': 'MKV', 'rating': 7.8, 'poster': '🧠'},
    ],
    'sci-fi': [
        {'title': 'Interstellar', 'year': 2014, 'size': '2.6 GB', 'format': 'MKV', 'rating': 8.6, 'poster': '🌌'},
        {'title': 'The Matrix', 'year': 1999, 'size': '1.9 GB', 'format': 'MP4', 'rating': 8.7, 'poster': '💊'},
        {'title': 'Dune', 'year': 2021, 'size': '3.2 GB', 'format': 'MKV', 'rating': 8.0, 'poster': '🏜️'},
    ],
    'romance': [
        {'title': 'The Notebook', 'year': 2004, 'size': '1.6 GB', 'format': 'MP4', 'rating': 7.8, 'poster': '📖'},
        {'title': 'Titanic', 'year': 1997, 'size': '2.4 GB', 'format': 'MKV', 'rating': 7.9, 'poster': '🚢'},
    ],
    'documentary': [
        {'title': 'Planet Earth II', 'year': 2016, 'size': '4.5 GB', 'format': 'MKV', 'rating': 9.5, 'poster': '🌍'},
        {'title': 'Our Planet', 'year': 2019, 'size': '3.8 GB', 'format': 'MP4', 'rating': 9.3, 'poster': '🌿'},
    ],
    'anime': [
        {'title': 'Spirited Away', 'year': 2001, 'size': '1.7 GB', 'format': 'MKV', 'rating': 8.6, 'poster': '🏮'},
        {'title': 'Your Name', 'year': 2016, 'size': '1.5 GB', 'format': 'MP4', 'rating': 8.4, 'poster': '✨'},
        {'title': 'Demon Slayer', 'year': 2020, 'size': '2.0 GB', 'format': 'MKV', 'rating': 8.6, 'poster': '⚔️'},
    ],
    'adult': [
        {'title': 'Adult Collection Vol 1', 'year': 2024, 'size': '3.2 GB', 'format': 'MKV', 'rating': 0, 'poster': '🔞'},
        {'title': 'Adult Collection Vol 2', 'year': 2024, 'size': '3.5 GB', 'format': 'MP4', 'rating': 0, 'poster': '🔞'},
        {'title': 'Adult Film 1', 'year': 2023, 'size': '2.8 GB', 'format': 'MKV', 'rating': 0, 'poster': '🔞'},
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
                        'poster': '🎬',
                        'thumbnail_color': generate_thumbnail(filename)
                    })
        movies.sort(key=lambda x: x['title'])
        return movies if movies else MOCK_MOVIES.get(category, [])
    except Exception as e:
        logger.error(f"Error getting movies for {category}: {e}")
        return MOCK_MOVIES.get(category, [])

# Make get_movie_listing available in templates
app.jinja_env.globals.update(get_movie_listing=get_movie_listing)

# ===== ROUTES =====

@app.route('/')
def index():
    featured = MOCK_MOVIES.get('action', [])[:5]
    users = load_users()
    leaderboard = get_leaderboard()
    trending = get_trending_videos()
    return render_template('index.html', 
                         categories=MOVIE_CATEGORIES,
                         featured=featured,
                         trending=trending,
                         logged_in='username' in session,
                         username=session.get('username', ''),
                         leaderboard=leaderboard,
                         theme=session.get('theme', 'dark'))

@app.route('/category/<category_id>')
def category_movies(category_id):
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
                         logged_in='username' in session,
                         username=session.get('username', ''),
                         theme=session.get('theme', 'dark'))

@app.route('/stream/<category>/<filename>')
def stream_movie(category, filename):
    try:
        videos = load_videos()
        video_id = None
        for vid_id, vid in videos.items():
            if vid.get('filename') == filename and vid.get('category') == category:
                video_id = vid_id
                break
        
        if video_id:
            increment_views(video_id)
            if 'username' in session:
                add_to_watch_history(session['username'], video_id)
        
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
        videos = load_videos()
        video_id = None
        for vid_id, vid in videos.items():
            if vid.get('filename') == filename and vid.get('category') == category:
                video_id = vid_id
                break
        
        if video_id:
            increment_views(video_id)
            if 'username' in session:
                add_to_watch_history(session['username'], video_id)
        
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
    return render_template('search_results.html', 
                         query=query, 
                         results=results,
                         categories=MOVIE_CATEGORIES,
                         logged_in='username' in session,
                         username=session.get('username', ''),
                         theme=session.get('theme', 'dark'))

# ===== AUTH ROUTES =====

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'GET':
        return render_template('register.html', logged_in='username' in session, theme=session.get('theme', 'dark'))
    
    data = request.form
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()
    profile_pic = request.files.get('profile_pic')
    
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
    
    profile_pic_path = ""
    if profile_pic and profile_pic.filename:
        os.makedirs(UPLOAD_FOLDER, exist_ok=True)
        ext = os.path.splitext(profile_pic.filename)[1]
        filename = f"{username}_{secrets.token_hex(4)}{ext}"
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        profile_pic.save(filepath)
        profile_pic_path = f"/{UPLOAD_FOLDER}/{filename}"
    
    users[username] = {
        "password": password,
        "role": "user",
        "created_at": datetime.now().isoformat(),
        "profile_pic": profile_pic_path,
        "total_views": 0,
        "total_uploads": 0
    }
    save_users(users)
    
    flash('Registration successful! Please login.', 'success')
    return redirect(url_for('login_page'))

@app.route('/login', methods=['GET', 'POST'])
def login_page():
    if request.method == 'GET':
        return render_template('login.html', logged_in='username' in session, theme=session.get('theme', 'dark'))
    
    data = request.form
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()
    users = load_users()
    
    if username not in users or users[username].get('password') != password:
        flash('Invalid username or password', 'error')
        return redirect(url_for('login_page'))
    
    session['username'] = username
    session['role'] = users[username].get('role', 'user')
    flash(f'Welcome back, {username}!', 'success')
    
    if session['role'] == 'admin':
        return redirect(url_for('admin_panel'))
    return redirect(url_for('index'))

@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out successfully', 'success')
    return redirect(url_for('index'))

@app.route('/toggle-theme')
def toggle_theme():
    current = session.get('theme', 'dark')
    session['theme'] = 'light' if current == 'dark' else 'dark'
    return redirect(request.referrer or '/')

# ===== API ROUTES =====

@app.route('/api/login', methods=['POST'])
def api_login():
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

@app.route('/api/leaderboard', methods=['GET'])
def api_leaderboard():
    time_filter = request.args.get('filter', 'all')
    leaderboard = get_leaderboard(time_filter)
    return jsonify({'leaderboard': leaderboard})

@app.route('/api/user-stats', methods=['GET'])
@login_required
def api_user_stats():
    username = session.get('username')
    videos = get_user_videos(username)
    total_videos = len(videos)
    total_views = sum(v.get('views', 0) for v in videos.values())
    total_rating = sum(v.get('rating', 0) for v in videos.values())
    avg_rating = total_rating / total_videos if total_videos > 0 else 0
    
    video_list = []
    for vid_id, vid in videos.items():
        video_list.append({
            'id': vid_id,
            'title': vid.get('title', 'Untitled'),
            'filename': vid.get('filename', ''),
            'category': vid.get('category', ''),
            'views': vid.get('views', 0),
            'uploaded_at': vid.get('uploaded_at', ''),
            'size': vid.get('size', ''),
            'format': vid.get('format', ''),
            'rating': vid.get('rating', 0),
            'is_in_mylist': is_in_mylist(username, vid_id)
        })
    
    video_list.sort(key=lambda x: x['views'], reverse=True)
    
    return jsonify({
        'total_videos': total_videos,
        'total_views': total_views,
        'avg_rating': round(avg_rating, 1),
        'videos': video_list,
        'profile_pic': load_users().get(username, {}).get('profile_pic', '')
    })

@app.route('/api/video/<video_id>/rate', methods=['POST'])
@login_required
def api_rate_video(video_id):
    data = request.json
    rating = data.get('rating', 0)
    if rating < 1 or rating > 5:
        return jsonify({'error': 'Rating must be between 1 and 5'}), 400
    
    videos = load_videos()
    if video_id not in videos:
        return jsonify({'error': 'Video not found'}), 404
    
    videos[video_id]['rating'] = rating
    save_videos(videos)
    return jsonify({'success': True, 'rating': rating})

@app.route('/api/mylist', methods=['GET', 'POST', 'DELETE'])
@login_required
def api_mylist():
    username = session.get('username')
    
    if request.method == 'GET':
        mylist = get_user_mylist(username)
        return jsonify({'mylist': mylist})
    
    data = request.json
    video_id = data.get('video_id')
    
    if not video_id:
        return jsonify({'error': 'Video ID required'}), 400
    
    if request.method == 'POST':
        result = add_to_mylist(username, video_id)
        return jsonify({'success': result})
    
    if request.method == 'DELETE':
        result = remove_from_mylist(username, video_id)
        return jsonify({'success': result})

@app.route('/api/mylist/add/<video_id>', methods=['POST'])
@login_required
def api_mylist_add(video_id):
    username = session.get('username')
    result = add_to_mylist(username, video_id)
    return jsonify({'success': result})

@app.route('/api/mylist/remove/<video_id>', methods=['DELETE'])
@login_required
def api_mylist_remove(video_id):
    username = session.get('username')
    result = remove_from_mylist(username, video_id)
    return jsonify({'success': result})

@app.route('/api/watch-history', methods=['GET'])
@login_required
def api_watch_history():
    username = session.get('username')
    history = get_user_watch_history(username)
    return jsonify({'history': history})

@app.route('/api/upload', methods=['POST'])
@login_required
def api_upload():
    username = session.get('username')
    users = load_users()
    
    if username not in users:
        return jsonify({'error': 'User not found'}), 401
    
    if 'movie_file' not in request.files:
        return jsonify({'error': 'No file selected'}), 400
    
    file = request.files['movie_file']
    category = request.form.get('category', '')
    title = request.form.get('title', '')
    
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    if not category:
        return jsonify({'error': 'Please select a category'}), 400
    
    if category not in [c['id'] for c in MOVIE_CATEGORIES]:
        return jsonify({'error': 'Invalid category'}), 400
    
    temp_path = os.path.join(tempfile.gettempdir(), file.filename)
    file.save(temp_path)
    
    remote_path = f'/movies/{category}/{file.filename}'
    success = upload_file_to_ftp(temp_path, remote_path)
    os.remove(temp_path)
    
    if not success:
        return jsonify({'error': 'Upload failed. Check FTP server connection.'}), 500
    
    videos = load_videos()
    video_id = generate_video_id()
    
    file_size_bytes = os.path.getsize(temp_path)
    if file_size_bytes < 1024*1024:
        size_str = f"{file_size_bytes/1024:.1f} KB"
    elif file_size_bytes < 1024*1024*1024:
        size_str = f"{file_size_bytes/(1024*1024):.1f} MB"
    else:
        size_str = f"{file_size_bytes/(1024*1024*1024):.2f} GB"
    
    videos[video_id] = {
        'title': title if title else os.path.splitext(file.filename)[0],
        'filename': file.filename,
        'category': category,
        'uploaded_by': username,
        'uploaded_at': datetime.now().isoformat(),
        'views': 0,
        'size': size_str,
        'format': os.path.splitext(file.filename)[1].upper().replace('.', ''),
        'rating': 0,
        'thumbnail_color': generate_thumbnail(file.filename)
    }
    save_videos(videos)
    
    update_user_total_views(username)
    
    return jsonify({'success': True, 'message': f'Movie "{file.filename}" uploaded successfully!', 'video_id': video_id})

@app.route('/api/admin/stats', methods=['GET'])
@admin_required
def api_admin_stats():
    stats = get_video_stats()
    users = load_users()
    
    user_list = [
        {
            'username': u,
            'role': data.get('role', 'user'),
            'created_at': data.get('created_at', ''),
            'total_views': data.get('total_views', 0),
            'total_uploads': data.get('total_uploads', 0),
            'profile_pic': data.get('profile_pic', '')
        }
        for u, data in users.items()
    ]
    
    return jsonify({
        'stats': stats,
        'users': user_list
    })

@app.route('/api/admin/delete-video/<video_id>', methods=['DELETE'])
@admin_required
def api_admin_delete_video(video_id):
    videos = load_videos()
    if video_id not in videos:
        return jsonify({'error': 'Video not found'}), 404
    
    video = videos[video_id]
    try:
        ftp = get_ftp_connection()
        remote_path = f'/movies/{video["category"]}/{video["filename"]}'
        ftp.delete(remote_path)
        ftp.quit()
    except:
        pass
    
    uploaded_by = video.get('uploaded_by')
    del videos[video_id]
    save_videos(videos)
    
    if uploaded_by:
        update_user_total_views(uploaded_by)
    
    return jsonify({'success': True, 'message': 'Video deleted successfully'})

@app.route('/api/admin/delete-user/<username>', methods=['DELETE'])
@admin_required
def api_admin_delete_user(username):
    if username == 'admin':
        return jsonify({'error': 'Cannot delete admin user'}), 403
    
    users = load_users()
    if username not in users:
        return jsonify({'error': 'User not found'}), 404
    
    videos = load_videos()
    videos_to_delete = [vid_id for vid_id, vid in videos.items() if vid.get('uploaded_by') == username]
    for vid_id in videos_to_delete:
        del videos[vid_id]
    save_videos(videos)
    
    del users[username]
    save_users(users)
    
    return jsonify({'success': True, 'message': f'User {username} deleted successfully'})

@app.route('/api/profile-pic', methods=['POST'])
@login_required
def api_upload_profile_pic():
    username = session.get('username')
    if 'profile_pic' not in request.files:
        return jsonify({'error': 'No file selected'}), 400
    
    file = request.files['profile_pic']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    allowed_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.webp'}
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in allowed_extensions:
        return jsonify({'error': 'Invalid file type. Use JPG, PNG, GIF, or WEBP'}), 400
    
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    
    filename = f"{username}_{secrets.token_hex(4)}{ext}"
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    file.save(filepath)
    
    users = load_users()
    if username in users:
        old_pic = users[username].get('profile_pic', '')
        if old_pic and old_pic.startswith(f'/{UPLOAD_FOLDER}/'):
            old_path = os.path.join('.', old_pic[1:])
            if os.path.exists(old_path):
                try:
                    os.remove(old_path)
                except:
                    pass
        
        users[username]['profile_pic'] = f"/{UPLOAD_FOLDER}/{filename}"
        save_users(users)
        return jsonify({'success': True, 'profile_pic': f"/{UPLOAD_FOLDER}/{filename}"})
    
    return jsonify({'error': 'User not found'}), 404

# ===== ADMIN ROUTES =====

@app.route('/admin', methods=['GET'])
def admin_panel():
    """Admin panel - ONLY accessible via /admin URL"""
    if 'username' not in session:
        return render_template('admin_login.html', theme=session.get('theme', 'dark'))
    
    users = load_users()
    if session.get('username') not in users or users[session.get('username')].get('role') != 'admin':
        flash('Admin access required', 'error')
        return redirect(url_for('index'))
    
    stats = get_video_stats()
    return render_template('admin.html', 
                         stats=stats,
                         users=users,
                         categories=MOVIE_CATEGORIES,
                         username=session.get('username', ''),
                         theme=session.get('theme', 'dark'))

@app.route('/admin/login', methods=['POST'])
def admin_login():
    """Admin login form submission - ONLY for /admin URL"""
    username = request.form.get('username', '').strip()
    password = request.form.get('password', '').strip()
    users = load_users()
    
    if username not in users or users[username].get('password') != password:
        flash('Invalid credentials', 'error')
        return redirect(url_for('admin_panel'))
    
    if users[username].get('role') != 'admin':
        flash('Admin access required', 'error')
        return redirect(url_for('admin_panel'))
    
    session['username'] = username
    session['role'] = 'admin'
    flash('Welcome Admin!', 'success')
    return redirect(url_for('admin_panel'))

@app.route('/admin/logout')
def admin_logout():
    """Admin logout"""
    session.clear()
    flash('Logged out successfully', 'success')
    return redirect(url_for('admin_panel'))

@app.route('/admin/upload', methods=['POST'])
@admin_required
def admin_upload():
    """Admin upload route"""
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
    
    temp_path = os.path.join(tempfile.gettempdir(), file.filename)
    file.save(temp_path)
    remote_path = f'/movies/{category}/{file.filename}'
    success = upload_file_to_ftp(temp_path, remote_path)
    os.remove(temp_path)
    
    if success:
        videos = load_videos()
        video_id = generate_video_id()
        
        file_size_bytes = os.path.getsize(temp_path)
        if file_size_bytes < 1024*1024:
            size_str = f"{file_size_bytes/1024:.1f} KB"
        elif file_size_bytes < 1024*1024*1024:
            size_str = f"{file_size_bytes/(1024*1024):.1f} MB"
        else:
            size_str = f"{file_size_bytes/(1024*1024*1024):.2f} GB"
        
        videos[video_id] = {
            'title': title if title else os.path.splitext(file.filename)[0],
            'filename': file.filename,
            'category': category,
            'uploaded_by': session.get('username', 'admin'),
            'uploaded_at': datetime.now().isoformat(),
            'views': 0,
            'size': size_str,
            'format': os.path.splitext(file.filename)[1].upper().replace('.', ''),
            'rating': 0,
            'thumbnail_color': generate_thumbnail(file.filename)
        }
        save_videos(videos)
        update_user_total_views(session.get('username', 'admin'))
        
        flash(f'Movie "{file.filename}" uploaded successfully!', 'success')
    else:
        flash('Upload failed. Check FTP server connection.', 'error')
    
    return redirect(url_for('admin_panel'))

# ===== USER ROUTES =====

@app.route('/dashboard')
@login_required
def dashboard():
    username = session.get('username')
    users = load_users()
    user_data = users.get(username, {})
    return render_template('dashboard.html',
                         username=username,
                         profile_pic=user_data.get('profile_pic', ''),
                         categories=MOVIE_CATEGORIES,
                         logged_in=True,
                         theme=session.get('theme', 'dark'))

@app.route('/profile/<username>')
def profile_page(username):
    users = load_users()
    if username not in users:
        flash('User not found', 'error')
        return redirect(url_for('index'))
    
    user_data = users[username]
    videos = get_user_videos(username)
    video_list = []
    for vid_id, vid in videos.items():
        video_list.append({**vid, 'id': vid_id})
    video_list.sort(key=lambda x: x.get('views', 0), reverse=True)
    
    return render_template('profile.html',
                         profile_user=username,
                         user_data=user_data,
                         videos=video_list,
                         categories=MOVIE_CATEGORIES,
                         logged_in='username' in session,
                         current_user=session.get('username', ''),
                         theme=session.get('theme', 'dark'))

@app.route('/mylist')
@login_required
def mylist():
    username = session.get('username')
    mylist = get_user_mylist(username)
    return render_template('mylist.html',
                         mylist=mylist,
                         categories=MOVIE_CATEGORIES,
                         logged_in=True,
                         username=username,
                         theme=session.get('theme', 'dark'))

@app.route('/watch-history')
@login_required
def watch_history():
    username = session.get('username')
    history = get_user_watch_history(username)
    return render_template('watch_history.html',
                         history=history,
                         categories=MOVIE_CATEGORIES,
                         logged_in=True,
                         username=username,
                         theme=session.get('theme', 'dark'))

@app.route('/leaderboard')
def leaderboard_page():
    """Full leaderboard page - accessible to all but only shows meaningful data for logged-in users"""
    return render_template('leaderboard.html', 
                         categories=MOVIE_CATEGORIES,
                         logged_in='username' in session,
                         username=session.get('username', ''),
                         theme=session.get('theme', 'dark'))

# ============================================================
# WATCH MOVIE ROUTE - EXTERNAL VIDEO EMBED (NEW)
# ============================================================

@app.route('/watch/<video_id>')
def watch_movie(video_id):
    """Watch movie page with embedded video"""
    videos = load_videos()
    if video_id not in videos:
        abort(404)
    
    movie = videos[video_id]
    # Increment views
    movie['views'] = movie.get('views', 0) + 1
    save_videos(videos)
    
    return render_template('embed.html', 
                         movie=movie,
                         logged_in='username' in session,
                         theme=session.get('theme', 'dark'))

# ============================================================
# OTHER ROUTES
# ============================================================

@app.route('/health')
def health():
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'users': len(load_users()),
        'videos': len(load_videos())
    })

# ============================================================
# SERVER START
# ============================================================

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(debug=False, host='0.0.0.0', port=port)
