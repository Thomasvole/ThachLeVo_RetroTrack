from flask import render_template, redirect, url_for, flash, session

from . import app
from .helpers import update_cached_routes, generate_cost_waste_chart
from .models import File, InefficientRoute


@app.route('/cost-analysis')
@app.route('/cost-analysis/<int:file_id>')
def cost_analysis(file_id=None):
    """
        Display cost analysis for inefficient routes.
        If no file_id is provided, show available files.
        Otherwise, compute and render cost data and chart for the selected file.
    """
    # Ensure the user is logged in
    if 'user_id' not in session:
        flash("Login required.", "danger")
        return redirect(url_for('login'))

    # If no specific file selected, list all user-uploaded files
    if file_id is None:
        files_list = File.query.filter_by(user_id=session['user_id']).all()
        return render_template("cost_analysis.html",
                               files=files_list,
                               cost_data=None,
                               chart_url=None,
                               selected_file=None)

    # Retrieve all inefficient routes for the given file
    routes = InefficientRoute.query.filter_by(file_id=file_id).all()
    # Update routes with optimized times and savings if needed
    update_cached_routes(routes)
    cost_data = []
    # Build cost_data list: one entry per route
    for r in routes:
        try:
            # Calculate actual duration in hours
            actual_duration = (r.actual_delivery_time - r.starting_time).total_seconds() / 3600.0
        except Exception:
            # Skip routes with invalid timestamps
            continue

        # Only include routes where optimized time is available
        if r.optimized_delivery_time is None:
            continue

        optimized_time = r.optimized_delivery_time
        # Compute cost on optimized and actual durations
        optimized_cost = r.max_delivery_cost * optimized_time
        actual_cost = r.max_delivery_cost * actual_duration
        # Calculate cost savings
        cost_saved = actual_cost - optimized_cost

        # Append a dict for rendering in the table
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
    # Generate bar-chart URL if there is any cost data
    if cost_data:
        chart_url = generate_cost_waste_chart(cost_data, file_id)

    # Get the file metadata or 404 if not found
    selected_file = File.query.get_or_404(file_id)

    # Render the template with cost data and chart
    return render_template("cost_analysis.html",
                           files=None,
                           cost_data=cost_data,
                           chart_url=chart_url,
                           selected_file=selected_file)
