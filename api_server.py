from flask import Flask, request, jsonify
from flask_cors import CORS
import json
import os
from functools import wraps

app = Flask(__name__)
CORS(app)

USERS_FILE = "users.json"
ADMIN_TOKEN = os.getenv('ADMIN_TOKEN', 'your_secret_admin_token_here')

def load_users():
    if not os.path.exists(USERS_FILE):
        return {}
    with open(USERS_FILE, 'r') as f:
        return json.load(f)

def save_users(users):
    with open(USERS_FILE, 'w') as f:
        json.dump(users, f, indent=2)

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        token = request.headers.get('Authorization', '')
        if token != f"Bearer {ADMIN_TOKEN}":
            return jsonify({"error": "Unauthorized - Admin token required"}), 401
        return f(*args, **kwargs)
    return decorated_function

@app.route('/', methods=['GET'])
def home():
    return jsonify({
        "message": "Media FTP Server API",
        "endpoints": {
            "register": "POST /api/register",
            "admin_panel": "GET /admin",
            "users_list": "GET /api/users (admin only)",
            "delete_user": "DELETE /api/delete-user/<username> (admin only)",
            "change_password": "POST /api/change-password"
        }
    })

@app.route('/api/register', methods=['POST'])
def register():
    data = request.json
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()
    
    # Validation
    if not username or not password:
        return jsonify({"error": "Username and password required"}), 400
    
    if len(username) < 3 or len(password) < 6:
        return jsonify({"error": "Username must be 3+ chars, password 6+ chars"}), 400
    
    if not username.isalnum():
        return jsonify({"error": "Username must be alphanumeric"}), 400
    
    users = load_users()
    if username in users:
        return jsonify({"error": "Username already exists"}), 400
    
    users[username] = {"password": password, "role": "user"}
    save_users(users)
    
    return jsonify({
        "message": "User registered successfully",
        "ftp_host": os.getenv("FTP_HOST", "your-domain.com"),
        "ftp_port": 21,
        "username": username,
        "instructions": "Use this username and password in your FTP client (FileZilla, WinSCP, etc.)"
    }), 201

@app.route('/api/change-password', methods=['POST'])
def change_password():
    data = request.json
    username = data.get('username', '').strip()
    old_password = data.get('old_password', '').strip()
    new_password = data.get('new_password', '').strip()
    
    if not all([username, old_password, new_password]):
        return jsonify({"error": "All fields required"}), 400
    
    if len(new_password) < 6:
        return jsonify({"error": "New password must be 6+ chars"}), 400
    
    users = load_users()
    if username not in users:
        return jsonify({"error": "User not found"}), 404
    
    if users[username]["password"] != old_password:
        return jsonify({"error": "Old password incorrect"}), 401
    
    users[username]["password"] = new_password
    save_users(users)
    
    return jsonify({"message": "Password changed successfully"})

@app.route('/api/users', methods=['GET'])
@admin_required
def get_users():
    users = load_users()
    return jsonify({
        "total_users": len(users),
        "users": [
            {"username": u, "role": users[u].get("role", "user")}
            for u in users.keys()
        ]
    })

@app.route('/api/delete-user/<username>', methods=['DELETE'])
@admin_required
def delete_user(username):
    users = load_users()
    if username not in users:
        return jsonify({"error": "User not found"}), 404
    
    if username == "admin":
        return jsonify({"error": "Cannot delete admin user"}), 403
    
    del users[username]
    save_users(users)
    
    return jsonify({"message": f"User {username} deleted"})

@app.route('/admin', methods=['GET'])
def admin_panel():
    return '''<!DOCTYPE html>
<html>
<head>
    <title>Media FTP Server - Admin Panel</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: Arial, sans-serif; background: #1a1a1a; color: #fff; }
        .container { max-width: 800px; margin: 50px auto; padding: 20px; }
        .header { text-align: center; margin-bottom: 30px; }
        h1 { color: #00ff00; margin-bottom: 10px; }
        .login-form { background: #2a2a2a; padding: 20px; border-radius: 8px; margin-bottom: 20px; }
        .form-group { margin-bottom: 15px; }
        label { display: block; margin-bottom: 5px; font-weight: bold; }
        input, button { width: 100%; padding: 10px; margin-bottom: 10px; border: none; border-radius: 4px; }
        input { background: #333; color: #fff; }
        button { background: #00ff00; color: #000; cursor: pointer; font-weight: bold; }
        button:hover { background: #00cc00; }
        .dashboard { display: none; background: #2a2a2a; padding: 20px; border-radius: 8px; }
        .dashboard.active { display: block; }
        .user-list { margin-top: 20px; }
        .user-item { background: #333; padding: 10px; margin-bottom: 10px; border-radius: 4px; display: flex; justify-content: space-between; align-items: center; }
        .delete-btn { background: #ff4444; padding: 5px 10px; border-radius: 4px; cursor: pointer; }
        .success { color: #00ff00; padding: 10px; background: #1a3a1a; border-radius: 4px; margin-bottom: 10px; }
        .error { color: #ff4444; padding: 10px; background: #3a1a1a; border-radius: 4px; margin-bottom: 10px; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🚀 Media FTP Server Admin Panel</h1>
            <p>Manage users and server settings</p>
        </div>

        <div id="loginSection" class="login-form">
            <div class="form-group">
                <label>Admin Security Token:</label>
                <input type="password" id="adminToken" placeholder="Enter admin token">
            </div>
            <button onclick="login()">Login to Admin Panel</button>
            <div id="loginMessage"></div>
        </div>

        <div id="dashboard" class="dashboard">
            <h2>Admin Dashboard</h2>
            <button onclick="logout()" style="background: #ff4444; margin-bottom: 20px; width: auto; padding: 10px 20px;">Logout</button>
            
            <div class="user-list">
                <h3>Users List</h3>
                <div id="usersList"></div>
                <button onclick="loadUsers()" style="width: auto; margin-top: 10px;">Refresh Users</button>
            </div>
        </div>
    </div>

    <script>
        let adminToken = null;

        function login() {
            adminToken = document.getElementById('adminToken').value;
            if (!adminToken) {
                showMessage('loginMessage', 'Please enter the admin token', 'error');
                return;
            }
            loadUsers();
        }

        function logout() {
            adminToken = null;
            document.getElementById('dashboard').classList.remove('active');
            document.getElementById('loginSection').style.display = 'block';
            document.getElementById('adminToken').value = '';
        }

        function loadUsers() {
            fetch('/api/users', {
                headers: { 'Authorization': `Bearer ${adminToken}` }
            })
            .then(r => r.json())
            .then(data => {
                if (data.error) {
                    showMessage('loginMessage', 'Invalid admin token', 'error');
                    return;
                }
                document.getElementById('loginSection').style.display = 'none';
                document.getElementById('dashboard').classList.add('active');
                
                let html = '';
                data.users.forEach(user => {
                    html += `<div class="user-item">
                        <span>${user.username} (${user.role})</span>
                        ${user.username !== 'admin' ? `<button class="delete-btn" onclick="deleteUser('${user.username}')">Delete</button>` : ''}
                    </div>`;
                });
                document.getElementById('usersList').innerHTML = html || '<p>No users found</p>';
                showMessage('usersList', `Total users: ${data.total_users}`, 'success', true);
            })
            .catch(e => showMessage('loginMessage', 'Error loading users', 'error'));
        }

        function deleteUser(username) {
            if (confirm(`Delete user ${username}?`)) {
                fetch(`/api/delete-user/${username}`, {
                    method: 'DELETE',
                    headers: { 'Authorization': `Bearer ${adminToken}` }
                })
                .then(r => r.json())
                .then(data => {
                    if (data.error) {
                        showMessage('usersList', data.error, 'error', true);
                    } else {
                        showMessage('usersList', data.message, 'success', true);
                        loadUsers();
                    }
                })
                .catch(e => showMessage('usersList', 'Error deleting user', 'error', true));
            }
        }

        function showMessage(elementId, message, type, prepend = false) {
            const element = document.getElementById(elementId);
            const msg = `<div class="${type}">${message}</div>`;
            if (prepend) {
                element.innerHTML = msg + element.innerHTML;
            } else {
                element.innerHTML = msg;
            }
        }
    </script>
</body>
</html>
'''

if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=int(os.getenv('PORT', 5000)))
