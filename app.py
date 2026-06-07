from flask import Flask, render_template, request, redirect, url_for, flash, make_response
from flask_socketio import SocketIO, emit
from flask_login import LoginManager, login_user, login_required, logout_user, UserMixin, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from flask_sqlalchemy import SQLAlchemy
import random, string, smtplib
from email.mime.text import MIMEText

# -------------------------
# App Setup
# -------------------------
app = Flask(__name__)
app.config['SECRET_KEY'] = 'yoursecret'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.db'

db = SQLAlchemy(app)
socketio = SocketIO(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"

# -------------------------
# Helper Functions
# -------------------------
def generate_temp_password():
    chars = string.ascii_letters + string.digits
    temp = ''.join(random.choice(chars) for _ in range(14))
    return temp[:4] + "-" + temp[4:8] + "-" + temp[8:14]

def send_temp_password_email(to_email, temp_password):
    try:
        msg = MIMEText(
            f"Your temporary login password is:\n\n{temp_password}\n\n"
            "Use this to log in. You will be asked to set a permanent password."
        )
        msg["Subject"] = "Your Temporary Password"
        msg["From"] = "pahama.hannahshane@gmail.com"
        msg["To"] = to_email

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login("pahama.hannahshane@gmail.com", "zfcx nmpl tbxs xgqz")
            server.send_message(msg)

        return True

    except smtplib.SMTPAuthenticationError as e:
        if b"Username and Password not accepted" in e.smtp_error:
            return "real_password"
        return "auth_error"

    except Exception:
        return "send_error"

# -------------------------
# No‑Cache Decorator
# -------------------------
def nocache(view):
    def no_cache(*args, **kwargs):
        response = make_response(view(*args, **kwargs))
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response
    no_cache.__name__ = view.__name__
    return no_cache

# -------------------------
# Database Models
# -------------------------
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True)
    email = db.Column(db.String(120), unique=True)
    password = db.Column(db.String(200))
    temp_password = db.Column(db.String(50))
    is_verified = db.Column(db.Boolean, default=False)

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80))
    text = db.Column(db.String(500))

# -------------------------
# Login Manager
# -------------------------
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# -------------------------
# Routes
# -------------------------
@app.route('/')
@login_required
@nocache
def chat():
    messages = Message.query.all()
    return render_template('chat.html', messages=messages)

@app.route('/register', methods=['GET','POST'])
def register():
    if request.method == 'POST':

        if User.query.filter_by(username=request.form['username']).first():
            flash("Username already taken.")
            return redirect(url_for('register'))

        if User.query.filter_by(email=request.form['email']).first():
            flash("Email already registered.")
            return redirect(url_for('register'))

        temp_pass = generate_temp_password()

        new_user = User(
            username=request.form['username'],
            email=request.form['email'],
            temp_password=temp_pass,
            is_verified=False
        )

        db.session.add(new_user)
        db.session.commit()

        email_status = send_temp_password_email(new_user.email, temp_pass)

        if email_status == "real_password":
            flash("Google blocked the login. Use a 16‑digit Google App Password.")
            return redirect(url_for('register'))

        if email_status == "auth_error":
            flash("Your Gmail App Password is incorrect.")
            return redirect(url_for('register'))

        if email_status == "send_error":
            flash("Could not send temporary password email.")
            return redirect(url_for('register'))

        flash("A temporary password has been sent to your email.")
        return redirect(url_for('check_email'))

    return render_template('register.html')

@app.route('/check-email')
def check_email():
    return render_template('check_email.html')

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form['username']).first()

        if not user:
            flash("No account with that username.")
            return redirect(url_for('login'))

        entered = request.form['password']

        if user.temp_password and entered == user.temp_password:
            user.is_verified = True
            db.session.commit()
            login_user(user)
            return redirect(url_for('verify'))

        if user.password and check_password_hash(user.password, entered):
            login_user(user)
            return redirect(url_for('chat'))

        flash("Incorrect password.")
        return redirect(url_for('login'))

    return render_template('login.html')

@app.route('/verify', methods=['GET','POST'])
@login_required
def verify():
    if request.method == 'POST':
        new_pass = request.form['password']

        current_user.password = generate_password_hash(new_pass)
        current_user.temp_password = None
        db.session.commit()

        flash("Your password has been updated.")
        return redirect(url_for('chat'))

    return render_template('verify.html')

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('login'))

# -------------------------
# SocketIO Events
# -------------------------
@socketio.on('send_message')
def handle_message(data):
    with app.app_context():
        msg = Message(username=data['username'], text=data['text'])
        db.session.add(msg)
        db.session.commit()

    emit('receive_message', data, broadcast=True)

# -------------------------
# Run
# -------------------------
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    socketio.run(app, debug=True)
