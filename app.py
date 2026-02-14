from flask import Flask, render_template, request, redirect, session, jsonify, send_from_directory
from flask_socketio import SocketIO, join_room, emit
from flask_mail import Mail, Message
import mysql.connector, random, string, hashlib, os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY")
socketio = SocketIO(app, cors_allowed_origins="*")

# ---------------- DATABASE HELPER ----------------
def get_db():
    return mysql.connector.connect(
        host=os.getenv("DB_HOST"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME"),
        autocommit=True
    )

# ---------------- MAIL ----------------
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USERNAME'] = os.getenv("MAIL_USERNAME")
app.config['MAIL_PASSWORD'] = os.getenv("MAIL_PASSWORD")
app.config['MAIL_USE_TLS'] = True
mail = Mail(app)

# ---------------- HELPERS ----------------
def hash_pass(password):
    return hashlib.sha256(password.encode()).hexdigest()

def send_otp(email):
    otp = ''.join(random.choices(string.digits, k=6))
    msg = Message("Your VeloApp OTP",
                  sender=app.config['MAIL_USERNAME'],
                  recipients=[email])
    msg.body = f"Your OTP is {otp}"
    mail.send(msg)
    return otp

def get_room_name(user1, user2):
    return f"chat_{min(user1, user2)}_{max(user1, user2)}"

# ---------------- GOOGLE VERIFICATION ----------------
@app.route('/google<verification_id>.html')
def google_verify(verification_id):
    filename = f"google{verification_id}.html"
    return send_from_directory('.', filename)

# ---------------- ROUTES ----------------
@app.route('/')
def index():
    return redirect('/login')

# -------- Auth Page (Login + Register) --------
@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST' and 'phone' in request.form:
        # Login form submitted
        db = get_db()
        cursor = db.cursor(dictionary=True)

        phone = request.form.get('phone')
        password = hash_pass(request.form.get('password'))

        cursor.execute("""
            SELECT * FROM users 
            WHERE phone_number=%s AND password=%s
        """, (phone, password))

        user = cursor.fetchone()
        cursor.close()
        db.close()

        if user:
            session['user_id'] = user['id']
            return redirect('/chat')

        return "Invalid login"

    # GET request → render combined auth page
    return render_template('auth.html')

@app.route('/register', methods=['POST'])
def register():
    # Register form submitted
    db = get_db()
    cursor = db.cursor(dictionary=True)

    username = request.form.get('username')
    phone = request.form.get('phone')
    email = request.form.get('email')
    password = hash_pass(request.form.get('password'))

    cursor.execute("SELECT * FROM users WHERE email=%s OR phone_number=%s",
                   (email, phone))
    if cursor.fetchone():
        cursor.close()
        db.close()
        return "User already exists!"

    otp = send_otp(email)
    session['otp'] = otp
    session['reg_data'] = {
        'username': username,
        'phone': phone,
        'email': email,
        'password': password
    }

    cursor.close()
    db.close()
    return redirect('/verify')

# -------- Verify OTP --------
@app.route('/verify', methods=['GET','POST'])
def verify():
    if request.method == 'POST':
        if request.form['otp'] == session.get('otp'):
            db = get_db()
            cursor = db.cursor()

            data = session.pop('reg_data')
            cursor.execute("""
                INSERT INTO users (username, phone_number, email, password, verified)
                VALUES (%s,%s,%s,%s,1)
            """, (data['username'], data['phone'],
                  data['email'], data['password']))

            cursor.close()
            db.close()
            return redirect('/login')

        return "Invalid OTP"

    return render_template('verify.html')

# -------- Chat Page --------
@app.route('/chat')
def chat():
    if not session.get('user_id'):
        return redirect('/login')
    return render_template('chat.html', my_id=session.get('user_id'))

# -------- Search Users --------
@app.route('/search_users')
def search_users():
    query = request.args.get('q', '')
    my_id = session.get('user_id')

    db = get_db()
    cursor = db.cursor(dictionary=True)

    cursor.execute("""
        SELECT id, username 
        FROM users
        WHERE username LIKE %s
        AND id != %s
        LIMIT 20
    """, (query + "%", my_id))

    users = cursor.fetchall()
    cursor.close()
    db.close()

    return jsonify(users)

# -------- Recent Chats --------
@app.route('/recent_chats')
def recent_chats():
    my_id = session.get('user_id')

    db = get_db()
    cursor = db.cursor(dictionary=True)

    cursor.execute("""
        SELECT u.id, u.username, m.message, m.timestamp
        FROM messages m
        JOIN users u 
          ON u.id = IF(m.sender_id=%s, m.receiver_id, m.sender_id)
        WHERE m.sender_id=%s OR m.receiver_id=%s
        ORDER BY m.timestamp DESC
    """, (my_id, my_id, my_id))

    rows = cursor.fetchall()
    seen = set()
    recent = []
    for row in rows:
        if row['id'] not in seen:
            seen.add(row['id'])
            recent.append(row)

    cursor.close()
    db.close()
    return jsonify(recent)

# -------- Load Messages --------
@app.route('/messages/<int:other_id>')
def get_messages(other_id):
    my_id = session.get('user_id')

    db = get_db()
    cursor = db.cursor(dictionary=True)

    cursor.execute("""
        SELECT * FROM messages 
        WHERE (sender_id=%s AND receiver_id=%s)
        OR (sender_id=%s AND receiver_id=%s)
        ORDER BY timestamp
    """, (my_id, other_id, other_id, my_id))

    messages = cursor.fetchall()
    cursor.close()
    db.close()
    return jsonify(messages)

# -------- SOCKET --------
@socketio.on('connect')
def on_connect():
    if session.get('user_id'):
        join_room(str(session.get('user_id')))

@socketio.on('join')
def handle_join(data):
    join_room(data['room'])

@socketio.on('send_message')
def handle_message(data):
    sender = int(data['sender'])
    receiver = int(data['receiver'])
    msg = data['message']

    db = get_db()
    cursor = db.cursor()

    cursor.execute("""
        INSERT INTO messages (sender_id, receiver_id, message)
        VALUES (%s,%s,%s)
    """, (sender, receiver, msg))

    cursor.close()
    db.close()

    room = get_room_name(sender, receiver)
    emit('receive_message', data, room=room)
    emit('update_recents', room=str(sender))
    emit('update_recents', room=str(receiver))

# -------- RUN --------
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    socketio.run(app, host='0.0.0.0', port=port, debug=True)
