from flask import Flask, render_template_string, request, jsonify, session, redirect, url_for, send_from_directory
import sqlite3
import hashlib
import uuid
import os
import base64
from datetime import datetime
import secrets

app = Flask(__name__)
app.secret_key = secrets.token_hex(16)

# Configuration
DATABASE = 'chatroom.db'
UPLOAD_FOLDER = 'uploads'
MAX_IMAGE_SIZE = 1024 * 1024  # 1MB default

# Ensure upload directory exists
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def init_db():
    """Initialize the database with required tables"""
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    
    # Users table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            email TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_banned BOOLEAN DEFAULT 0,
            is_admin BOOLEAN DEFAULT 0
        )
    ''')
    
    # Messages table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT NOT NULL,
            message_type TEXT NOT NULL,
            content TEXT,
            image_data TEXT,
            url TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    
    # Settings table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    ''')
    
    # Insert default settings
    cursor.execute('INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)', ('max_image_size', str(MAX_IMAGE_SIZE)))
    cursor.execute('INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)', ('admin_password', 'admin123'))
    
    # Create default admin user
    admin_hash = hashlib.sha256('admin123'.encode()).hexdigest()
    cursor.execute('INSERT OR IGNORE INTO users (username, password_hash, is_admin) VALUES (?, ?, ?)', ('admin', admin_hash, 1))
    
    conn.commit()
    conn.close()

def get_db_connection():
    """Get database connection"""
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def hash_password(password):
    """Hash password using SHA256"""
    return hashlib.sha256(password.encode()).hexdigest()

def get_setting(key):
    """Get setting value from database"""
    conn = get_db_connection()
    result = conn.execute('SELECT value FROM settings WHERE key = ?', (key,)).fetchone()
    conn.close()
    return result['value'] if result else None

def update_setting(key, value):
    """Update setting in database"""
    conn = get_db_connection()
    conn.execute('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', (key, value))
    conn.commit()
    conn.close()

# HTML Template
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Chatroom</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        
        .container {
            background: white;
            border-radius: 15px;
            box-shadow: 0 20px 40px rgba(0,0,0,0.1);
            width: 100%;
            max-width: 800px;
            height: 90vh;
            display: flex;
            flex-direction: column;
            overflow: hidden;
        }
        
        .header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 20px;
            text-align: center;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        
        .user-info {
            display: flex;
            align-items: center;
            gap: 15px;
        }
        
        .logout-btn, .admin-btn {
            background: rgba(255,255,255,0.2);
            border: none;
            color: white;
            padding: 8px 15px;
            border-radius: 20px;
            cursor: pointer;
            transition: all 0.3s;
        }
        
        .logout-btn:hover, .admin-btn:hover {
            background: rgba(255,255,255,0.3);
        }
        
        .messages {
            flex: 1;
            overflow-y: auto;
            padding: 20px;
            background: #f8f9fa;
        }
        
        .message {
            margin-bottom: 15px;
            padding: 15px;
            border-radius: 10px;
            background: white;
            box-shadow: 0 2px 5px rgba(0,0,0,0.1);
            animation: fadeIn 0.3s ease-in;
        }
        
        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(10px); }
            to { opacity: 1; transform: translateY(0); }
        }
        
        .message-header {
            display: flex;
            justify-content: space-between;
            margin-bottom: 8px;
            font-size: 12px;
            color: #666;
        }
        
        .username {
            font-weight: bold;
            color: #667eea;
        }
        
        .message-content {
            line-height: 1.4;
        }
        
        .message-image {
            max-width: 100%;
            max-height: 300px;
            border-radius: 8px;
            margin-top: 10px;
        }
        
        .message-url {
            color: #667eea;
            text-decoration: none;
            margin-top: 10px;
            display: block;
        }
        
        .message-url:hover {
            text-decoration: underline;
        }
        
        .input-area {
            padding: 20px;
            border-top: 1px solid #eee;
            background: white;
        }
        
        .message-type-selector {
            display: flex;
            gap: 10px;
            margin-bottom: 15px;
        }
        
        .type-btn {
            padding: 8px 15px;
            border: 2px solid #667eea;
            background: white;
            color: #667eea;
            border-radius: 20px;
            cursor: pointer;
            transition: all 0.3s;
        }
        
        .type-btn.active {
            background: #667eea;
            color: white;
        }
        
        .input-group {
            display: flex;
            gap: 10px;
            align-items: flex-end;
        }
        
        .input-field {
            flex: 1;
            padding: 12px;
            border: 2px solid #eee;
            border-radius: 25px;
            outline: none;
            transition: border-color 0.3s;
        }
        
        .input-field:focus {
            border-color: #667eea;
        }
        
        .file-input {
            display: none;
        }
        
        .file-btn, .send-btn {
            background: #667eea;
            color: white;
            border: none;
            padding: 12px 20px;
            border-radius: 25px;
            cursor: pointer;
            transition: all 0.3s;
        }
        
        .file-btn:hover, .send-btn:hover {
            background: #5a6fd8;
            transform: translateY(-2px);
        }
        
        .login-form, .register-form, .admin-panel {
            max-width: 400px;
            margin: 0 auto;
            padding: 40px;
            background: white;
            border-radius: 15px;
            box-shadow: 0 20px 40px rgba(0,0,0,0.1);
        }
        
        .form-group {
            margin-bottom: 20px;
        }
        
        .form-group label {
            display: block;
            margin-bottom: 5px;
            font-weight: bold;
            color: #333;
        }
        
        .form-group input {
            width: 100%;
            padding: 12px;
            border: 2px solid #eee;
            border-radius: 8px;
            outline: none;
            transition: border-color 0.3s;
        }
        
        .form-group input:focus {
            border-color: #667eea;
        }
        
        .btn-primary {
            width: 100%;
            background: #667eea;
            color: white;
            border: none;
            padding: 12px;
            border-radius: 8px;
            cursor: pointer;
            font-size: 16px;
            transition: background 0.3s;
        }
        
        .btn-primary:hover {
            background: #5a6fd8;
        }
        
        .switch-form {
            text-align: center;
            margin-top: 20px;
        }
        
        .switch-form a {
            color: #667eea;
            text-decoration: none;
        }
        
        .admin-section {
            margin: 20px 0;
            padding: 20px;
            border: 1px solid #eee;
            border-radius: 8px;
        }
        
        .admin-section h3 {
            margin-bottom: 15px;
            color: #333;
        }
        
        .user-list {
            max-height: 200px;
            overflow-y: auto;
        }
        
        .user-item {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 10px;
            border-bottom: 1px solid #eee;
        }
        
        .user-actions button {
            margin-left: 5px;
            padding: 5px 10px;
            border: none;
            border-radius: 4px;
            cursor: pointer;
        }
        
        .btn-danger {
            background: #dc3545;
            color: white;
        }
        
        .btn-warning {
            background: #ffc107;
            color: black;
        }
        
        .hidden {
            display: none;
        }
    </style>
</head>
<body>
    <!-- Login Form -->
    <div id="loginForm" class="login-form">
        <h2 style="text-align: center; margin-bottom: 30px; color: #667eea;">Login to Chatroom</h2>
        <form onsubmit="login(event)">
            <div class="form-group">
                <label for="loginUsername">Username:</label>
                <input type="text" id="loginUsername" required>
            </div>
            <div class="form-group">
                <label for="loginPassword">Password:</label>
                <input type="password" id="loginPassword" required>
            </div>
            <button type="submit" class="btn-primary">Login</button>
        </form>
        <div class="switch-form">
            <a href="#" onclick="showRegister()">Don't have an account? Register here</a>
        </div>
    </div>
    
    <!-- Register Form -->
    <div id="registerForm" class="register-form hidden">
        <h2 style="text-align: center; margin-bottom: 30px; color: #667eea;">Create Account</h2>
        <form onsubmit="register(event)">
            <div class="form-group">
                <label for="regUsername">Username:</label>
                <input type="text" id="regUsername" required>
            </div>
            <div class="form-group">
                <label for="regEmail">Email (optional):</label>
                <input type="email" id="regEmail">
            </div>
            <div class="form-group">
                <label for="regPassword">Password:</label>
                <input type="password" id="regPassword" required>
            </div>
            <button type="submit" class="btn-primary">Create Account</button>
        </form>
        <div class="switch-form">
            <a href="#" onclick="showLogin()">Already have an account? Login here</a>
        </div>
    </div>
    
    <!-- Chat Interface -->
    <div id="chatInterface" class="container hidden">
        <div class="header">
            <h1>💬 Chatroom</h1>
            <div class="user-info">
                <span id="currentUser"></span>
                <button class="admin-btn" id="adminBtn" onclick="showAdmin()" style="display: none;">Admin</button>
                <button class="logout-btn" onclick="logout()">Logout</button>
            </div>
        </div>
        
        <div class="messages" id="messages"></div>
        
        <div class="input-area">
            <div class="message-type-selector">
                <button class="type-btn active" onclick="setMessageType('text')">Text</button>
                <button class="type-btn" onclick="setMessageType('image')">Image</button>
                <button class="type-btn" onclick="setMessageType('text+image')">Text + Image</button>
                <button class="type-btn" onclick="setMessageType('url')">URL</button>
            </div>
            
            <div class="input-group">
                <input type="text" class="input-field" id="messageInput" placeholder="Type your message...">
                <input type="url" class="input-field hidden" id="urlInput" placeholder="Enter URL...">
                <input type="file" class="file-input" id="imageInput" accept="image/*">
                <button class="file-btn hidden" id="fileBtn" onclick="document.getElementById('imageInput').click()">📁</button>
                <button class="send-btn" onclick="sendMessage()">Send</button>
            </div>
        </div>
    </div>
    
    <!-- Admin Panel -->
    <div id="adminPanel" class="admin-panel hidden">
        <h2 style="text-align: center; margin-bottom: 30px; color: #667eea;">Admin Dashboard</h2>
        
        <div class="admin-section">
            <h3>Settings</h3>
            <div class="form-group">
                <label for="maxImageSize">Max Image Size (KB):</label>
                <input type="number" id="maxImageSize" value="1024">
                <button onclick="updateSettings()" style="margin-top: 10px;" class="btn-primary">Update Settings</button>
            </div>
        </div>
        
        <div class="admin-section">
            <h3>Users</h3>
            <div id="usersList" class="user-list"></div>
        </div>
        
        <div class="admin-section">
            <h3>Actions</h3>
            <button onclick="deleteAllMessages()" class="btn-danger" style="width: 100%; margin-bottom: 10px;">Delete All Messages</button>
        </div>
        
        <button onclick="hideAdmin()" class="btn-primary">Back to Chat</button>
    </div>
    
    <script>
        let currentMessageType = 'text';
        let currentUser = null;
        let isAdmin = false;
        
        // Check if user is logged in on page load
        window.onload = function() {
            checkLoginStatus();
            if (currentUser) {
                loadMessages();
                setInterval(loadMessages, 2000); // Poll for new messages every 2 seconds
            }
        };
        
        function checkLoginStatus() {
            fetch('/api/check_login')
                .then(response => response.json())
                .then(data => {
                    if (data.logged_in) {
                        currentUser = data.username;
                        isAdmin = data.is_admin;
                        showChat();
                    }
                });
        }
        
        function login(event) {
            event.preventDefault();
            const username = document.getElementById('loginUsername').value;
            const password = document.getElementById('loginPassword').value;
            
            fetch('/api/login', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({username, password})
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    currentUser = username;
                    isAdmin = data.is_admin;
                    showChat();
                    loadMessages();
                    setInterval(loadMessages, 2000);
                } else {
                    alert(data.message);
                }
            });
        }
        
        function register(event) {
            event.preventDefault();
            const username = document.getElementById('regUsername').value;
            const email = document.getElementById('regEmail').value;
            const password = document.getElementById('regPassword').value;
            
            fetch('/api/register', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({username, email, password})
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    alert('Account created successfully! Please login.');
                    showLogin();
                } else {
                    alert(data.message);
                }
            });
        }
        
        function logout() {
            fetch('/api/logout', {method: 'POST'})
                .then(() => {
                    currentUser = null;
                    isAdmin = false;
                    showLogin();
                });
        }
        
        function showLogin() {
            document.getElementById('loginForm').classList.remove('hidden');
            document.getElementById('registerForm').classList.add('hidden');
            document.getElementById('chatInterface').classList.add('hidden');
            document.getElementById('adminPanel').classList.add('hidden');
        }
        
        function showRegister() {
            document.getElementById('loginForm').classList.add('hidden');
            document.getElementById('registerForm').classList.remove('hidden');
            document.getElementById('chatInterface').classList.add('hidden');
            document.getElementById('adminPanel').classList.add('hidden');
        }
        
        function showChat() {
            document.getElementById('loginForm').classList.add('hidden');
            document.getElementById('registerForm').classList.add('hidden');
            document.getElementById('chatInterface').classList.remove('hidden');
            document.getElementById('adminPanel').classList.add('hidden');
            document.getElementById('currentUser').textContent = currentUser;
            
            if (isAdmin) {
                document.getElementById('adminBtn').style.display = 'block';
            }
        }
        
        function showAdmin() {
            if (!isAdmin) return;
            document.getElementById('adminPanel').classList.remove('hidden');
            document.getElementById('chatInterface').classList.add('hidden');
            loadAdminData();
        }
        
        function hideAdmin() {
            document.getElementById('adminPanel').classList.add('hidden');
            document.getElementById('chatInterface').classList.remove('hidden');
        }
        
        function setMessageType(type) {
            currentMessageType = type;
            
            // Update button states
            document.querySelectorAll('.type-btn').forEach(btn => btn.classList.remove('active'));
            event.target.classList.add('active');
            
            // Show/hide relevant inputs
            const messageInput = document.getElementById('messageInput');
            const urlInput = document.getElementById('urlInput');
            const fileBtn = document.getElementById('fileBtn');
            
            messageInput.classList.add('hidden');
            urlInput.classList.add('hidden');
            fileBtn.classList.add('hidden');
            
            if (type === 'text') {
                messageInput.classList.remove('hidden');
                messageInput.placeholder = 'Type your message...';
            } else if (type === 'image') {
                fileBtn.classList.remove('hidden');
            } else if (type === 'text+image') {
                messageInput.classList.remove('hidden');
                fileBtn.classList.remove('hidden');
                messageInput.placeholder = 'Type your message...';
            } else if (type === 'url') {
                messageInput.classList.remove('hidden');
                urlInput.classList.remove('hidden');
                messageInput.placeholder = 'Description (optional)...';
            }
        }
        
        function sendMessage() {
            const messageInput = document.getElementById('messageInput');
            const urlInput = document.getElementById('urlInput');
            const imageInput = document.getElementById('imageInput');
            
            const formData = new FormData();
            formData.append('message_type', currentMessageType);
            
            if (currentMessageType === 'text') {
                if (!messageInput.value.trim()) return;
                formData.append('content', messageInput.value.trim());
            } else if (currentMessageType === 'image') {
                if (!imageInput.files[0]) return;
                formData.append('image', imageInput.files[0]);
            } else if (currentMessageType === 'text+image') {
                if (!messageInput.value.trim() && !imageInput.files[0]) return;
                formData.append('content', messageInput.value.trim());
                if (imageInput.files[0]) {
                    formData.append('image', imageInput.files[0]);
                }
            } else if (currentMessageType === 'url') {
                if (!urlInput.value.trim()) return;
                formData.append('url', urlInput.value.trim());
                formData.append('content', messageInput.value.trim());
            }
            
            fetch('/api/send_message', {
                method: 'POST',
                body: formData
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    messageInput.value = '';
                    urlInput.value = '';
                    imageInput.value = '';
                    loadMessages();
                } else {
                    alert(data.message);
                }
            });
        }
        
        function loadMessages() {
            fetch('/api/messages')
                .then(response => response.json())
                .then(data => {
                    const messagesDiv = document.getElementById('messages');
                    messagesDiv.innerHTML = '';
                    
                    data.messages.forEach(message => {
                        const messageDiv = document.createElement('div');
                        messageDiv.className = 'message';
                        
                        let messageContent = `
                            <div class="message-header">
                                <span class="username">${message.username}</span>
                                <span>${new Date(message.timestamp).toLocaleString()}</span>
                            </div>
                            <div class="message-content">
                        `;
                        
                        if (message.content) {
                            messageContent += `<div>${message.content}</div>`;
                        }
                        
                        if (message.image_data) {
                            messageContent += `<img src="data:image/jpeg;base64,${message.image_data}" class="message-image" alt="Image">`;
                        }
                        
                        if (message.url) {
                            messageContent += `<a href="${message.url}" target="_blank" class="message-url">${message.url}</a>`;
                        }
                        
                        messageContent += `</div>`;
                        messageDiv.innerHTML = messageContent;
                        messagesDiv.appendChild(messageDiv);
                    });
                    
                    messagesDiv.scrollTop = messagesDiv.scrollHeight;
                });
        }
        
        function loadAdminData() {
            // Load current settings
            fetch('/api/admin/settings')
                .then(response => response.json())
                .then(data => {
                    document.getElementById('maxImageSize').value = Math.floor(data.max_image_size / 1024);
                });
            
            // Load users
            fetch('/api/admin/users')
                .then(response => response.json())
                .then(data => {
                    const usersList = document.getElementById('usersList');
                    usersList.innerHTML = '';
                    
                    data.users.forEach(user => {
                        const userDiv = document.createElement('div');
                        userDiv.className = 'user-item';
                        userDiv.innerHTML = `
                            <span>${user.username} (${user.email || 'No email'}) ${user.is_banned ? '[BANNED]' : ''}</span>
                            <div class="user-actions">
                                <button onclick="toggleBan(${user.id}, ${user.is_banned})" class="btn-warning">
                                    ${user.is_banned ? 'Unban' : 'Ban'}
                                </button>
                                <button onclick="deleteUser(${user.id})" class="btn-danger">Delete</button>
                            </div>
                        `;
                        usersList.appendChild(userDiv);
                    });
                });
        }
        
        function updateSettings() {
            const maxImageSize = document.getElementById('maxImageSize').value * 1024;
            
            fetch('/api/admin/update_settings', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({max_image_size: maxImageSize})
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    alert('Settings updated successfully!');
                } else {
                    alert('Error updating settings');
                }
            });
        }
        
        function toggleBan(userId, isBanned) {
            fetch('/api/admin/toggle_ban', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({user_id: userId, ban: !isBanned})
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    loadAdminData();
                } else {
                    alert('Error updating user status');
                }
            });
        }
        
        function deleteUser(userId) {
            if (confirm('Are you sure you want to delete this user?')) {
                fetch('/api/admin/delete_user', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({user_id: userId})
                })
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        loadAdminData();
                    } else {
                        alert('Error deleting user');
                    }
                });
            }
        }
        
        function deleteAllMessages() {
            if (confirm('Are you sure you want to delete ALL messages? This cannot be undone!')) {
                fetch('/api/admin/delete_all_messages', {
                    method: 'POST'
                })
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        alert('All messages deleted successfully!');
                        loadMessages();
                    } else {
                        alert('Error deleting messages');
                    }
                });
            }
        }
        
        // Allow Enter key to send messages
        document.addEventListener('keypress', function(e) {
            if (e.key === 'Enter' && (e.target.id === 'messageInput' || e.target.id === 'urlInput')) {
                sendMessage();
            }
        });
    </script>
</body>
</html>
'''

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/api/register', methods=['POST'])
def register():
    data = request.get_json()
    username = data.get('username', '').strip()
    email = data.get('email', '').strip()
    password = data.get('password', '')
    
    if not username or not password:
        return jsonify({'success': False, 'message': 'Username and password are required'})
    
    try:
        conn = get_db_connection()
        password_hash = hash_password(password)
        conn.execute('INSERT INTO users (username, password_hash, email) VALUES (?, ?, ?)', 
                    (username, password_hash, email if email else None))
        conn.commit()
        conn.close()
        return jsonify({'success': True})
    except sqlite3.IntegrityError:
        return jsonify({'success': False, 'message': 'Username already exists'})
    except Exception as e:
        return jsonify({'success': False, 'message': 'Registration failed'})

@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()
    username = data.get('username', '').strip()
    password = data.get('password', '')
    
    if not username or not password:
        return jsonify({'success': False, 'message': 'Username and password are required'})
    
    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
    conn.close()
    
    if user and user['password_hash'] == hash_password(password):
        if user['is_banned']:
            return jsonify({'success': False, 'message': 'Your account has been banned'})
        
        session['user_id'] = user['id']
        session['username'] = user['username']
        session['is_admin'] = user['is_admin']
        return jsonify({'success': True, 'is_admin': user['is_admin']})
    else:
        return jsonify({'success': False, 'message': 'Invalid username or password'})

@app.route('/api/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({'success': True})

@app.route('/api/check_login')
def check_login():
    if 'user_id' in session:
        return jsonify({
            'logged_in': True, 
            'username': session['username'],
            'is_admin': session.get('is_admin', False)
        })
    return jsonify({'logged_in': False})

@app.route('/api/send_message', methods=['POST'])
def send_message():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Not logged in'})
    
    message_type = request.form.get('message_type')
    content = request.form.get('content', '').strip()
    url = request.form.get('url', '').strip()
    image_data = None
    
    # Handle image upload
    if 'image' in request.files:
        image_file = request.files['image']
        if image_file and image_file.filename:
            # Check file size
            max_size = int(get_setting('max_image_size'))
            image_file.seek(0, 2)  # Seek to end
            file_size = image_file.tell()
            image_file.seek(0)  # Reset to beginning
            
            if file_size > max_size:
                return jsonify({'success': False, 'message': f'Image too large. Max size: {max_size/1024}KB'})
            
            # Convert to base64
            image_data = base64.b64encode(image_file.read()).decode('utf-8')
    
    # Validate message content
    if message_type == 'text' and not content:
        return jsonify({'success': False, 'message': 'Message content required'})
    elif message_type == 'image' and not image_data:
        return jsonify({'success': False, 'message': 'Image required'})
    elif message_type == 'url' and not url:
        return jsonify({'success': False, 'message': 'URL required'})
    elif message_type == 'text+image' and not content and not image_data:
        return jsonify({'success': False, 'message': 'Text or image required'})
    
    try:
        conn = get_db_connection()
        conn.execute('''
            INSERT INTO messages (user_id, username, message_type, content, image_data, url)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (session['user_id'], session['username'], message_type, content or None, image_data, url or None))
        conn.commit()
        conn.close()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'message': 'Failed to send message'})

@app.route('/api/messages')
def get_messages():
    if 'user_id' not in session:
        return jsonify({'messages': []})
    
    conn = get_db_connection()
    messages = conn.execute('''
        SELECT * FROM messages 
        ORDER BY timestamp DESC 
        LIMIT 50
    ''').fetchall()
    conn.close()
    
    messages_list = []
    for msg in reversed(messages):
        messages_list.append({
            'id': msg['id'],
            'username': msg['username'],
            'message_type': msg['message_type'],
            'content': msg['content'],
            'image_data': msg['image_data'],
            'url': msg['url'],
            'timestamp': msg['timestamp']
        })
    
    return jsonify({'messages': messages_list})

@app.route('/api/admin/settings')
def admin_get_settings():
    if 'user_id' not in session or not session.get('is_admin'):
        return jsonify({'error': 'Unauthorized'}), 403
    
    max_image_size = get_setting('max_image_size')
    return jsonify({
        'max_image_size': int(max_image_size) if max_image_size else 1024*1024
    })

@app.route('/api/admin/update_settings', methods=['POST'])
def admin_update_settings():
    if 'user_id' not in session or not session.get('is_admin'):
        return jsonify({'error': 'Unauthorized'}), 403
    
    data = request.get_json()
    max_image_size = data.get('max_image_size')
    
    if max_image_size:
        update_setting('max_image_size', str(max_image_size))
    
    return jsonify({'success': True})

@app.route('/api/admin/users')
def admin_get_users():
    if 'user_id' not in session or not session.get('is_admin'):
        return jsonify({'error': 'Unauthorized'}), 403
    
    conn = get_db_connection()
    users = conn.execute('SELECT id, username, email, created_at, is_banned, is_admin FROM users ORDER BY created_at DESC').fetchall()
    conn.close()
    
    users_list = []
    for user in users:
        users_list.append({
            'id': user['id'],
            'username': user['username'],
            'email': user['email'],
            'created_at': user['created_at'],
            'is_banned': user['is_banned'],
            'is_admin': user['is_admin']
        })
    
    return jsonify({'users': users_list})

@app.route('/api/admin/toggle_ban', methods=['POST'])
def admin_toggle_ban():
    if 'user_id' not in session or not session.get('is_admin'):
        return jsonify({'error': 'Unauthorized'}), 403
    
    data = request.get_json()
    user_id = data.get('user_id')
    ban = data.get('ban')
    
    try:
        conn = get_db_connection()
        conn.execute('UPDATE users SET is_banned = ? WHERE id = ?', (ban, user_id))
        conn.commit()
        conn.close()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/admin/delete_user', methods=['POST'])
def admin_delete_user():
    if 'user_id' not in session or not session.get('is_admin'):
        return jsonify({'error': 'Unauthorized'}), 403
    
    data = request.get_json()
    user_id = data.get('user_id')
    
    # Don't allow deleting admin user
    if user_id == session['user_id']:
        return jsonify({'success': False, 'message': 'Cannot delete your own account'})
    
    try:
        conn = get_db_connection()
        conn.execute('DELETE FROM messages WHERE user_id = ?', (user_id,))
        conn.execute('DELETE FROM users WHERE id = ?', (user_id,))
        conn.commit()
        conn.close()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/admin/delete_all_messages', methods=['POST'])
def admin_delete_all_messages():
    if 'user_id' not in session or not session.get('is_admin'):
        return jsonify({'error': 'Unauthorized'}), 403
    
    try:
        conn = get_db_connection()
        conn.execute('DELETE FROM messages')
        conn.commit()
        conn.close()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

if __name__ == '__main__':
    init_db()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
