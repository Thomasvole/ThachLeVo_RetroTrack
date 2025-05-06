from flask import render_template, redirect, url_for, flash, session

from . import app
from .helpers import update_cached_routes, generate_cost_waste_chart
from .models import File, InefficientRoute


@app.route('/cost-analysis')
@app.route('/cost-analysis/<int:file_id>')
def cost_analysis(file_id=None):
    if 'user_id' not in session:
        flash("Login required.", "danger")
        return redirect(url_for('login'))

    if file_id is None:
        files_list = File.query.filter_by(user_id=session['user_id']).all()
        return render_template("cost_analysis.html",
                               files=files_list,
                               cost_data=None,
                               chart_url=None,
                               selected_file=None)

    routes = InefficientRoute.query.filter_by(file_id=file_id).all()
    update_cached_routes(routes)
    cost_data = []
    for r in routes:
        try:
            actual_duration = (r.actual_delivery_time - r.starting_time).total_seconds() / 3600.0
        except Exception:
            continue
        if r.optimized_delivery_time is None:
            continue

        optimized_time = r.optimized_delivery_time
        optimized_cost = r.max_delivery_cost * optimized_time
        actual_cost = r.max_delivery_cost * actual_duration
        cost_saved = actual_cost - optimized_cost

        cost_data.append({
            "route_id": r.id,
            "base_address": r.base_address,
            "shipping_address": r.shipping_address,
            "actual_duration": round(actual_duration, 2),
            "optimized_time": round(optimized_time, 2),
            "max_delivery_cost": r.max_delivery_cost,
            "optimized_cost": round(optimized_cost, 2),
            "actual_cost": round(actual_cost, 2),
            "cost_saved": round(cost_saved, 2)
        })

    chart_url = None
    if cost_data:
        chart_url = generate_cost_waste_chart(cost_data, file_id)

    selected_file = File.query.get_or_404(file_id)
    return render_template("cost_analysis.html",
                           files=None,
                           cost_data=cost_data,
                           chart_url=chart_url,
                           selected_file=selected_file)
