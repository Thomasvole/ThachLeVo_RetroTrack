from datetime import datetime

from . import db


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(100), nullable=False)
    last_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(60), nullable=False)

    def __repr__(self):
        return f"User('{self.email}')"


class File(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False)
    upload_date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    size = db.Column(db.Float, nullable=False)
    user_id = db.Column(db.Integer, nullable=False)
    parsed_data = db.Column(db.Text, nullable=True)

    def __repr__(self):
        return f"File('{self.filename}', UserID={self.user_id})"


class InefficientRoute(db.Model):
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
    optimized_delivery_time = db.Column(db.Float, nullable=True)
    time_saved = db.Column(db.Float, nullable=True)

    def __repr__(self):
        delay = (self.actual_delivery_time - self.expected_delivery_time).total_seconds() / 3600.0
        return f"InefficientRoute(FileID={self.file_id}, BaseAddress={self.base_address}, Delay={round(delay, 2)}h)"
