from datetime import datetime

from flask import render_template, redirect, url_for, flash, session

from . import app, db, bcrypt
from .forms import RegistrationForm, LoginForm, ProfileEditForm
from .models import User, File


@app.context_processor
def inject_now():
    return {"now": datetime.utcnow()}


@app.route('/')
def home():
    user = None
    if 'user_id' in session:
        user = User.query.get(session['user_id'])
        if user:
            user_files = File.query.filter_by(user_id=user.id).all()
            session['user_files'] = [{"id": f.id, "filename": f.filename} for f in user_files]
    return render_template('homepage.html', user=user)


@app.route('/register', methods=['GET', 'POST'])
def register():
    form = RegistrationForm()
    if form.validate_on_submit():
        hashed = bcrypt.generate_password_hash(form.password.data).decode('utf-8')
        usr = User(
            first_name=form.first_name.data,
            last_name=form.last_name.data,
            email=form.email.data,
            password=hashed
        )
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
