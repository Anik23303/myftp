from pyftpdlib.authorizers import DummyAuthorizer
from pyftpdlib.handlers import FTPHandler
from pyftpdlib.servers import FTPServer
import os
import json
from pathlib import Path
import tempfile
from datetime import datetime

# Simple user database (JSON)
USERS_FILE = "users.json"
TEMP_DIR = "/tmp/ftp_storage"  # Temporary local storage before upload to cloud

class UserManager:
    def __init__(self):
        self.users_file = USERS_FILE
        self.ensure_users_file()
    
    def ensure_users_file(self):
        if not os.path.exists(self.users_file):
            default_users = {
                "admin": {"password": "admin123", "role": "admin"},
                "guest": {"password": "guest123", "role": "user"}
            }
            self.save_users(default_users)
    
    def load_users(self):
        with open(self.users_file, 'r') as f:
            return json.load(f)
    
    def save_users(self, users):
        with open(self.users_file, 'w') as f:
            json.dump(users, f, indent=2)
    
    def create_user(self, username, password, role="user"):
        users = self.load_users()
        if username in users:
            return False, "User already exists"
        users[username] = {"password": password, "role": role}
        self.save_users(users)
        return True, "User created successfully"
    
    def verify_user(self, username, password):
        users = self.load_users()
        if username in users and users[username]["password"] == password:
            return True
        return False

class CustomFTPHandler(FTPHandler):
    def __init__(self, conn, server, user_manager):
        self.user_manager = user_manager
        super().__init__(conn, server)

def setup_ftp_server(host="0.0.0.0", port=21):
    # Create temp directory
    os.makedirs(TEMP_DIR, exist_ok=True)
    
    # Initialize user manager
    user_manager = UserManager()
    
    # Create authorizer
    authorizer = DummyAuthorizer()
    
    # Load users and add to authorizer
    users = user_manager.load_users()
    for username, user_data in users.items():
        password = user_data["password"]
        role = user_data["role"]
        
        # Create user directory
        user_dir = os.path.join(TEMP_DIR, username)
        os.makedirs(user_dir, exist_ok=True)
        
        # Set permissions (admins have full access)
        if role == "admin":
            perm = "elradfmw"  # Full permissions
        else:
            perm = "elradf"    # Read, list, append, delete (own files), create folder, modify
        
        authorizer.add_user(username, password, user_dir, perm=perm)
    
    # Create handler
    handler = FTPHandler
    handler.authorizer = authorizer
    handler.banner = "Welcome to Media FTP Server"
    
    # Additional handler settings
    handler.permit_foreign_addresses = True
    handler.max_connections = 1000
    handler.max_connections_per_ip = 50
    
    # Create and start server
    server = FTPServer((host, port), handler)
    print(f"🚀 FTP Server started on {host}:{port}")
    print(f"📝 Default users:")
    print(f"   - admin / admin123 (full access)")
    print(f"   - guest / guest123 (limited access)")
    print(f"\n⚠️  Change default passwords immediately!")
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n🛑 Server stopped")

if __name__ == "__main__":
    setup_ftp_server()
