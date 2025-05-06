import json
from datetime import datetime, timedelta

from flask import render_template, redirect, url_for, flash, session, request

from . import app, db
from .helpers import update_cached_routes, to_float
from .models import File, InefficientRoute


@app.route('/inefficient', methods=['GET', 'POST'])
@app.route('/inefficient/<int:file_id>', methods=['GET', 'POST'])
def show_inefficient(file_id=None):
    if 'user_id' not in session:
        flash("Login required.", "danger")
        return redirect(url_for('login'))

    if request.method == 'POST':
        new_routes_count = 0
        user_files = File.query.filter_by(user_id=session['user_id']).all()
        for file in user_files:
            if file.parsed_data:
                try:
                    data = json.loads(file.parsed_data)
                    for route in data.get("inefficient_routes", []):
                        existing = InefficientRoute.query.filter_by(
                            file_id=file.id,
                            base_address=route["base_address"],
                            starting_time=route["starting_time"]
                        ).first()
                        if existing:
                            continue

                        delay = route.get("delay_hours")
                        if delay is None:
                            ev = to_float(route["expected_delivery_time"])
                            av = to_float(route["actual_delivery_time"])
                            if ev is not None and av is not None:
                                delay = av - ev
                            else:
                                continue

                        if delay > 24:
                            try:
                                start_time = datetime.fromisoformat(route["starting_time"])
                            except Exception:
                                start_time = datetime.strptime(route["starting_time"], "%Y-%m-%d %H:%M:%S")

                            expected_time = (
                                start_time + timedelta(hours=route["expected_delivery_time"]) if isinstance(
                                    route["expected_delivery_time"], float)
                                else datetime.fromisoformat(route["expected_delivery_time"]))

                            actual_time = (start_time + timedelta(hours=route["actual_delivery_time"]) if isinstance(
                                route["actual_delivery_time"], float)
                                           else datetime.fromisoformat(route["actual_delivery_time"]))

                            new_ir = InefficientRoute(
                                file_id=file.id,
                                base_address=route["base_address"],
                                shipping_address=route["shipping_address"],
                                starting_time=start_time,
                                expected_delivery_time=expected_time,
                                actual_delivery_time=actual_time,
                                expected_delivery_cost=to_float(route["expected_delivery_cost"]),
                                actual_delivery_cost=to_float(route["actual_delivery_cost"]),
                                max_delivery_cost=to_float(route["max_delivery_cost"])
                            )
                            db.session.add(new_ir)
                            new_routes_count += 1
                except Exception as e:
                    print("Error processing file", file.filename, e)

        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            flash("An error occurred while saving to the database.", "danger")
            print("Commit error:", e)
            return redirect(url_for('show_inefficient'))

        if new_routes_count > 0:
            flash(f"{new_routes_count} inefficient route(s) identified and saved into the database.", "success")
        else:
            flash("No new inefficient routes found.", "info")
        return redirect(url_for('show_inefficient'))

    if file_id is None:
        file_ids = [fid for (fid,) in db.session.query(InefficientRoute.file_id).distinct().all()]
        files_list = File.query.filter(File.id.in_(file_ids), File.user_id == session['user_id']).all()
        return render_template("inefficient.html", files=files_list, routes=None, selected_file=None)
    else:
        routes = InefficientRoute.query.filter_by(file_id=file_id).all()
        update_cached_routes(routes)

        ineff_data = []
        for r in routes:
            try:
                delay = (r.actual_delivery_time - r.expected_delivery_time).total_seconds() / 3600.0
            except Exception:
                delay = "N/A"
            ineff_data.append({
                "file_id": r.file_id,
                "base_address": r.base_address,
                "shipping_address": r.shipping_address,
                "starting_time": r.starting_time.strftime("%Y-%m-%d %H:%M"),
                "expected_delivery_time": r.expected_delivery_time.strftime("%Y-%m-%d %H:%M"),
                "actual_delivery_time": r.actual_delivery_time.strftime("%Y-%m-%d %H:%M"),
                "expected_delivery_cost": r.expected_delivery_cost,
                "actual_delivery_cost": r.actual_delivery_cost,
                "max_delivery_cost": r.max_delivery_cost,
                "delay_hours": round(delay, 2) if isinstance(delay, (int, float)) else delay,
                "optimized_delivery_time": r.optimized_delivery_time if r.optimized_delivery_time is not None else "N/A",
                "time_saved": r.time_saved if r.time_saved is not None else "N/A"
            })

        selected_file = File.query.get(file_id)
        return render_template("inefficient.html", files=None, routes=ineff_data, selected_file=selected_file)
