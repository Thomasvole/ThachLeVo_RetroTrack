from flask import Flask, render_template, redirect, url_for, flash, session, request
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField
from wtforms.validators import DataRequired, EqualTo, ValidationError
from werkzeug.utils import secure_filename
import os
import re
from datetime import datetime

# Initialize Flask app
app = Flask(__name__)

# Configuration
app.config['SECRET_KEY'] = 'a_very_secret_key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///site.db'
app.config['UPLOAD_FOLDER'] = 'uploads/'  # Directory for uploaded files
app.config['ALLOWED_EXTENSIONS'] = {'pdf', 'doc', 'docx', 'xls', 'xlsx'}

# Ensure upload folder exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Initialize extensions
db = SQLAlchemy(app)
bcrypt = Bcrypt(app)


# Database Models
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(100), nullable=False)
    last_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(60), nullable=False)
    files = db.relationship('File', backref='uploader', lazy=True)  # Relationship to File model

    def __repr__(self):
        return f"User('{self.email}')"


class File(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False)
    upload_date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    def __repr__(self):
        return f"File('{self.filename}', Uploaded by User ID: {self.user_id})"


# Custom Email Validation
def validate_email(form, field):
    email = field.data
    email_regex = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if not re.match(email_regex, email):
        raise ValidationError('Invalid email address.')


# Forms
class RegistrationForm(FlaskForm):
    first_name = StringField('First Name', validators=[DataRequired()])
    last_name = StringField('Last Name', validators=[DataRequired()])
    email = StringField('Email', validators=[DataRequired(), validate_email])
    password = PasswordField('Password', validators=[DataRequired()])
    confirm_password = PasswordField('Confirm Password', validators=[DataRequired(), EqualTo('password')])
    submit = SubmitField('Register')

    def validate_email(self, email):
        user = User.query.filter_by(email=email.data).first()
        if user:
            raise ValidationError('That email is already registered.')


class LoginForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), validate_email])
    password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('Login')


# Helper Functions
def allowed_file(filename):
    """Check if the uploaded file has an allowed extension."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']


# Routes
@app.route('/')
@app.route('/home')
def home():
    return render_template('homepage.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    form = RegistrationForm()
    if form.validate_on_submit():
        hashed_password = bcrypt.generate_password_hash(form.password.data).decode('utf-8')
        user = User(first_name=form.first_name.data, last_name=form.last_name.data, email=form.email.data,
                    password=hashed_password)
        db.session.add(user)
        db.session.commit()
        flash('Your account has been created! You can now log in.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html', form=form)


@app.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user and bcrypt.check_password_hash(user.password, form.password.data):
            session['user_id'] = user.id
            session['user_name'] = f"{user.first_name} {user.last_name}"
            session['user_email'] = user.email
            flash('Login successful!', 'success')
            return redirect(url_for('home'))
        else:
            flash('Login unsuccessful. Please check your credentials.', 'danger')
    return render_template('login.html', form=form)


@app.route('/upload', methods=['GET', 'POST'])
def upload():
    if 'user_id' not in session:
        flash('You must be logged in to upload files.', 'danger')
        return redirect(url_for('login'))

    if request.method == 'POST':
        if 'file' not in request.files:
            flash('No file part in the request.', 'danger')
            return redirect(request.url)

        file = request.files['file']

        if file.filename == '':
            flash('No file selected.', 'danger')
            return redirect(request.url)

        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))

            # Save file metadata to the database
            uploaded_file = File(filename=filename, user_id=session['user_id'])
            db.session.add(uploaded_file)
            db.session.commit()

            flash('File uploaded successfully!', 'success')
            return redirect(url_for('upload'))
        else:
            flash('Invalid file type. Only PDF, Word, and Excel files are allowed.', 'danger')

    return render_template('upload.html')


@app.route('/profile')
def profile():
    if 'user_id' not in session:
        flash('Please log in to access your profile.', 'danger')
        return redirect(url_for('login'))
    return render_template('profile.html', user=session)


# Run the app
if __name__ == '__main__':
    app.run(debug=True)



@app.route('/logout')
def logout():
    session.clear()  # Clear all session data
    flash('You have been logged out.', 'success')
    return redirect(url_for('home'))


# Run the app
if __name__ == '__main__':
    app.run(debug=True)
