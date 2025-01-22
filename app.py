"""
app.py - Full code with the modifications to store ALL Excel data in ExcelRow, plus existing logic.
"""

from flask import Flask, render_template, redirect, url_for, flash, session, request
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField
from wtforms.validators import DataRequired, EqualTo
from werkzeug.utils import secure_filename
from PyPDF2 import PdfReader
from docx import Document
import pandas as pd
import os
from datetime import datetime
import json  # for storing row data as JSON
import random  # used for mock route optimization data

# --------------------------------------------------------------------
# Initialize Flask app
# --------------------------------------------------------------------
app = Flask(__name__)

# --------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------
app.config['SECRET_KEY'] = 'a_very_secret_key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///site.db'

# Where uploaded files are temporarily stored
app.config['UPLOAD_FOLDER'] = 'uploads/'

# Allowed file extensions
app.config['ALLOWED_EXTENSIONS'] = {'pdf', 'doc', 'docx', 'xls', 'xlsx'}

# Set security flags for session cookies
app.config['SESSION_COOKIE_SECURE'] = True
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

# Ensure upload folder exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# --------------------------------------------------------------------
# Initialize extensions
# --------------------------------------------------------------------
db = SQLAlchemy(app)
bcrypt = Bcrypt(app)


# --------------------------------------------------------------------
# Database Models
# --------------------------------------------------------------------
class User(db.Model):
    """
    Represents a user in the system, who can upload files
    and manage their own data.
    """
    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(100), nullable=False)
    last_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(60), nullable=False)
    files = db.relationship('File', backref='uploader', lazy=True)

    def __repr__(self):
        return f"User('{self.email}')"


class File(db.Model):
    """
    Represents a file that was uploaded by a user.
    We store filename, date/time, size (KB), reference to the user,
    and optional parsed data (for PDF, DOC, XLS).
    """
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False)
    upload_date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    size = db.Column(db.Float, nullable=False)  # File size in KB
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    parsed_data = db.Column(db.Text, nullable=True)  # JSON or string representation of parsed data

    def __repr__(self):
        return f"File('{self.filename}', Uploaded by User ID: {self.user_id})"


class SummaryData(db.Model):
    """
    For Excel files, we store data from the "Summary" sheet in this table.
    """
    id = db.Column(db.Integer, primary_key=True)
    file_id = db.Column(db.Integer, db.ForeignKey('file.id'), nullable=False)
    row_labels = db.Column(db.String(255), nullable=False)
    cth = db.Column(db.Float, nullable=True)
    hcm = db.Column(db.Float, nullable=True)
    hni = db.Column(db.Float, nullable=True)
    grand_total = db.Column(db.Float, nullable=True)

    def __repr__(self):
        return f"SummaryData(FileID={self.file_id}, RowLabels={self.row_labels})"


class DetailData(db.Model):
    """
    For Excel files, we store data from the "BANG KE CHI TIET" sheet in this table.
    It also calculates the delay_days from NGÀY ĐH to NGÀY CHI.
    """
    id = db.Column(db.Integer, primary_key=True)
    file_id = db.Column(db.Integer, db.ForeignKey('file.id'), nullable=False)
    ngay_dh = db.Column(db.DateTime, nullable=True)
    ngay_chi = db.Column(db.DateTime, nullable=True)
    delay_days = db.Column(db.Integer, nullable=True)

    def __repr__(self):
        return f"DetailData(FileID={self.file_id}, DelayDays={self.delay_days})"


class ExcelRow(db.Model):
    """
    A generic storage model that keeps all rows from all sheets of an Excel file.
    Each row is stored in JSON format, so you can reconstruct or display it later.
    """
    id = db.Column(db.Integer, primary_key=True)
    file_id = db.Column(db.Integer, db.ForeignKey('file.id'), nullable=False)
    sheet_name = db.Column(db.String(255), nullable=False)     # Name of the Excel sheet
    row_index = db.Column(db.Integer, nullable=False)          # The row index in that sheet
    row_data = db.Column(db.Text, nullable=False)              # JSON string of the row's data

    def __repr__(self):
        return f"ExcelRow(FileID={self.file_id}, Sheet={self.sheet_name}, RowIndex={self.row_index})"


# --------------------------------------------------------------------
# Forms
# --------------------------------------------------------------------
class RegistrationForm(FlaskForm):
    """
    Form for user registration.
    """
    first_name = StringField('First Name', validators=[DataRequired()])
    last_name = StringField('Last Name', validators=[DataRequired()])
    email = StringField('Email', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    confirm_password = PasswordField('Confirm Password',
                                     validators=[DataRequired(), EqualTo('password')])
    submit = SubmitField('Register')


class LoginForm(FlaskForm):
    """
    Form for user login.
    """
    email = StringField('Email', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('Login')


class ProfileEditForm(FlaskForm):
    """
    Form for editing user profile.
    """
    first_name = StringField('First Name', validators=[DataRequired()])
    last_name = StringField('Last Name', validators=[DataRequired()])
    submit = SubmitField('Save Changes')


# --------------------------------------------------------------------
# Helper Functions
# --------------------------------------------------------------------
def allowed_file(filename):
    """
    Check if the uploaded file has an allowed extension.
    """
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']


def parse_file(file_path, filename):
    """
    Parse uploaded file based on its extension.
    Supported: PDF, Word (doc/docx), Excel (xls/xlsx).
    Returns a dictionary or list of extracted data.
    """
    ext = filename.rsplit('.', 1)[1].lower()
    if ext == 'pdf':
        return parse_pdf(file_path)
    elif ext in ['doc', 'docx']:
        return parse_word(file_path)
    elif ext in ['xls', 'xlsx']:
        # If we call parse_excel here without a file_id, we won't store everything
        # in ExcelRow. If we want all data stored, we do that after we have file_id.
        # We'll simply parse & return specialized data from "Summary" & "BANG KE CHI TIET".
        return parse_excel(file_path)
    else:
        raise ValueError("Unsupported file type.")


def parse_pdf(file_path):
    """
    Extract text from a PDF file as a list of page texts.
    """
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
    """
    Extract text from a Word document as a list of paragraphs.
    """
    try:
        document = Document(file_path)
        extracted_text = [para.text for para in document.paragraphs if para.text.strip()]
        return extracted_text
    except Exception as e:
        print(f"Error processing Word document: {e}")
        raise e


def parse_excel(file_path, file_id=None):
    """
    Extract data from *all* sheets in the Excel file. If file_id is provided,
    store each row of each sheet in ExcelRow. Also, return a dict:
        {
          'summary_data': [...],
          'detail_data': [...]
        }
    for specialized logic on "Summary" & "BANG KE CHI TIET".
    """
    try:
        excel_data = pd.ExcelFile(file_path)
        parsed_data = {
            'summary_data': [],
            'detail_data': []
        }

        # Go through each sheet in the workbook
        for sheet_name in excel_data.sheet_names:
            # Parse sheet into a DataFrame
            df = excel_data.parse(sheet_name)

            # If we want to store in ExcelRow table, do it row-by-row
            if file_id:
                for idx, row in df.iterrows():
                    row_dict = row.to_dict()  # Convert the row to a dictionary
                    # Convert to JSON string, skipping NaN or null items:
                    row_json = json.dumps({k: str(v) for k, v in row_dict.items() if pd.notnull(v)})
                    # Save to DB
                    excel_row = ExcelRow(
                        file_id=file_id,
                        sheet_name=sheet_name,
                        row_index=idx,
                        row_data=row_json
                    )
                    db.session.add(excel_row)
                # We'll commit later outside this function

        # 1) Specialized logic for "Summary"
        if "Summary" in excel_data.sheet_names:
            df_summary = excel_data.parse("Summary", skiprows=3)
            needed_cols = ["Row Labels", "CTH", "HCM", "HNI", "Grand Total"]
            for col in needed_cols:
                if col not in df_summary.columns:
                    pass
            df_summary = df_summary.dropna(subset=["Row Labels"])
            for _, row in df_summary.iterrows():
                parsed_data['summary_data'].append({
                    'row_labels': str(row.get("Row Labels", "")),
                    'cth': float(row["CTH"]) if pd.notnull(row.get("CTH")) else None,
                    'hcm': float(row["HCM"]) if pd.notnull(row.get("HCM")) else None,
                    'hni': float(row["HNI"]) if pd.notnull(row.get("HNI")) else None,
                    'grand_total': float(row["Grand Total"]) if pd.notnull(row.get("Grand Total")) else None
                })

        # 2) Specialized logic for "BANG KE CHI TIET"
        if "BANG KE CHI TIET" in excel_data.sheet_names:
            df_details = excel_data.parse("BANG KE CHI TIET")
            df_details["NGÀY ĐH"] = pd.to_datetime(df_details["NGÀY ĐH"], errors="coerce")
            df_details["NGÀY CHI"] = pd.to_datetime(df_details["NGÀY CHI"], errors="coerce")
            df_details["Delay (Days)"] = (df_details["NGÀY CHI"] - df_details["NGÀY ĐH"]).dt.days

            for _, row in df_details.iterrows():
                parsed_data['detail_data'].append({
                    'ngay_dh': row.get("NGÀY ĐH"),
                    'ngay_chi': row.get("NGÀY CHI"),
                    'delay_days': int(row["Delay (Days)"]) if pd.notnull(row.get("Delay (Days)")) else None
                })

        return parsed_data

    except Exception as e:
        print(f"Error processing Excel file: {e}")
        raise e


# Pass the current datetime to all templates
@app.context_processor
def inject_datetime():
    return {'now': datetime.utcnow()}


# --------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------

@app.route('/')
@app.route('/home')
def home():
    """
    Homepage. Shows a welcome message if user is logged in.
    """
    user = None
    if 'user_id' in session:
        user = User.query.get(session['user_id'])
    return render_template('homepage.html', user=user)


@app.route('/register', methods=['GET', 'POST'])
def register():
    """
    Register a new user.
    """
    form = RegistrationForm()
    if form.validate_on_submit():
        hashed_password = bcrypt.generate_password_hash(form.password.data).decode('utf-8')
        user = User(
            first_name=form.first_name.data,
            last_name=form.last_name.data,
            email=form.email.data,
            password=hashed_password
        )
        db.session.add(user)
        db.session.commit()
        flash('Your account has been created! You can now log in.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html', form=form)


@app.route('/login', methods=['GET', 'POST'])
def login():
    """
    User login route.
    """
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


@app.route('/logout')
def logout():
    """
    Logs out the current user and clears the session.
    """
    session.clear()
    flash('You have been logged out.', 'success')
    return redirect(url_for('home'))


@app.route('/profile')
def profile():
    """
    Displays the logged-in user's profile.
    """
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
    """
    Edits the profile details (first_name, last_name) of the user.
    """
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


@app.route('/upload', methods=['GET', 'POST'])
def upload():
    """
    Allows the user to upload a file (PDF, DOC, DOCX, XLS, XLSX) of max size 10MB.
    The file is parsed; extracted data is stored in the database.
    Also stores ALL rows of the Excel file in ExcelRow if .xls/.xlsx.
    The original file is removed from the server once processed.
    """
    if 'user_id' not in session:
        flash('You must be logged in to upload files.', 'danger')
        return redirect(url_for('login'))

    if request.method == 'POST':
        # Check if file size exceeds 10MB before reading it
        if request.content_length and request.content_length > 10 * 1024 * 1024:
            flash('File is too large. Maximum 10MB allowed.', 'danger')
            return redirect(request.url)

        file = request.files.get('file')
        if not file or file.filename == '':
            flash('No file selected.', 'danger')
            return redirect(request.url)

        if allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(file_path)
            file_size_kb = os.path.getsize(file_path) / 1024.0

            if file_size_kb > 10240:  # 10MB in KB
                os.remove(file_path)
                flash('File is too large. Maximum 10MB allowed.', 'danger')
                return redirect(request.url)

            try:
                # 1) Create a new File record in DB (so we have file_id)
                new_file = File(
                    filename=filename,
                    size=file_size_kb,
                    user_id=session['user_id']
                )
                db.session.add(new_file)
                db.session.commit()  # new_file.id is now available

                extension = filename.rsplit('.', 1)[1].lower()

                # 2) If this is Excel, parse & store all row data in ExcelRow
                if extension in ['xls', 'xlsx']:
                    # parse_excel with file_id so it can store data in ExcelRow
                    parsed_data = parse_excel(file_path, file_id=new_file.id)
                else:
                    # For PDF/Word, parse normally
                    parsed_data = parse_file(file_path, filename)

                # 3) Save raw parsed_data to the file record if desired
                new_file.parsed_data = str(parsed_data)
                db.session.commit()

                # 4) If the file was Excel, also insert specialized summary/detail rows
                if extension in ['xls', 'xlsx']:
                    # Insert summary rows
                    for row_dict in parsed_data.get('summary_data', []):
                        summary_row = SummaryData(
                            file_id=new_file.id,
                            row_labels=row_dict['row_labels'],
                            cth=row_dict['cth'],
                            hcm=row_dict['hcm'],
                            hni=row_dict['hni'],
                            grand_total=row_dict['grand_total']
                        )
                        db.session.add(summary_row)

                    # Insert detail rows
                    for row_dict in parsed_data.get('detail_data', []):
                        detail_row = DetailData(
                            file_id=new_file.id,
                            ngay_dh=row_dict['ngay_dh'],
                            ngay_chi=row_dict['ngay_chi'],
                            delay_days=row_dict['delay_days']
                        )
                        db.session.add(detail_row)

                    db.session.commit()

                flash('File uploaded and parsed successfully!', 'success')

            except Exception as e:
                flash('An error occurred while processing the file.', 'danger')
                print(f"Error: {e}")
            finally:
                if os.path.exists(file_path):
                    os.remove(file_path)

            return redirect(url_for('view_files'))
        else:
            flash('Invalid file extension.', 'danger')
            return redirect(request.url)

    return render_template('upload.html')


@app.route('/files')
def view_files():
    """
    Lists all files uploaded by the currently logged-in user.
    """
    if 'user_id' not in session:
        flash('You need to log in to view files.', 'danger')
        return redirect(url_for('login'))

    user_files = File.query.filter_by(user_id=session['user_id']).all()
    if user_files == None:
        user_files = []
    return render_template('files.html', files=user_files)


@app.route('/delete-file/<int:file_id>', methods=['POST'])
def delete_file(file_id):
    """
    Deletes a file and its related data (summary, detail) from the database.
    """
    file = File.query.get_or_404(file_id)
    if file.user_id != session['user_id']:
        flash('Unauthorized action.', 'danger')
        return redirect(url_for('view_files'))

    # Delete related rows from SummaryData & DetailData
    SummaryData.query.filter_by(file_id=file_id).delete()
    DetailData.query.filter_by(file_id=file_id).delete()

    # Delete related rows from ExcelRow
    ExcelRow.query.filter_by(file_id=file_id).delete()

    # Remove the file from server if it still exists
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
    if os.path.exists(file_path):
        os.remove(file_path)

    # Remove file record
    db.session.delete(file)
    db.session.commit()
    flash('File and related data deleted successfully!', 'success')
    return redirect(url_for('view_files'))


# --------------------------------------------------------------------
# Analysis routes
# --------------------------------------------------------------------

@app.route('/view-summary/<int:file_id>')
def view_summary(file_id):
    """
    View raw summary rows for a specific file from the "Summary" sheet.
    """
    if 'user_id' not in session:
        flash('You need to log in.', 'danger')
        return redirect(url_for('login'))

    summary_rows = SummaryData.query.filter_by(file_id=file_id).all()
    return render_template('view_summary.html', rows=summary_rows, file_id=file_id)


@app.route('/view-details/<int:file_id>')
def view_details(file_id):
    """
    View raw detail rows for a specific file from the "BANG KE CHI TIET" sheet.
    This also inherently shows the delay_days for each row, highlighting inefficiencies.
    """
    if 'user_id' not in session:
        flash('You need to log in.', 'danger')
        return redirect(url_for('login'))

    detail_rows = DetailData.query.filter_by(file_id=file_id).all()
    return render_template('view_details.html', rows=detail_rows, file_id=file_id)


@app.route('/analyze_route/<int:file_id>')
def analyze_route(file_id):
    """
    Analyze the detail data to provide route suggestions based on delays.
    - If delay_days is above a threshold, we generate an "optimized route".
    - The result is presented in a table-based report that includes the
      original route, the optimized route, and potential time savings.
    """
    if 'user_id' not in session:
        flash('You need to log in.', 'danger')
        return redirect(url_for('login'))

    # Fetch all detail rows for the file
    detail_rows = DetailData.query.filter_by(file_id=file_id).all()

    # Build suggestion data
    route_report = []
    for row in detail_rows:
        current_route = "Route A"  # Example placeholder
        optimized_route = "Route B"  # Example placeholder

        # If row.delay_days > 2, propose a random time saving
        if row.delay_days and row.delay_days > 2:
            time_saving_hours = random.randint(1, 24)
        else:
            time_saving_hours = 0

        route_report.append({
            'ngay_dh': row.ngay_dh,
            'ngay_chi': row.ngay_chi,
            'delay_days': row.delay_days,
            'current_route': current_route,
            'optimized_route': optimized_route if time_saving_hours > 0 else "N/A",
            'time_saving_hours': time_saving_hours
        })

    return render_template('route_analysis.html', route_report=route_report, file_id=file_id)


@app.route('/analyze_cost/<int:file_id>')
def analyze_cost(file_id):
    """
    Perform cost analysis on the 'SummaryData' rows for a selected file.
    We produce a table of costs AND a bar chart to visualize them.
    """
    if 'user_id' not in session:
        flash('You need to log in.', 'danger')
        return redirect(url_for('login'))

    # Fetch summary data for the file
    summary_rows = SummaryData.query.filter_by(file_id=file_id).all()

    # Prepare data for Chart.js
    labels = [row.row_labels for row in summary_rows]
    cth_data = [row.cth if row.cth else 0 for row in summary_rows]
    hcm_data = [row.hcm if row.hcm else 0 for row in summary_rows]
    hni_data = [row.hni if row.hni else 0 for row in summary_rows]
    grand_data = [row.grand_total if row.grand_total else 0 for row in summary_rows]

    return render_template(
        'cost_analysis.html',
        summary_rows=summary_rows,
        labels=json.dumps(labels),
        cth_data=json.dumps(cth_data),
        hcm_data=json.dumps(hcm_data),
        hni_data=json.dumps(hni_data),
        grand_data=json.dumps(grand_data),
        file_id=file_id
    )


# --------------------------------------------------------------------
# NEW: Route to view ALL Excel data in ExcelRow (optional)
# --------------------------------------------------------------------
@app.route('/view-all-excel-data/<int:file_id>')
def view_all_excel_data(file_id):
    """
    Shows all raw rows from ExcelRow for a given file_id, grouped by sheet.
    """
    if 'user_id' not in session:
        flash('You need to log in.', 'danger')
        return redirect(url_for('login'))

    file = File.query.get_or_404(file_id)
    if file.user_id != session['user_id']:
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('view_files'))

    from collections import defaultdict
    excel_rows = ExcelRow.query.filter_by(file_id=file_id).order_by(ExcelRow.sheet_name, ExcelRow.row_index).all()
    grouped_sheets = defaultdict(list)
    for row in excel_rows:
        grouped_sheets[row.sheet_name].append(row)

    return render_template('view_all_excel.html', file=file, grouped_sheets=grouped_sheets)


# --------------------------------------------------------------------
# Main Entry
# --------------------------------------------------------------------
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
