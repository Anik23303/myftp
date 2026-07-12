from flask import Flask, render_template, request, send_file, abort, jsonify
from flask_cors import CORS
import os
import tempfile
import logging
import time
from datetime import datetime
import re

# Initialize Flask app
app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'dev-secret-key')

# Setup CORS
CORS(app)

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration from environment
FTP_HOST = os.getenv('FTP_HOST', 'your-ftp-server.com')
FTP_PORT = int(os.getenv('FTP_PORT', 21))
FTP_USER = os.getenv('FTP_USER', 'anonymous')
FTP_PASS = os.getenv('FTP_PASS', '')

# Movie categories (these match your FTP folder structure)
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

# Simple FTP client (built-in, no extra dependencies)
from ftplib import FTP, error_perm

def get_ftp_connection():
    """Get FTP connection"""
    ftp = FTP()
    ftp.connect(FTP_HOST, FTP_PORT)
    ftp.login(FTP_USER, FTP_PASS)
    ftp.set_pasv(True)  # Passive mode for firewalls
    return ftp

def get_movie_listing(category):
    """Get movie listing from FTP"""
    movies = []
    try:
        ftp = get_ftp_connection()
        # Navigate to category folder
        remote_path = f'/movies/{category}'
        try:
            ftp.cwd(remote_path)
        except:
            # Category folder doesn't exist
            ftp.quit()
            return []
        
        # List files
        files = []
        try:
            # Try MLSD first (modern FTP)
            files = list(ftp.mlsd())
        except:
            # Fallback to LIST
            def parse_line(line):
                parts = line.split()
                if len(parts) >= 9:
                    filename = ' '.join(parts[8:])
                    size = parts[4]
                    is_dir = line.startswith('d')
                    return {
                        'filename': filename,
                        'size': size,
                        'type': 'directory' if is_dir else 'file'
                    }
            ftp.dir(lambda line: files.append(parse_line(line)))
        
        ftp.quit()
        
        # Filter video files
        video_extensions = {'.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.webm', '.m4v'}
        for file in files:
            if isinstance(file, dict) and file.get('type') == 'file':
                filename = file['filename']
                ext = os.path.splitext(filename)[1].lower()
                if ext in video_extensions:
                    # Extract year from filename
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
        
        # Sort by title
        movies.sort(key=lambda x: x['title'])
        
    except Exception as e:
        logger.error(f"Error getting movies for {category}: {e}")
    
    return movies

@app.route('/')
def index():
    """Homepage"""
    return render_template('index.html', categories=MOVIE_CATEGORIES)

@app.route('/category/<category_id>')
def category_movies(category_id):
    """List movies in category"""
    category = next((c for c in MOVIE_CATEGORIES if c['id'] == category_id), None)
    if not category:
        abort(404)
    
    movies = get_movie_listing(category_id)
    
    return render_template('movies.html', 
                         category=category_id,
                         category_name=category['name'],
                         category_icon=category['icon'],
                         movies=movies,
                         categories=MOVIE_CATEGORIES)

@app.route('/stream/<category>/<filename>')
def stream_movie(category, filename):
    """Stream movie"""
    try:
        ftp = get_ftp_connection()
        remote_path = f'/movies/{category}/{filename}'
        
        # Download to temp file
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(filename)[1])
        temp_path = temp_file.name
        temp_file.close()
        
        with open(temp_path, 'wb') as f:
            ftp.retrbinary(f'RETR {remote_path}', f.write)
        ftp.quit()
        
        # Determine mimetype
        ext = os.path.splitext(filename)[1].lower()
        mimetype = 'video/mp4'
        if ext == '.mkv':
            mimetype = 'video/x-matroska'
        elif ext == '.avi':
            mimetype = 'video/x-msvideo'
        elif ext == '.mov':
            mimetype = 'video/quicktime'
        
        return send_file(temp_path, mimetype=mimetype, conditional=True)
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
                         categories=MOVIE_CATEGORIES)

@app.route('/health')
def health():
    """Health check"""
    return jsonify({'status': 'healthy', 'timestamp': datetime.now().isoformat()})

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(debug=False, host='0.0.0.0', port=port)
