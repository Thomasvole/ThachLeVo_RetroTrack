import json
import os

from flask import render_template, redirect, url_for, flash, session, request
from werkzeug.utils import secure_filename

from . import app, db
from .helpers import parse_excel, to_float, update_cached_routes
from .models import File, InefficientRoute


@app.route('/upload', methods=['GET', 'POST'])
def upload():
    if 'user_id' not in session:
        flash("Login required to upload files.", "danger")
        return redirect(url_for('login'))

    if request.method == 'POST':
        # 10 MB max
        if request.content_length and request.content_length > 10 * 1024 * 1024:
            flash("File too large (>10MB).", "danger")
            return redirect(url_for('upload'))

        file = request.files.get('file')
        if not file or file.filename == '':
            flash("No file selected.", "danger")
            return redirect(url_for('upload'))

        ext = file.filename.rsplit('.', 1)[-1].lower()
        if ext in app.config['ALLOWED_EXTENSIONS']:
            fname = secure_filename(file.filename)
            fpath = os.path.join(app.config['UPLOAD_FOLDER'], fname)
            file.save(fpath)
            size_kb = os.path.getsize(fpath) / 1024.0

            # enforce 10 MB server‐side too
            if size_kb > 10240:
                os.remove(fpath)
                flash("File too large (>10MB).", "danger")
                return redirect(url_for('upload'))

            try:
                # Save metadata
                new_file = File(filename=fname, size=size_kb, user_id=session['user_id'])
                db.session.add(new_file)
                db.session.commit()

                # Parse only Excel for routes
                if ext in ['xls', 'xlsx']:
                    parsed = parse_excel(fpath)
                else:
                    flash("Only Excel files are supported for parsing inefficient routes.", "danger")
                    return redirect(url_for('upload'))

                # Store raw parsed JSON
                new_file.parsed_data = json.dumps(parsed, default=str)
                db.session.commit()

                # Insert any delay>24h routes
                for route in parsed.get('inefficient_routes', []):
                    delay = route.get("delay_hours")
                    if delay is None:
                        ev = to_float(route["expected_delivery_time"])
                        av = to_float(route["actual_delivery_time"])
                        if ev is not None and av is not None:
                            delay = av - ev
                        else:
                            try:
                                delay = (route["actual_delivery_time"] - route["expected_delivery_time"]) \
                                            .total_seconds() / 3600.0
                            except:
                                continue

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

                # Now fetch them and update with optimized times & time_saved
                routes = InefficientRoute.query.filter_by(file_id=new_file.id).all()
                update_cached_routes(routes)

                flash("File uploaded and processed successfully!", "success")
                return redirect(url_for('files'))

            except Exception as e:
                db.session.rollback()
                flash("Error processing the file.", "danger")
                print("Error:", e)

            finally:
                if os.path.exists(fpath):
                    os.remove(fpath)

        else:
            flash("Invalid file extension.", "danger")
            return redirect(url_for('upload'))

    return render_template('upload.html', form_action=url_for('upload'))


@app.route('/delete-file/<int:file_id>', methods=['POST'])
def delete_file(file_id):
    if 'user_id' not in session:
        flash("Login required.", "danger")
        return redirect(url_for('login'))

    this_file = File.query.get_or_404(file_id)
    if this_file.user_id != session['user_id']:
        flash("Not authorized.", "danger")
        return redirect(url_for('files'))

    fpath = os.path.join(app.config['UPLOAD_FOLDER'], this_file.filename)
    try:
        if os.path.exists(fpath):
            os.remove(fpath)
    except Exception as e:
        flash(f"Error deleting file: {e}", "danger")

    try:
        InefficientRoute.query.filter_by(file_id=file_id).delete()
        db.session.delete(this_file)
        db.session.commit()
        flash("File and data deleted.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Database error: {e}", "danger")

    return redirect(url_for('files'))


@app.route('/files')
def files():
    if 'user_id' not in session:
        flash("Login required.", "danger")
        return redirect(url_for('login'))

    user_files = File.query.filter_by(user_id=session['user_id']).all()
    return render_template('files.html', files=user_files)
