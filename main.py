import sys
import os
import time
import json
import requests
from geopy.geocoders import Nominatim
import folium
from folium.plugins import HeatMap
from flask import Flask, request, render_template, jsonify
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.linear_model import LinearRegression

app = Flask(__name__)

OPENWEATHER_API_KEY = os.getenv('OPENWEATHER_API_KEY', '76ee506d882ad9c3ec73bec4a5027d7c')  # Fallback to your key
if not OPENWEATHER_API_KEY:
    raise ValueError("Please set OPENWEATHER_API_KEY in your environment")

CHARTS_FOLDER = 'static/charts'
CACHE_FOLDER = 'cache'
for folder in [CHARTS_FOLDER, CACHE_FOLDER]:
    if not os.path.exists(folder):
        os.makedirs(folder)
app.config['CHARTS_FOLDER'] = CHARTS_FOLDER

LANGUAGES = {
    'en': {'title': 'JuaNuru - Solar Feasibility', 'address_prompt': 'Enter your address or place name:', 'submit': 'Submit', 'results': 'Results', 'solar_score': 'Solar Score', 'live_data': 'Live Solar Data', 'potential_map': 'Solar Potential Map', 'unelectrified': 'Unelectrified Communities', 'impact': 'Impact Estimate', 'elevation': 'Elevation (m)', 'peak_sun_hours': 'Peak Sun Hours (kWh/m²/day)', 'potential_savings': 'Potential Monthly Savings', 'recommended_system': 'Recommended System Size (kW)', 'roi': 'Estimated ROI (years)', 'carbon_offset': 'Carbon Offset (kg CO₂/year)', 'priority_index': 'Priority Index', 'error': 'Invalid location or data unavailable.', 'currency_label': 'Currency'},
    'sw': {'title': 'JuaNuru - Uwezekano wa Jua', 'address_prompt': 'Weka anwani yako au jina la mahali:', 'submit': 'Wasilisha', 'results': 'Matokeo', 'solar_score': 'Alama za Jua', 'live_data': 'Data ya Jua ya Moja kwa Moja', 'potential_map': 'Ramani ya Uwezekano wa Jua', 'unelectrified': 'Jamii Zisizo na Umeme', 'impact': 'Makadirio ya Athari', 'elevation': 'Mwinuko (m)', 'peak_sun_hours': 'Saa za Jua za Kilele (kWh/m²/siku)', 'potential_savings': 'Akiba ya Kila Mwezi ya Potensia', 'recommended_system': 'Ukubwa wa Mfumo Unaopendekezwa (kW)', 'roi': 'ROI ya Kukadiriwa (miaka)', 'carbon_offset': 'Kupunguza Kaboni (kg CO₂/mwaka)', 'priority_index': 'Kiwango cha Kipaumbele', 'error': 'Mahali pasipofaa au data haipatikani.', 'currency_label': 'Sarafu'}
}

def convert_currency(amount, from_currency='USD', to_currency='KSH'):
    rates = {'USD': 1, 'KSH': 130, 'EUR': 0.91}
    usd_amount = amount / rates[from_currency]
    return round(usd_amount * rates[to_currency], 2)

def save_to_cache(key, data):
    with open(os.path.join(CACHE_FOLDER, f"{key}.json"), 'w') as f:
        json.dump(data, f)

def read_from_cache(key):
    cache_file = os.path.join(CACHE_FOLDER, f"{key}.json")
    if os.path.exists(cache_file) and (time.time() - os.path.getmtime(cache_file)) < 86400:
        with open(cache_file, 'r') as f:
            return json.load(f)
    return None

def fetch_with_retry(url, retries=3, delay=2, cache_key=None):
    if cache_key and (cached := read_from_cache(cache_key)):
        return cached
    for attempt in range(retries):
        try:
            response = requests.get(url, timeout=15)
            response.raise_for_status()
            data = response.json()
            if cache_key:
                save_to_cache(cache_key, data)
            return data
        except Exception as e:
            print(f"Attempt {attempt + 1} failed: {e}")
            if attempt < retries - 1:
                time.sleep(delay)
    return None

def get_coordinates(place):
    cache_key = f"coords_{place.lower().replace(' ', '_')}"
    if cached := read_from_cache(cache_key):
        return cached['lat'], cached['lon']
    geolocator = Nominatim(user_agent="juanuru")
    location = geolocator.geocode(place)
    if location:
        data = {'lat': location.latitude, 'lon': location.longitude}
        save_to_cache(cache_key, data)
        return data['lat'], data['lon']
    return None, None

def get_elevation(lat, lon):
    url = f"https://api.open-meteo.com/v1/elevation?latitude={lat}&longitude={lon}"
    data = fetch_with_retry(url, cache_key=f"elev_{lat}_{lon}")
    return data['elevation'][0] if data and 'elevation' in data else 0

def get_solar_irradiance(lat, lon):
    url = f"https://power.larc.nasa.gov/api/temporal/daily/point?parameters=ALLSKY_SFC_SW_DWN&community=RE&latitude={lat}&longitude={lon}&start=20230101&end=20240331&format=JSON"
    data = fetch_with_retry(url, cache_key=f"irr_{lat}_{lon}")
    if data and 'properties' in data:
        irradiance = [float(v) for v in data['properties']['parameter']['ALLSKY_SFC_SW_DWN'].values() if v >= 0]
        if irradiance:
            return irradiance
    return [5.5] * 365  # Mock fallback

def get_cloud_cover(lat, lon):
    url = f"https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={OPENWEATHER_API_KEY}"
    data = fetch_with_retry(url, cache_key=f"weather_{lat}_{lon}")
    return data['clouds']['all'] if data and 'clouds' in data else 50

def get_electrification_status(lat, lon):
    mock_data = {(-1.28, 36.81): {"population": 50000, "electrified": False}, (-4.05, 39.67): {"population": 30000, "electrified": True}}
    for (mock_lat, mock_lon), info in mock_data.items():
        if abs(lat - mock_lat) < 0.5 and abs(lon - mock_lon) < 0.5:
            return info
    return {"population": 1000, "electrified": False}

def generate_map(lat, lon, solar_data, unelectrified_data):
    m = folium.Map(location=[lat, lon], zoom_start=8)
    valid_solar_data = [d for d in solar_data if len(d) == 3 and all(isinstance(x, (int, float)) and not np.isnan(x) for x in d)]
    if not valid_solar_data:
        print("No valid solar data, using fallback")
        valid_solar_data = [[lat, lon, 1.0]]
    
    weights = [float(d[2]) for d in valid_solar_data]
    max_weight = max(weights) if weights else 1.0
    normalized_solar_data = [[float(d[0]), float(d[1]), float(min(d[2] / max_weight, 1.0))] for d in valid_solar_data]
    
    try:
        HeatMap(normalized_solar_data, radius=15, gradient={0.4: 'blue', 0.65: 'yellow', 1.0: 'red'}).add_to(m)
    except Exception as e:
        print(f"Map rendering error: {e}")
        folium.Marker([lat, lon], popup=f"Center: {lat}, {lon}").add_to(m)
    
    for u_lat, u_lon, pop in unelectrified_data:
        if isinstance(u_lat, (int, float)) and isinstance(u_lon, (int, float)) and isinstance(pop, (int, float)):
            folium.Marker([u_lat, u_lon], popup=f"Pop: {pop} (Unelectrified)", icon=folium.Icon(color='red')).add_to(m)
    
    return m._repr_html_()

def generate_chart(irradiance):
    plt.figure(figsize=(10, 6))
    sns.lineplot(data=irradiance[:12], color='orange', linewidth=2.5)
    plt.title("Monthly Solar Irradiance (kWh/m²/day)")
    chart_path = os.path.join(app.config['CHARTS_FOLDER'], 'monthly_chart.png')
    plt.savefig(chart_path, dpi=100)
    plt.close()
    return 'monthly_chart.png'  # Fixed to match URL

def ai_recommendation(irradiance, cloud_cover, energy_cost=0.15):
    model = LinearRegression()
    X = np.array(range(len(irradiance))).reshape(-1, 1)
    y = np.array(irradiance)
    model.fit(X, y)
    system_size = np.mean(irradiance) * 0.3 * (1 - cloud_cover / 100)
    savings = system_size * energy_cost * 30
    jobs = round(system_size * 0.1, 2)
    households = round(system_size * 2)
    return {"size": round(system_size, 2), "savings": round(savings, 2), "jobs": jobs, "households": households}

def calculate_priority_index(solar_score, population, electrified):
    return solar_score * (1 if not electrified else 0.5) * min(population / 1000, 10)

@app.route('/', methods=['GET'])
def home():
    lang = request.args.get('lang', 'en')
    return render_template('index.html', lang=lang, translations=LANGUAGES[lang])

@app.route('/results', methods=['GET', 'POST'])
def results():
    if request.method == 'GET':
        lang = request.args.get('lang', 'en')
        default_data = {"place": "Unknown", "lat": 0, "lon": 0, "elevation": 0, "solar_score": 0, "badge": "Sun Starter", "peak_sun_hours": 0, "map_html": "<p>No map available</p>", "chart_path": "", "potential_savings": 0, "recommended_system": 0, "roi": "N/A", "carbon_offset": 0, "currency": "KSH", "lang": lang, "jobs": 0, "households": 0, "priority_index": 0, "population": 0, "electrified": True}
        return render_template('results.html', lang=lang, translations=LANGUAGES[lang], data=default_data)

    lang = request.form.get('lang', 'en')
    currency = request.form.get('currency', 'KSH')
    place = request.form.get('place')
    energy_cost_usd = float(request.form.get('energy_cost', 0.15))

    lat, lon = get_coordinates(place)
    if not lat or not lon:
        return render_template('error.html', lang=lang, translations=LANGUAGES[lang])

    elevation = get_elevation(lat, lon)
    irradiance = get_solar_irradiance(lat, lon)
    cloud_cover = get_cloud_cover(lat, lon)
    electrification_info = get_electrification_status(lat, lon)

    solar_score = min(100, int(np.mean(irradiance) * 20 * (1 - cloud_cover / 200)))
    badge = "Solar Superstar" if solar_score > 90 else "Eco Warrior" if solar_score > 70 else "Sun Starter"
    ai_rec = ai_recommendation(irradiance, cloud_cover, energy_cost_usd)
    savings_converted = convert_currency(ai_rec["savings"], 'USD', currency)
    roi = round(2000 / ai_rec["savings"], 1) if ai_rec["savings"] > 0 else "N/A"
    priority_index = calculate_priority_index(solar_score, electrification_info["population"], electrification_info["electrified"])

    solar_data = [(lat + i*0.1, lon + j*0.1, np.mean(irradiance)*(1 - cloud_cover/100)) for i in range(-2, 3) for j in range(-2, 3)]
    unelectrified_data = [(lat + 0.2, lon + 0.2, 1000), (lat - 0.3, lon - 0.3, 500)] if not electrification_info["electrified"] else []
    map_html = generate_map(lat, lon, solar_data, unelectrified_data)
    chart_path = generate_chart(irradiance)

    data = {"place": place, "lat": lat, "lon": lon, "elevation": elevation, "solar_score": solar_score, "badge": badge, "peak_sun_hours": round(np.mean(irradiance), 2), "map_html": map_html, "chart_path": chart_path, "potential_savings": savings_converted, "recommended_system": ai_rec["size"], "roi": roi, "carbon_offset": solar_score * 5, "currency": currency, "lang": lang, "jobs": ai_rec["jobs"], "households": ai_rec["households"], "priority_index": round(priority_index, 1), "population": electrification_info["population"], "electrified": electrification_info["electrified"]}
    
    script = f"<script>localStorage.setItem('lastResults', JSON.stringify({json.dumps(data)}));</script>"
    return render_template('results.html', lang=lang, translations=LANGUAGES[lang], data=data) + script

@app.route('/live', methods=['GET'])
def live_data():
    try:
        lat, lon = float(request.args['lat']), float(request.args['lon'])
        url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true"  # Fixed typo
        data = fetch_with_retry(url)
        return jsonify(data['current_weather'] if data else {'temperature': 'N/A', 'windspeed': 'N/A'})
    except Exception as e:
        print(f"Live data error: {e}")
        return jsonify({'temperature': 'N/A', 'windspeed': 'N/A'})

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=True)