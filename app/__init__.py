import os

from flask import Flask
from flask_bcrypt import Bcrypt
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
# Core configuration
app.config['SECRET_KEY'] = 'a_very_secret_key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///site.db'
app.config['UPLOAD_FOLDER'] = 'uploads/'
app.config['ALLOWED_EXTENSIONS'] = {'pdf', 'doc', 'docx', 'xls', 'xlsx'}
app.config['GEOAPIFY_API_KEY'] = "380c58ce52a64969a8f5a6e5ea6106da"

# Ensure upload folder exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Initialize extensions
db = SQLAlchemy(app)
bcrypt = Bcrypt(app)

# Import route modules to register their endpoints
from . import routes
from . import upload_routes
from . import inefficient_routes
from . import cost_analysis_routes
from . import report_routes
