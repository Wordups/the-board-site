# weather.py
"""
Weather gate (Rule #4). Downgrades HR/TB in cold or in-wind.
Boosts K props in the same conditions. Data via open-meteo (no key).
"""
import requests
from datetime import datetime
from math import cos, radians

VENUE_META = {
    "Yankee Stadium":              {"lat": 40.8296, "lon": -73.9262, "cf": 48,  "dome": False},
    "Fenway Park":                 {"lat": 42.3467, "lon": -71.0972, "cf": 57,  "dome": False},
    "Wrigley Field":               {"lat": 41.9484, "lon": -87.6553, "cf": 36,  "dome": False},
    "Target Field":                {"lat": 44.9817, "lon": -93.2776, "cf": 90,  "dome": False},
    "Citi Field":                  {"lat": 40.7571, "lon": -73.8458, "cf": 40,  "dome": False},
    "Oriole Park at Camden Yards": {"lat": 39.2840, "lon": -76.6217, "cf": 60,  "dome": False},
    "Kauffman Stadium":            {"lat": 39.0517, "lon": -94.4803, "cf": 45,  "dome": False},
    "Coors Field":                 {"lat": 39.7559, "lon": -104.9942,"cf": 0,   "dome": False},
    "PNC Park":                    {"lat": 40.4469, "lon": -80.0057, "cf": 120, "dome": False},
    "Great American Ball Park":    {"lat": 39.0975, "lon": -84.5068, "cf": 40,  "dome": False},
    "Nationals Park":              {"lat": 38.8730, "lon": -77.0074, "cf": 25,  "dome": False},
    "Citizens Bank Park":          {"lat": 39.9061, "lon": -75.1665, "cf": 15,  "dome": False},
    "Dodger Stadium":              {"lat": 34.0739, "lon": -118.2400,"cf": 30,  "dome": False},
    "Petco Park":                  {"lat": 32.7073, "lon": -117.1566,"cf": 0,   "dome": False},
    "Oracle Park":                 {"lat": 37.7786, "lon": -122.3893,"cf": 90,  "dome": False},
    "T-Mobile Park":               {"lat": 47.5914, "lon": -122.3325,"cf": 45,  "dome": False},
    "Angel Stadium":               {"lat": 33.8003, "lon": -117.8827,"cf": 30,  "dome": False},
    "Truist Park":                 {"lat": 33.8906, "lon": -84.4677, "cf": 40,  "dome": False},
    "Busch Stadium":               {"lat": 38.6226, "lon": -90.1928, "cf": 30,  "dome": False},
    "Progressive Field":           {"lat": 41.4962, "lon": -81.6852, "cf": 20,  "dome": False},
    "Comerica Park":                {"lat": 42.3390, "lon": -83.0485, "cf": 120, "dome": False},
    "Rate Field":                  {"lat": 41.8299, "lon": -87.6338, "cf": 45,  "dome": False},
    "Sutter Health Park":          {"lat": 38.5803, "lon": -121.5133,"cf": 90,  "dome": False},
    "Globe Life Field":            {"lat": 32.7473, "lon": -97.0847, "cf": 0,   "dome": True},
    "Minute Maid Park":            {"lat": 29.7572, "lon": -95.3558, "cf": 0,   "dome": True},
    "Daikin Park":                 {"lat": 29.7572, "lon": -95.3558, "cf": 0,   "dome": True},
    "Rogers Centre":               {"lat": 43.6414, "lon": -79.3894, "cf": 0,   "dome": True},
    "Tropicana Field":             {"lat": 27.7683, "lon": -82.6534, "cf": 0,   "dome": True},
    "loanDepot park":              {"lat": 25.7781, "lon": -80.2197, "cf": 0,   "dome": True},
    "loanDepot Park":              {"lat": 25.7781, "lon": -80.2197, "cf": 0,   "dome": True},
    "American Family Field":       {"lat": 43.0280, "lon": -87.9712, "cf": 0,   "dome": True},
    "Chase Field":                 {"lat": 33.4455, "lon": -112.0667,"cf": 0,   "dome": True},
}


def _wind_to_cf(wind_dir_deg, cf_bearing):
    """Positive = wind toward CF (out, hitter friendly). Negative = in."""
    wind_going = (wind_dir_deg + 180) % 360
    diff = (wind_going - cf_bearing + 360) % 360
    if diff > 180: diff -= 360
    return cos(radians(diff))


def fetch_game_weather(venue_name, game_time_utc):
    meta = VENUE_META.get(venue_name)
    if meta is None:
        return {"ok": False, "reason": f"unknown_venue:{venue_name}"}
    if meta["dome"]:
        return {"ok": True, "is_dome": True, "temp_f": 72, "wind_mph": 0,
                "wind_dir": 0, "precip_prob": 0, "cf_component": 0, "reason": "dome"}
    try:
        hour_str = None
        if game_time_utc:
            gt = datetime.fromisoformat(game_time_utc.replace("Z", "+00:00"))
            hour_str = gt.strftime("%Y-%m-%dT%H:00")
        url = ("https://api.open-meteo.com/v1/forecast"
               f"?latitude={meta['lat']}&longitude={meta['lon']}"
               "&hourly=temperature_2m,wind_speed_10m,wind_direction_10m,"
               "precipitation_probability"
               "&temperature_unit=fahrenheit&wind_speed_unit=mph"
               "&timezone=UTC&forecast_days=2")
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        hours = data.get("hourly", {}).get("time", [])
        idx = 0
        if hour_str:
            for i, h in enumerate(hours):
                if h.startswith(hour_str[:13]):
                    idx = i; break
        temp_f = data["hourly"]["temperature_2m"][idx]
        wind_mph = data["hourly"]["wind_speed_10m"][idx]
        wind_dir = data["hourly"]["wind_direction_10m"][idx]
        precip = data["hourly"]["precipitation_probability"][idx]
        return {"ok": True, "is_dome": False, "temp_f": temp_f,
                "wind_mph": wind_mph, "wind_dir": wind_dir, "precip_prob": precip,
                "cf_component": _wind_to_cf(wind_dir, meta["cf"]), "reason": "ok"}
    except Exception as e:
        return {"ok": False, "reason": f"weather_api_failed:{e}"}


def weather_multiplier(weather, prop_type="hr"):
    flags = []
    if not weather.get("ok") or weather.get("is_dome"):
        return 1.00, ["dome_or_unavailable"]

    temp = weather.get("temp_f", 70)
    wind = weather.get("wind_mph", 0)
    cf_comp = weather.get("cf_component", 0)
    precip = weather.get("precip_prob", 0)

    if prop_type == "k":
        mult = 1.00
        if temp < 50:
            mult += 0.05; flags.append("k_cold_boost")
        if wind >= 10 and cf_comp < -0.3:
            mult += 0.05; flags.append("k_wind_in_boost")
        return round(max(0.5, min(1.15, mult)), 3), flags

    mult = 1.00
    if prop_type in {"hr", "tb"}:
        if temp < 45:
            mult -= 0.12; flags.append(f"cold:{int(temp)}F")
        elif temp < 55:
            mult -= 0.06; flags.append(f"cool:{int(temp)}F")
        elif temp >= 85:
            mult += 0.04; flags.append(f"hot:{int(temp)}F")

    wind_factor = 0.015 if prop_type == "hr" else 0.008
    if wind >= 8:
        effect = cf_comp * wind * wind_factor
        mult += max(-0.15, min(0.15, effect))
        direction = "out" if cf_comp > 0.3 else "in" if cf_comp < -0.3 else "cross"
        flags.append(f"wind_{direction}_{int(wind)}mph")

    if precip >= 60:
        mult -= 0.08; flags.append(f"rain_risk_{int(precip)}%")
    elif precip >= 30:
        flags.append(f"rain_watch_{int(precip)}%")

    return round(max(0.5, min(1.15, mult)), 3), flags
