import os

import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from flask import current_app, url_for


def generate_cost_waste_chart(cost_data, file_id):
    """
    Generates and saves a bar chart of cost_saved for each route into the app's static folder,
    then returns its URL.
    """
    # Ensure plots directory exists inside Flask's static folder
    plot_dir = os.path.join(current_app.root_path, 'static', 'plots')
    os.makedirs(plot_dir, exist_ok=True)

    if not cost_data:
        return None

    labels = [str(item['route_id']) for item in cost_data]
    waste_millions = [item['cost_saved'] / 1_000_000 for item in cost_data]

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.bar(labels, waste_millions)
    ax.set_xlabel('Route ID')
    ax.set_ylabel('Cost Saved (Million VND)')
    ax.set_title('Cost Saved per Inefficient Route')
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, rotation=45, ha='right')
    ax.yaxis.set_major_formatter(mticker.FormatStrFormatter('%.1f'))

    plt.tight_layout()
    plot_filename = f"cost_waste_{file_id}.png"
    plot_path = os.path.join(plot_dir, plot_filename)
    plt.savefig(plot_path)
    plt.close(fig)

    # Return URL for use in templates
    return url_for('static', filename=f'plots/{plot_filename}')


def generate_summary(file_id, user):
    from app.models import File, InefficientRoute
    from .geoapify import update_cached_routes

    file = File.query.get_or_404(file_id)
    routes = InefficientRoute.query.filter_by(file_id=file_id).all()
    update_cached_routes(routes)

    # Count only those delayed by >24h
    inefficient_count = len([
        r for r in routes
        if (r.actual_delivery_time - r.expected_delivery_time).total_seconds() / 3600 > 24
    ])

    total_delay = sum((r.actual_delivery_time - r.expected_delivery_time).total_seconds() / 3600 for r in routes)
    avg_delay = total_delay / inefficient_count if inefficient_count else 0

    total_saved = sum(r.time_saved for r in routes if r.time_saved)
    avg_saved = total_saved / inefficient_count if inefficient_count else 0

    total_cost_saved = 0
    cost_table = []
    for r in routes:
        try:
            actual_dur = (r.actual_delivery_time - r.starting_time).total_seconds() / 3600.0
        except Exception:
            continue
        if r.optimized_delivery_time is None:
            continue

        opt_time = r.optimized_delivery_time
        opt_cost = r.max_delivery_cost * opt_time
        act_cost = r.max_delivery_cost * actual_dur
        saved = act_cost - opt_cost
        total_cost_saved += saved
        cost_table.append({
            "route_id": r.id,
            "base_address": r.base_address,
            "shipping_address": r.shipping_address,
            "actual_duration": round(actual_dur, 2),
            "optimized_time": round(opt_time, 2),
            "max_delivery_cost": r.max_delivery_cost,
            "optimized_cost": round(opt_cost, 2),
            "actual_cost": round(act_cost, 2),
            "cost_saved": round(saved, 2)
        })

    avg_cost_saved = total_cost_saved / inefficient_count if inefficient_count else 0

    ineff_table = []
    for r in routes:
        try:
            delay = (r.actual_delivery_time - r.expected_delivery_time).total_seconds() / 3600.0
        except Exception:
            delay = "N/A"
        ineff_table.append({
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

    # Generate chart URL
    chart_url = generate_cost_waste_chart(cost_table, file_id) if cost_table else None

    return {
        "file_name": file.filename,
        "upload_date": file.upload_date,
        "user_name": f"{user.first_name} {user.last_name}",
        "user_email": user.email,
        "inefficient_routes": inefficient_count,
        "total_delayed_hours": round(total_delay, 2),
        "avg_delayed_hours": round(avg_delay, 2),
        "total_time_saved": round(total_saved, 2),
        "avg_time_saved": round(avg_saved, 2),
        "total_cost_saved": round(total_cost_saved, 2),
        "avg_cost_saved": round(avg_cost_saved, 2),
        "ineff_table": ineff_table,
        "cost_table": cost_table,
        "chart_url": chart_url
    }
