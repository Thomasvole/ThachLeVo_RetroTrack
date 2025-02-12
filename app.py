import json
import os
from datetime import datetime

import pandas as pd
from flask import Flask, render_template, redirect, url_for, flash, session, request
from flask_bcrypt import Bcrypt
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import FlaskForm
from werkzeug.utils import secure_filename
from wtforms import StringField, PasswordField, SubmitField
from wtforms.validators import DataRequired, EqualTo

#########################################################################
# Initialize Flask app and configuration
#########################################################################
app = Flask(__name__)
app.config['SECRET_KEY'] = 'a_very_secret_key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///site.db'
app.config['UPLOAD_FOLDER'] = 'uploads/'
app.config['ALLOWED_EXTENSIONS'] = {'pdf', 'doc', 'docx', 'xls', 'xlsx'}

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

db = SQLAlchemy(app)
bcrypt = Bcrypt(app)


#########################################################################
# Database Models
#########################################################################
class User(db.Model):
    """Represents a user in the system."""
    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(100), nullable=False)
    last_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(60), nullable=False)

    def __repr__(self):
        return f"User('{self.email}')"


class File(db.Model):
    """Represents a file uploaded by a user."""
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False)
    upload_date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    size = db.Column(db.Float, nullable=False)
    user_id = db.Column(db.Integer, nullable=False)  # storing owner user id
    parsed_data = db.Column(db.Text, nullable=True)

    def __repr__(self):
        return f"File('{self.filename}', UserID={self.user_id})"


class InefficientRoute(db.Model):
    """
    Stores route information when the actual delivery time lags the expected delivery time by >24 hours.
    Only rows with complete data in these columns are stored:
      - Base Address, Shipping Address, Starting Time,
      - Expected Delivery Time, Actual Delivery Time,
      - Expected Delivery Cost, Actual Delivery Cost, Max Delivery Cost.
    (Delay is computed on the fly when displaying.)
    """
    id = db.Column(db.Integer, primary_key=True)
    file_id = db.Column(db.Integer, db.ForeignKey('file.id'), nullable=False)
    base_address = db.Column(db.String(255), nullable=False)
    shipping_address = db.Column(db.String(255), nullable=False)
    starting_time = db.Column(db.DateTime, nullable=False)
    expected_delivery_time = db.Column(db.DateTime, nullable=False)
    actual_delivery_time = db.Column(db.DateTime, nullable=False)
    expected_delivery_cost = db.Column(db.Float, nullable=False)
    actual_delivery_cost = db.Column(db.Float, nullable=False)
    max_delivery_cost = db.Column(db.Float, nullable=False)

    def __repr__(self):
        # Compute delay on the fly.
        delay = (self.actual_delivery_time - self.expected_delivery_time).total_seconds() / 3600.0
        return f"InefficientRoute(FileID={self.file_id}, BaseAddress={self.base_address}, Delay={round(delay, 2)}h)"


#########################################################################
# Forms
#########################################################################
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


#########################################################################
# Helper Functions
#########################################################################
def allowed_file(filename):
    """Return True if the file extension is allowed."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']


def to_float(value):
    """Convert a value (possibly containing commas) to a float."""
    try:
        return float(str(value).replace(',', '').strip())
    except Exception:
        return None


def parse_excel(file_path):
    """
    Extracts inefficient route data from an Excel file.

    Expected columns (exact match):
      - Base Address
      - Shipping Address
      - Starting Time
      - Expected Delivery Time (hours)
      - Actual Delivery Time (hours)
      - Expected Delivery Cost (VND)
      - Actual Delivery Cost (VND)
      - Max Delivery Cost (VND/hr)

    Converts "Starting Time" to a datetime and attempts to convert the expected and actual
    delivery time values to floats. If both are numeric, delay = actual - expected;
    otherwise, delay is computed using datetime subtraction.
    Only rows with delay > 24 hours are kept.
    Returns a dictionary with key "inefficient_routes".
    """
    required_cols = [
        "Base Address",
        "Shipping Address",
        "Starting Time",
        "Expected Delivery Time (hours)",
        "Actual Delivery Time (hours)",
        "Expected Delivery Cost (VND)",
        "Actual Delivery Cost (VND)",
        "Max Delivery Cost (VND/hr)"
    ]
    result = {"inefficient_routes": []}
    try:
        xls = pd.ExcelFile(file_path)
        for sheet in xls.sheet_names:
            df = xls.parse(sheet)
            df.columns = df.columns.str.strip()
            if not set(required_cols).issubset(df.columns):
                continue
            for _, row in df.iterrows():
                # Skip if any required value is missing.
                if any(pd.isnull(row[col]) for col in required_cols):
                    continue
                try:
                    st = pd.to_datetime(row["Starting Time"], errors='coerce')
                except Exception:
                    continue
                if pd.isnull(st):
                    continue
                # Try converting expected and actual delivery times to float.
                exp_val = to_float(row["Expected Delivery Time (hours)"])
                act_val = to_float(row["Actual Delivery Time (hours)"])
                if exp_val is None or act_val is None:
                    # Fallback: try converting to datetime.
                    exp_dt_tmp = pd.to_datetime(row["Expected Delivery Time (hours)"], errors='coerce')
                    act_dt_tmp = pd.to_datetime(row["Actual Delivery Time (hours)"], errors='coerce')
                    if pd.isnull(exp_dt_tmp) or pd.isnull(act_dt_tmp):
                        continue
                    diff = (act_dt_tmp - exp_dt_tmp).total_seconds() / 3600.0
                    exp_dt, act_dt = exp_dt_tmp, act_dt_tmp
                else:
                    diff = act_val - exp_val
                    base = st
                    exp_dt = base + pd.to_timedelta(exp_val, unit='h')
                    act_dt = base + pd.to_timedelta(act_val, unit='h')
                if diff > 24:
                    ec = to_float(row["Expected Delivery Cost (VND)"])
                    ac = to_float(row["Actual Delivery Cost (VND)"])
                    mc = to_float(row["Max Delivery Cost (VND/hr)"])
                    if None in (ec, ac, mc):
                        continue
                    route = {
                        "base_address": str(row["Base Address"]),
                        "shipping_address": str(row["Shipping Address"]),
                        "starting_time": st,
                        "expected_delivery_time": exp_dt,
                        "actual_delivery_time": act_dt,
                        "expected_delivery_cost": ec,
                        "actual_delivery_cost": ac,
                        "max_delivery_cost": mc,
                        "delay_hours": diff  # computed delay in hours
                    }
                    result["inefficient_routes"].append(route)
        # Debug print to console
        print("Parsed Inefficient Routes:")
        print(json.dumps(result, default=str, indent=4))
        return result
    except Exception as e:
        print(f"Error processing Excel file: {e}")
        return result


#########################################################################
# Context Processor
#########################################################################
@app.context_processor
def inject_now():
    return {"now": datetime.utcnow()}


#########################################################################
# Routes
#########################################################################
@app.route('/')
@app.route('/home')
def home():
    user = None
    if 'user_id' in session:
        user = User.query.get(session['user_id'])
    return render_template('homepage.html', user=user)


@app.route('/register', methods=['GET', 'POST'])
def register():
    form = RegistrationForm()
    if form.validate_on_submit():
        hashed = bcrypt.generate_password_hash(form.password.data).decode('utf-8')
        usr = User(first_name=form.first_name.data,
                   last_name=form.last_name.data,
                   email=form.email.data,
                   password=hashed)
        db.session.add(usr)
        db.session.commit()
        flash("Account created. Please log in.", "success")
        return redirect(url_for('login'))
    return render_template('register.html', form=form)


@app.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        usr = User.query.filter_by(email=form.email.data).first()
        if usr and bcrypt.check_password_hash(usr.password, form.password.data):
            session['user_id'] = usr.id
            session['user_name'] = f"{usr.first_name} {usr.last_name}"
            session['user_email'] = usr.email
            flash("Logged in successfully.", "success")
            return redirect(url_for('home'))
        else:
            flash("Login failed. Check email/password.", "danger")
    return render_template('login.html', form=form)


@app.route('/logout')
def logout():
    session.clear()
    flash("Logged out.", "success")
    return redirect(url_for('home'))


@app.route('/profile')
def profile():
    if 'user_id' not in session:
        flash("Login required.", "danger")
        return redirect(url_for('login'))
    usr = User.query.get(session['user_id'])
    if not usr:
        flash("User not found.", "danger")
        return redirect(url_for('logout'))
    return render_template('profile.html', user=usr)


@app.route('/edit-profile', methods=['GET', 'POST'])
def edit_profile():
    if 'user_id' not in session:
        flash("Login required.", "danger")
        return redirect(url_for('login'))
    usr = User.query.get(session['user_id'])
    if not usr:
        flash("User not found.", "danger")
        return redirect(url_for('logout'))
    form = ProfileEditForm(obj=usr)
    if form.validate_on_submit():
        usr.first_name = form.first_name.data
        usr.last_name = form.last_name.data
        db.session.commit()
        flash("Profile updated.", "success")
        return redirect(url_for('profile'))
    return render_template('edit_profile.html', form=form, user=usr)


@app.route('/upload', methods=['GET', 'POST'])
def upload():
    if 'user_id' not in session:
        flash("Login required to upload files.", "danger")
        return redirect(url_for('login'))
    if request.method == 'POST':
        if request.content_length and request.content_length > 10 * 1024 * 1024:
            flash("File too large (>10MB).", "danger")
            return redirect(request.url)
        file = request.files.get('file')
        if not file or file.filename == '':
            flash("No file selected.", "danger")
            return redirect(request.url)
        if allowed_file(file.filename):
            fname = secure_filename(file.filename)
            fpath = os.path.join(app.config['UPLOAD_FOLDER'], fname)
            file.save(fpath)
            size_kb = os.path.getsize(fpath) / 1024.0
            if size_kb > 10240:
                os.remove(fpath)
                flash("File too large (>10MB).", "danger")
                return redirect(request.url)
            try:
                new_file = File(filename=fname, size=size_kb, user_id=session['user_id'])
                db.session.add(new_file)
                db.session.commit()  # new_file.id is available

                ext = fname.rsplit('.', 1)[1].lower()
                if ext in ['xls', 'xlsx']:
                    parsed = parse_excel(fpath)
                else:
                    flash("Only Excel files are supported for parsing inefficient routes.", "danger")
                    return redirect(url_for('upload'))

                new_file.parsed_data = json.dumps(parsed, default=str)
                db.session.commit()

                # Insert inefficient route records (only if delay > 24 hours)
                for route in parsed.get('inefficient_routes', []):
                    delay = route.get("delay_hours")
                    if delay is None:
                        ev = to_float(route["expected_delivery_time"])
                        av = to_float(route["actual_delivery_time"])
                        if ev is not None and av is not None:
                            delay = av - ev
                        else:
                            delay = (route["actual_delivery_time"] - route[
                                "expected_delivery_time"]).total_seconds() / 3600.0
                    if delay > 24:
                        ir = InefficientRoute(
                            file_id=new_file.id,
                            base_address=route["base_address"],
                            shipping_address=route["shipping_address"],
                            starting_time=route["starting_time"],
                            expected_delivery_time=route["expected_delivery_time"],
                            actual_delivery_time=route["actual_delivery_time"],
                            expected_delivery_cost=to_float(route["expected_delivery_cost"]),
                            actual_delivery_cost=to_float(route["actual_delivery_cost"]),
                            max_delivery_cost=to_float(route["max_delivery_cost"])
                        )
                        db.session.add(ir)
                db.session.commit()

                # Debug: Print inefficient routes to console.
                ineffs = InefficientRoute.query.filter_by(file_id=new_file.id).all()
                print("\n=== Inefficient Routes Stored in DB ===")
                print("Number of inefficient routes:", len(ineffs))
                for ir in ineffs:
                    computed_delay = (ir.actual_delivery_time - ir.expected_delivery_time).total_seconds() / 3600.0
                    print(f"FileID: {ir.file_id}, Base: {ir.base_address}, Delay: {round(computed_delay, 2)}h")
                print("=== End ===\n")

                flash("File uploaded and processed successfully!", "success")
            except Exception as e:
                flash("Error processing the file.", "danger")
                print("Error:", e)
            finally:
                if os.path.exists(fpath):
                    os.remove(fpath)
            return redirect(url_for('files'))
        else:
            flash("Invalid file extension.", "danger")
            return redirect(request.url)
    return render_template('upload.html')


@app.route('/files')
def files():
    if 'user_id' not in session:
        flash("Login required.", "danger")
        return redirect(url_for('login'))
    user_files = File.query.filter_by(user_id=session['user_id']).all()
    return render_template('files.html', files=user_files)


@app.route('/delete-file/<int:file_id>', methods=['POST'])
def delete_file(file_id):
    if 'user_id' not in session:
        flash("Login required.", "danger")
        return redirect(url_for('login'))
    this_file = File.query.get_or_404(file_id)
    if this_file.user_id != session['user_id']:
        flash("Not authorized.", "danger")
        return redirect(url_for('files'))
    # Delete associated inefficient routes.
    InefficientRoute.query.filter_by(file_id=file_id).delete()
    fpath = os.path.join(app.config['UPLOAD_FOLDER'], this_file.filename)
    if os.path.exists(fpath):
        os.remove(fpath)
    db.session.delete(this_file)
    db.session.commit()
    flash("File and related data deleted.", "success")
    return redirect(url_for('files'))


@app.route('/inefficient')
def show_inefficient():
    """
    Displays all inefficient routes from the database.
    The delay is computed on the fly (actual_delivery_time - expected_delivery_time).
    """
    routes = InefficientRoute.query.all()
    print("Number of inefficient routes found:", len(routes))
    ineffs = []
    for r in routes:
        try:
            delay = (r.actual_delivery_time - r.expected_delivery_time).total_seconds() / 3600.0
        except Exception:
            delay = "N/A"
        ineffs.append({
            "file_id": r.file_id,
            "base_address": r.base_address,
            "shipping_address": r.shipping_address,
            "starting_time": r.starting_time,
            "expected_delivery_time": r.expected_delivery_time,
            "actual_delivery_time": r.actual_delivery_time,
            "expected_delivery_cost": r.expected_delivery_cost,
            "actual_delivery_cost": r.actual_delivery_cost,
            "max_delivery_cost": r.max_delivery_cost,
            "delay_hours": round(delay, 2) if isinstance(delay, (int, float)) else delay
        })
    return render_template("inefficient.html", routes=ineffs)


#########################################################################
# Main Entry
#########################################################################
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
