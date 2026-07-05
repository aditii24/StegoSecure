import os, threading, time, base64
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_from_directory
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.utils import secure_filename

from config import Config
from models import db, User, Contact, Message, FileUpload, IntrusionLog
from auth_utils import hash_password, check_password, generate_totp_secret, get_totp_uri, generate_qr_base64, verify_totp
from crypto_utils import generate_rsa_keys, aes_encrypt, aes_decrypt, rsa_wrap_key, rsa_unwrap_key
from steg_utils import hide_message_in_image_file, extract_message_from_image_file
from file_utils import allowed_file, save_upload
from datetime import datetime, timedelta
import pytz
from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_OAEP, AES
import base64
from PIL import Image



def decrypt_message(msg):
    """Decrypts a message using the current user's private RSA key and AES-GCM."""
    try:
        if getattr(msg, "is_image", False):
            return None

        # Load private key
        private_key = RSA.import_key(current_user.rsa_private)

        # Pick correct wrapped AES key
        wrapped_key_b64 = (
            msg.wrapped_key if msg.receiver_id == current_user.id else msg.wrapped_key_sender
        )

        # Decode base64 fields
        wrapped_key = base64.b64decode(wrapped_key_b64)
        nonce = base64.b64decode(msg.nonce)
        ciphertext = base64.b64decode(msg.ciphertext)
        tag = base64.b64decode(msg.tag)

        # Unwrap AES key with RSA private key
        cipher_rsa = PKCS1_OAEP.new(private_key)
        aes_key = cipher_rsa.decrypt(wrapped_key)

        # Decrypt with AES-GCM (must include nonce)
        cipher_aes = AES.new(aes_key, AES.MODE_GCM, nonce=nonce)
        plaintext = cipher_aes.decrypt_and_verify(ciphertext, tag)

        return plaintext.decode(errors='ignore')

    except Exception as e:
        print(f"❌ Decrypt failed for message {msg.id}: {e}")
        return "[Decryption failed]"




IST = pytz.timezone("Asia/Kolkata")

# app init
app = Flask(__name__)
import os

# 📁 Folder to store uploaded stego files
UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

app.config.from_object(Config)
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

db.init_app(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def log_intrusion(user_id, ip, ua, success):
    entry = IntrusionLog(user_id=user_id, ip_address=ip, user_agent=ua, success=success)
    db.session.add(entry)
    db.session.commit()

@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/register', methods=['GET','POST'])
def register():
    if request.method == 'POST':
        username = request.form['username'].strip()
        email = request.form.get('email','').strip()
        password = request.form['password']
        if not username or not password:
            flash("Provide username and password", "danger")
            return redirect(url_for('register'))
        if User.query.filter_by(username=username).first():
            flash("Username already taken", "danger")
            return redirect(url_for('register'))
        priv, pub = generate_rsa_keys()
        totp_secret = generate_totp_secret()
        u = User(username=username, email=email or None, password_hash=hash_password(password),
                 totp_secret=totp_secret, rsa_private=priv, rsa_public=pub)
        db.session.add(u)
        db.session.commit()
        uri = get_totp_uri(totp_secret, username)
        qr_b64 = generate_qr_base64(uri)
        flash("Registered successfully. Scan the QR below into Google Authenticator or Authy.", "success")
        return render_template('register.html', qr_b64=qr_b64, totp_secret=totp_secret)
    return render_template('register.html')

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']
        token = request.form.get('token','').strip()
        user = User.query.filter_by(username=username).first()
        ip = request.remote_addr
        ua = request.headers.get('User-Agent')
        if not user:
            log_intrusion(None, ip, ua, False)
            flash("Invalid credentials", "danger"); return redirect(url_for('login'))
        if user.locked_until and user.locked_until > datetime.utcnow():
            flash("Account temporarily locked", "danger"); return redirect(url_for('login'))
        if check_password(password, user.password_hash) and verify_totp(user.totp_secret, token):
            login_user(user)
            user.failed_logins = 0
            db.session.commit()
            log_intrusion(user.id, ip, ua, True)
            return redirect(url_for('dashboard'))
        else:
            user.failed_logins = (user.failed_logins or 0) + 1
            if user.failed_logins >= 5:
                user.locked_until = datetime.utcnow() + timedelta(minutes=15)
            db.session.commit()
            log_intrusion(user.id, ip, ua, False)
            flash("Invalid username/password or 2FA token", "danger")
            return redirect(url_for('login'))
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    cs = Contact.query.filter_by(user_id=current_user.id).all()
    contacts = [User.query.get(c.contact_id) for c in cs]
    return render_template('dashboard.html', contacts=contacts)

@app.route('/add_contact', methods=['POST'])
@login_required
def add_contact():
    target = request.form['username'].strip()
    user = User.query.filter_by(username=target).first()
    if not user:
        flash("No such user", "danger"); return redirect(url_for('dashboard'))
    if not user.allow_contacts:
        flash("User does not accept contacts", "warning"); return redirect(url_for('dashboard'))
    if user.id == current_user.id:
        flash("Cannot add yourself", "warning"); return redirect(url_for('dashboard'))
    if Contact.query.filter_by(user_id=current_user.id, contact_id=user.id).first():
        flash("Already in contacts", "info"); return redirect(url_for('dashboard'))
    db.session.add(Contact(user_id=current_user.id, contact_id=user.id))
    db.session.commit()
    flash("Contact added", "success")
    return redirect(url_for('dashboard'))


@app.route('/toggle_privacy', methods=['POST'])
@login_required
def toggle_privacy():
    current_user.allow_contacts = not current_user.allow_contacts
    db.session.commit()
    flash("Privacy updated", "success")
    return redirect(url_for('dashboard'))

@app.route('/upload_file', methods=['POST'])
@login_required
def upload_file():
    if 'file' not in request.files:
        flash("No file uploaded", "danger")
        return redirect(url_for('dashboard'))

    f = request.files['file']
    receiver_id = int(request.form['receiver_id'])
    hide_text = request.form.get('hide_text', '').strip()

    if f.filename == '':
        flash("No selected file", "danger")
        return redirect(url_for('dashboard'))

    # Check file extension
    original_ext = f.filename.rsplit('.', 1)[-1].lower()
    filename = secure_filename(f.filename)
    save_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)

    # ✅ Convert JPG/JPEG to PNG
    if original_ext in ['jpg', 'jpeg']:
        from PIL import Image
        img = Image.open(f.stream).convert("RGBA")
        filename = filename.rsplit('.', 1)[0] + '.png'
        save_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        img.save(save_path, 'PNG')
        print(f"🖼️ Converted JPEG to PNG: {filename}")
    else:
        f.save(save_path)

    # If image and hide_text is provided → hide the message
    if original_ext in ('png', 'jpg', 'jpeg') and hide_text:
        out = os.path.join(app.config['UPLOAD_FOLDER'], 'stego_' + filename)
        hide_message_in_image_file(save_path, hide_text, out)
        os.remove(save_path)
        filename = 'stego_' + filename
        save_path = out
        print(f"🔐 Hidden message embedded in image: {filename}")

    # Store FileUpload record in DB
    file_record = FileUpload(
        filename=filename,
        original_name=f.filename,
        sender_id=current_user.id,
        receiver_id=receiver_id
    )
    db.session.add(file_record)
    db.session.commit()

    # Create message record (so image appears in chat)
    msg = Message(
        sender_id=current_user.id,
        receiver_id=receiver_id,
        ciphertext=filename,
        wrapped_key='',
        wrapped_key_sender='',
        nonce='',
        is_image=True
    )
    db.session.add(msg)
    db.session.commit()

    flash("File uploaded successfully", "success")
    return redirect(url_for('dashboard'))


@app.route('/uploads/<filename>')
def uploaded_file(filename):
    # Serve files from the actual uploads folder
    return send_from_directory(os.path.join(os.getcwd(), 'uploads'), filename)

@app.route('/extract_stego_by_filename', methods=['POST'])
@login_required
def extract_stego_by_filename():
    """
    Extracts hidden message from an uploaded image file (called by chat.js).
    Expects JSON: { "filename": "stego_image.png" }
    Returns JSON with { status, message }.
    """
    try:
        data = request.get_json()
        if not data or 'filename' not in data:
            return jsonify({"status": "error", "message": "Filename missing"}), 400

        filename = data['filename']
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)

        if not os.path.exists(file_path):
            return jsonify({"status": "error", "message": "File not found"}), 404

        # 🧠 Try extracting hidden message
        from steg_utils import extract_message_from_image_file
        hidden_msg = extract_message_from_image_file(file_path)

        if hidden_msg:
            print(f"🔍 Hidden message extracted from {filename}: {hidden_msg}")
            return jsonify({"status": "ok", "message": hidden_msg})
        else:
            print(f"ℹ️ No hidden message found in {filename}")
            return jsonify({"status": "ok", "message": None})

    except Exception as e:
        print(f"❌ Stego extraction error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500




@app.route('/extract_stego', methods=['POST'])
@login_required
def extract_stego():
    if 'image' not in request.files:
        flash("No image", "danger"); return redirect(url_for('dashboard'))
    img = request.files['image']
    path = os.path.join(app.config['UPLOAD_FOLDER'], 'temp_'+secure_filename(img.filename))
    img.save(path)
    try:
        msg = extract_message_from_image_file(path)
        if msg:
            flash(f"Hidden message: {msg}", "info")
        else:
            flash("No hidden message found", "warning")
    except Exception:
        flash("Error extracting message", "danger")
    os.remove(path)
    return redirect(url_for('dashboard'))

@app.route('/send_message', methods=['POST'])
@login_required
def send_message():
    print("\n=== 📩 SEND MESSAGE START ===")

    receiver_id = int(request.form.get('receiver_id'))
    text = request.form.get('text', '').strip()
    print("🧠 DEBUG /send_message FORM KEYS:", list(request.form.keys()))
    print(f"📨 Raw text received: '{text}'")
    destruct_option = request.form.get('self_destruct')
    receiver = User.query.get(receiver_id)

    if not receiver:
        return jsonify({"error": "Receiver not found"}), 404

    # Generate AES key
    aes_key = os.urandom(32)

    # Wrap AES key for both sender and receiver
    receiver_pub = RSA.import_key(receiver.rsa_public)
    sender_pub = RSA.import_key(current_user.rsa_public)
    wrapped_receiver = PKCS1_OAEP.new(receiver_pub).encrypt(aes_key)
    wrapped_sender = PKCS1_OAEP.new(sender_pub).encrypt(aes_key)

    # 🔐 Encrypt the message text using AES-GCM
    cipher_aes = AES.new(aes_key, AES.MODE_GCM)
    ciphertext, tag = cipher_aes.encrypt_and_digest(text.encode())

    # Optional self-destruct timer
    # Optional self-destruct timer
    self_destruct_at = None
    if destruct_option in ('10s', '10', '10sec'):
        self_destruct_at = datetime.now(IST) + timedelta(seconds=10)
    elif destruct_option == '1m':
        self_destruct_at = datetime.now(IST) + timedelta(minutes=1)
    elif destruct_option == '5m':
        self_destruct_at = datetime.now(IST) + timedelta(minutes=5)

    print(f"🕒 Self-destruct option: {destruct_option}, set for {self_destruct_at}")


    # 📨 Save message
    message = Message(
        sender_id=current_user.id,
        receiver_id=receiver.id,
        ciphertext=base64.b64encode(ciphertext).decode(),
        nonce=base64.b64encode(cipher_aes.nonce).decode(),
        tag=base64.b64encode(tag).decode(),
        wrapped_key=base64.b64encode(wrapped_receiver).decode(),
        wrapped_key_sender=base64.b64encode(wrapped_sender).decode(),
        is_image=False,
        self_destruct_at=self_destruct_at
    )

    db.session.add(message)
    db.session.commit()

    print(f"✅ Message committed successfully: {message.id}")
    print("=== ✅ SEND MESSAGE END ===\n")

    return jsonify({"success": True})



@app.route('/messages/<int:contact_id>')
@login_required
def get_messages(contact_id):
    messages = Message.query.filter(
        ((Message.sender_id == current_user.id) & (Message.receiver_id == contact_id)) |
        ((Message.sender_id == contact_id) & (Message.receiver_id == current_user.id))
    ).order_by(Message.timestamp.asc()).all()

    response = []
    for m in messages:
        try:
            # ✅ Normalize the is_image flag to boolean
            is_img = str(m.is_image).lower() in ("true", "1", "yes")

            if is_img:
                response.append({
                    "id": m.id,
                    "from": m.sender_id,
                    "to": m.receiver_id,
                    "is_image": True,
                    "file_url": f"/uploads/{m.ciphertext}",
                    "text": None,
                    "self_destruct_at": (
                        m.self_destruct_at.isoformat() if m.self_destruct_at else None
                    ),
                })
                continue  # ⛔ Skip decryption completely

            # 🔐 Only decrypt non-image messages
            text = decrypt_message(m)

        except Exception as e:
            print(f"❌ Decrypt failed for message {getattr(m, 'id', '?')}: {e}")
            text = "[Decryption failed]"

        response.append({
            "id": m.id,
            "from": m.sender_id,
            "to": m.receiver_id,
            "is_image": False,
            "file_url": None,
            "text": text,
            "self_destruct_at": (
                m.self_destruct_at.isoformat() if m.self_destruct_at else None
            ),
        })

    print("=== 🧩 JSON Sent to Frontend ===")
    from pprint import pprint
    pprint(response)
    print("================================")

    return jsonify(response)



@app.route('/logs')
@login_required
def logs():
    logs = IntrusionLog.query.order_by(IntrusionLog.timestamp.desc()).limit(200).all()
    return render_template('logs.html', logs=logs)

def cleanup_loop():
    """Background thread that deletes self-destructed messages every few seconds."""
    with app.app_context():
        while True:
            try:
                now = datetime.now(IST)
                expired = Message.query.filter(
                    Message.self_destruct_at != None,
                    Message.self_destruct_at <= now
                ).all()

                # 🧩 Debug logs — you'll see these every 5 seconds
                if expired:
                    print(f"🧨 Cleaning up {len(expired)} expired messages at {now}")
                    for m in expired:
                        db.session.delete(m)
                    db.session.commit()
                else:
                    print(f"⏳ No expired messages at {now}")

                time.sleep(5)

            except Exception as e:
                print("⚠️ Cleanup error:", e)
                time.sleep(10)


if __name__ == '__main__':
    from models import User, Contact, Message, FileUpload, IntrusionLog  # <-- force table registration

    with app.app_context():
        print("🔄 Creating all tables...")
        db.drop_all()       # optional safety: clear any partial tables
        db.create_all()
        print("✅ Database tables created successfully!")

    # Start cleanup thread AFTER tables are ready
    cleanup_thread = threading.Thread(target=cleanup_loop, daemon=True)
    cleanup_thread.start()

    app.run(host='127.0.0.1', port=5000, debug=True)
