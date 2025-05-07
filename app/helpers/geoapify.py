from urllib.parse import quote_plus

import requests
from flask import current_app

from app import db


def get_coordinates(address):
    """
       Convert a free-form address into geographic coordinates (latitude, longitude)
       using the Geoapify Geocoding API.
    """
    try:
        # URL-encode the address to safely include it in the API request
        encoded_address = quote_plus(address)
        api_key = current_app.config['GEOAPIFY_API_KEY']
        # Build the geocoding API URL with parameters for language, result limit, and format
        url = (
            f"https://api.geoapify.com/v1/geocode/search"
            f"?text={encoded_address}"
            f"&apiKey={api_key}"
            f"&lang=vi&limit=1&format=json"
        )
        headers = {"Accept": "application/json"}
        resp = requests.get(url, headers=headers)
        # If the request succeeds, parse out the first result’s lat/lon
        if resp.status_code == 200:
            data = resp.json()
            if data.get("results"):
                r = data["results"][0]
                return r.get("lat"), r.get("lon")
    except Exception as e:
        # Log any errors (network issues, parsing errors, etc.)
        print("Error geocoding:", e)
    # Return None if geocoding fails
    return None


def get_optimized_route_time(base_address, shipping_address):
    """
        Fetch the optimized drive time (in hours) between two addresses
        using Geoapify’s Routing API.
    """
    # First, obtain coordinates for both endpoints
    start_coords = get_coordinates(base_address)
    end_coords = get_coordinates(shipping_address)
    if not start_coords or not end_coords:
        return None

    api_key = current_app.config['GEOAPIFY_API_KEY']
    # Build the routing API URL with drive mode, shortest path, and metric units
    url = (
        f"https://api.geoapify.com/v1/routing"
        f"?waypoints={start_coords[0]},{start_coords[1]}|{end_coords[0]},{end_coords[1]}"
        f"&mode=drive&type=short&units=metric"
        f"&apiKey={api_key}"
        f"&limit=1&format=json"
    )
    headers = {"Accept": "application/json"}
    try:
        resp = requests.get(url, headers=headers)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("results"):
                # time is in seconds
                secs = data["results"][0].get("time")
                if secs is not None:
                    return secs / 3600.0
    except Exception as e:
        print("Error fetching route:", e)
    return None


def update_cached_routes(routes):
    """
        For each InefficientRoute without optimization data, call the routing API,
        compare the optimized time to the actual delivery duration,
        and store any time savings back into the database.
    """
    updated = False

    for r in routes:
        # Only process if we haven't already computed optimized time or savings
        if r.optimized_delivery_time is None or r.time_saved is None:
            opt_time = get_optimized_route_time(r.base_address, r.shipping_address)
            if opt_time is not None:
                # Calculate actual delivery duration in hours
                actual_dur = (r.actual_delivery_time - r.starting_time).total_seconds() / 3600.0
                # Only record savings if optimized route is faster
                if actual_dur > opt_time:
                    r.optimized_delivery_time = round(opt_time, 2)
                    r.time_saved = round(actual_dur - opt_time, 2)
                    updated = True

    # If any routes were updated, commit them in one batch
    if updated:
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            print("Error committing route updates:", e)
