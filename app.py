from flask import Flask, render_template, redirect, url_for, flash, session, request
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField
from wtforms.validators import DataRequired, EqualTo, ValidationError
from werkzeug.utils import secure_filename
from PyPDF2 import PdfReader
from docx import Document
import pandas as pd
import os
from datetime import datetime

# Initialize Flask app
app = Flask(__name__)

# Configuration
app.config['SECRET_KEY'] = 'a_very_secret_key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///site.db'
app.config['UPLOAD_FOLDER'] = 'uploads/'
app.config['ALLOWED_EXTENSIONS'] = {'pdf', 'doc', 'docx', 'xls', 'xlsx'}
app.config['SESSION_COOKIE_SECURE'] = True
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

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
    files = db.relationship('File', backref='uploader', lazy=True)

    def __repr__(self):
        return f"User('{self.email}')"

class File(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False)
    upload_date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    size = db.Column(db.Float, nullable=False)  # File size in KB
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    parsed_data = db.Column(db.Text, nullable=True)  # Store parsed data as JSON or string

    def __repr__(self):
        return f"File('{self.filename}', Uploaded by User ID: {self.user_id}')"

# Forms
class RegistrationForm(FlaskForm):
    first_name = StringField('First Name', validators=[DataRequired()])
    last_name = StringField('Last Name', validators=[DataRequired()])
    email = StringField('Email', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    confirm_password = PasswordField('Confirm Password', validators=[DataRequired(), EqualTo('password')])
    submit = SubmitField('Register')

class LoginForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('Login')

class ProfileEditForm(FlaskForm):
    first_name = StringField('First Name', validators=[DataRequired()])
    last_name = StringField('Last Name', validators=[DataRequired()])
    submit = SubmitField('Save Changes')

# Helper Functions
def allowed_file(filename):
    """Check if the uploaded file has an allowed extension."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def parse_file(file_path, filename):
    """Parse uploaded file based on its extension."""
    ext = filename.rsplit('.', 1)[1].lower()
    if ext == 'pdf':
        return parse_pdf(file_path)
    elif ext in ['doc', 'docx']:
        return parse_word(file_path)
    elif ext in ['xls', 'xlsx']:
        return parse_excel(file_path)
    else:
        raise ValueError("Unsupported file type.")

def parse_pdf(file_path):
    """Extract text from a PDF file."""
    extracted_text = []
    try:
        reader = PdfReader(file_path)
        for page in reader.pages:
            extracted_text.append(page.extract_text())
        return extracted_text
    except Exception as e:
        print(f"Error processing PDF: {e}")
        raise e

def parse_word(file_path):
    """Extract text from a Word document."""
    try:
        document = Document(file_path)
        extracted_text = [para.text for para in document.paragraphs if para.text.strip()]
        return extracted_text
    except Exception as e:
        print(f"Error processing Word document: {e}")
        raise e

def parse_excel(file_path):
    """Extract relevant data from an Excel file."""
    try:
        excel_data = pd.ExcelFile(file_path)
        parsed_data = {}
        if "Summary" in excel_data.sheet_names:
            summary = excel_data.parse("Summary", skiprows=3)
            summary_cleaned = summary[["Row Labels", "CTH", "HCM", "HNI", "Grand Total"]].dropna(subset=["Row Labels"])
            parsed_data["regional_costs"] = summary_cleaned.to_dict(orient="records")
        if "BANG KE CHI TIET" in excel_data.sheet_names:
            details = excel_data.parse("BANG KE CHI TIET")
            details["NGÀY ĐH"] = pd.to_datetime(details["NGÀY ĐH"], errors="coerce")
            details["NGÀY CHI"] = pd.to_datetime(details["NGÀY CHI"], errors="coerce")
            details["Delay (Days)"] = (details["NGÀY CHI"] - details["NGÀY ĐH"]).dt.days
            parsed_data["inefficiencies"] = details[details["Delay (Days)"] > 0].to_dict(orient="records")
        return parsed_data
    except Exception as e:
        print(f"Error processing Excel file: {e}")
        raise e

# Define a context processor to pass 'now' to all templates
@app.context_processor
def inject_datetime():
    """Inject the current datetime into all templates."""
    return {'now': datetime.utcnow()}

@app.route('/')
@app.route('/home')
def home():
    """Home route."""
    user = None  # Default user as None
    if 'user_id' in session:  # Check if a user is logged in
        user = User.query.get(session['user_id'])  # Fetch user from the database
    now = datetime.utcnow()  # Get the current UTC datetime
    return render_template('homepage.html', user=user, now=now)

@app.route('/register', methods=['GET', 'POST'])
def register():
    """User registration route."""
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
    """User login route."""
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
            flash('Login unsuccessful. Please check your email and password.', 'danger')
    return render_template('login.html', form=form)

@app.route('/upload', methods=['GET', 'POST'])
def upload():
    """File upload route."""
    if 'user_id' not in session:
        flash('You must be logged in to upload files.', 'danger')
        return redirect(url_for('login'))

    if request.method == 'POST':
        file = request.files['file']
        if file.filename == '':
            flash('No file selected.', 'danger')
            return redirect(request.url)
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(file_path)
            file_size_kb = os.path.getsize(file_path) / 1024.0
            try:
                parsed_data = parse_file(file_path, filename)
                new_file = File(
                    filename=filename,
                    size=file_size_kb,
                    user_id=session['user_id'],
                    parsed_data=str(parsed_data)
                )
                db.session.add(new_file)
                db.session.commit()
                flash('File uploaded and parsed successfully!', 'success')
            except Exception as e:
                flash('An error occurred while processing the file.', 'danger')
                print(f"Error: {e}")
            finally:
                os.remove(file_path)
            return redirect(url_for('view_files'))
    return render_template('upload.html')


@app.route('/files')
def view_files():
    if 'user_id' not in session:
        flash('You need to log in to view files.', 'danger')
        return redirect(url_for('login'))

    print(f"Session User ID: {session.get('user_id')}")
    user_files = File.query.filter_by(user_id=session['user_id']).all()
    print(f"User Files: {user_files}")

    return render_template('files.html', files=user_files)

@app.route('/delete-file/<int:file_id>', methods=['POST'])
def delete_file(file_id):
    """Delete a file."""
    file = File.query.get_or_404(file_id)
    if file.user_id != session['user_id']:
        flash('Unauthorized action.', 'danger')
        return redirect(url_for('view_files'))
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
    if os.path.exists(file_path):
        os.remove(file_path)
    db.session.delete(file)
    db.session.commit()
    flash('File deleted successfully!', 'success')
    return redirect(url_for('view_files'))

@app.route('/profile')
def profile():
    """User profile route."""
    if 'user_id' not in session:
        flash('You need to log in to access your profile.', 'danger')
        return redirect(url_for('login'))
    user = User.query.get(session['user_id'])
    if not user:
        flash('User not found.', 'danger')
        return redirect(url_for('logout'))
    return render_template('profile.html', user=user)

@app.route('/edit-profile', methods=['GET', 'POST'])
def edit_profile():
    """Edit profile route."""
    if 'user_id' not in session:
        flash('You need to log in to edit your profile.', 'danger')
        return redirect(url_for('login'))
    user = User.query.get(session['user_id'])
    if not user:
        flash('User not found.', 'danger')
        return redirect(url_for('logout'))
    form = ProfileEditForm(obj=user)
    if form.validate_on_submit():
        user.first_name = form.first_name.data
        user.last_name = form.last_name.data
        db.session.commit()
        flash('Your profile has been updated successfully!', 'success')
        return redirect(url_for('profile'))
    return render_template('edit_profile.html', form=form, user=user)

@app.route('/logout')
def logout():
    """User logout route."""
    session.clear()
    flash('You have been logged out.', 'success')
    return redirect(url_for('home'))

if __name__ == '__main__':
   with app.app_context():
     db.create_all()
   app.run(debug=True)
