import sys
# Ensure Replit finds user-installed packages
sys.path.append('/home/runner/.local/lib/python3.9/site-packages')

import requests
from geopy.geocoders import Nominatim
import folium
from flask import Flask, request, render_template, redirect, url_for, jsonify, send_file
import numpy as np
import pandas as pd
from io import BytesIO
import base64
import os
import time
from datetime import datetime
import json
import matplotlib.pyplot as plt
import seaborn as sns
from werkzeug.utils import secure_filename
import cv2  # For AR processing
from sklearn.linear_model import LinearRegression  # For AI recommendations
from reportlab.lib.pagesizes import letter  # For PDF generation
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image
from reportlab.lib.styles import getSampleStyleSheet

app = Flask(__name__)

# Configurations
METEOSTAT_API_KEY = os.getenv('METEOSTAT_API_KEY', 'your-api-key-here')  # Replace with real key if available
UPLOAD_FOLDER = 'static/uploads'
CHARTS_FOLDER = 'static/charts'
CACHE_FOLDER = 'cache'
for folder in [UPLOAD_FOLDER, CHARTS_FOLDER, CACHE_FOLDER]:
    if not os.path.exists(folder):
        os.makedirs(folder)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['CHARTS_FOLDER'] = CHARTS_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

# Language support (English only for brevity; expand as needed)
LANGUAGES = {
    'en': {
        'title': 'JuaNuru - Solar Feasibility',
        'address_prompt': 'Enter your address or place name:',
        'submit': 'Submit',
        'results': 'Results',
        'solar_score': 'Solar Score',
        'live_data': 'Live Solar Data',
        'financing': 'Financing Options',
        'share': 'Share Your Results',
        'elevation': 'Elevation (m)',
        'peak_sun_hours': 'Peak Sun Hours (kWh/m²/day)',
        'potential_savings': 'Potential Monthly Savings (USD)',
        'recommended_system': 'Recommended System Size (kW)',
        'roi': 'Estimated ROI (years)',
        'carbon_offset': 'Carbon Offset (kg CO₂/year)',
        'error': 'Invalid location or data unavailable.',
    }
}

# Cache helpers
def save_to_cache(key, data):
    with open(os.path.join(CACHE_FOLDER, f"{key}.json"), 'w') as f:
        json.dump(data, f)

def read_from_cache(key):
    cache_file = os.path.join(CACHE_FOLDER, f"{key}.json")
    if os.path.exists(cache_file) and (time.time() - os.path.getmtime(cache_file)) < 86400:
        with open(cache_file, 'r') as f:
            return json.load(f)
    return None

# API fetch with retry
def fetch_with_retry(url, headers=None, retries=3, delay=2, cache_key=None):
    if cache_key and (cached := read_from_cache(cache_key)):
        return cached
    for attempt in range(retries):
        try:
            response = requests.get(url, headers=headers, timeout=15)
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

# Helper functions (simplified for MVP)
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
    return data['elevation'][0] if data and 'elevation' in data else None

def get_solar_irradiance(lat, lon):
    current_year = datetime.now().year
    url = f"https://power.larc.nasa.gov/api/temporal/daily/point?parameters=ALLSKY_SFC_SW_DWN&latitude={lat}&longitude={lon}&start={current_year-1}0101&end={current_year}1231&format=JSON"
    data = fetch_with_retry(url, cache_key=f"irr_{lat}_{lon}")
    if data and 'properties' in data:
        irradiance = [float(v) for v in data['properties']['parameter']['ALLSKY_SFC_SW_DWN'].values() if v != '-999']
        return irradiance
    return None

def generate_map(lat, lon):
    m = folium.Map(location=[lat, lon], zoom_start=10)
    folium.Marker([lat, lon]).add_to(m)
    return m._repr_html_()

def generate_chart(irradiance):
    plt.figure(figsize=(10, 6))
    sns.lineplot(data=irradiance[:12])  # First 12 months for simplicity
    plt.title("Monthly Solar Irradiance")
    chart_path = os.path.join(app.config['CHARTS_FOLDER'], 'monthly_chart.png')
    plt.savefig(chart_path)
    plt.close()
    return chart_path

def process_ar_image(photo_path):
    img = cv2.imread(photo_path)
    height, width = img.shape[:2]
    cv2.rectangle(img, (width//4, height//4), (3*width//4, 3*height//4), (0, 0, 255), 2)
    ar_path = os.path.join(app.config['UPLOAD_FOLDER'], 'ar_' + os.path.basename(photo_path))
    cv2.imwrite(ar_path, img)
    return ar_path

def ai_recommendation(irradiance, energy_cost=0.15):
    model = LinearRegression()
    X = np.array(range(len(irradiance))).reshape(-1, 1)
    y = np.array(irradiance)
    model.fit(X, y)
    system_size = np.mean(irradiance) * 0.3
    savings = system_size * energy_cost * 30
    return {"size": round(system_size, 2), "savings": round(savings, 2)}

def generate_pdf(data):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    story = [
        Paragraph("JuaNuru Solar Report", styles['Title']),
        Spacer(1, 12),
        Paragraph(f"Solar Score: {data['solar_score']}", styles['Normal']),
        Image(os.path.join(app.config['CHARTS_FOLDER'], 'monthly_chart.png'), width=400, height=300)
    ]
    doc.build(story)
    buffer.seek(0)
    return buffer

# Routes
@app.route('/', methods=['GET'])
def home():
    lang = request.args.get('lang', 'en')
    return render_template('index.html', lang=lang, translations=LANGUAGES[lang])

@app.route('/results', methods=['POST'])
def results():
    lang = request.form.get('lang', 'en')
    place = request.form.get('place')
    energy_cost = float(request.form.get('energy_cost', 0.15))
    photo = request.files.get('photo')

    lat, lon = get_coordinates(place)
    if not lat or not lon:
        return render_template('error.html', lang=lang, translations=LANGUAGES[lang])

    elevation = get_elevation(lat, lon) or 0
    irradiance = get_solar_irradiance(lat, lon) or [0] * 365
    map_html = generate_map(lat, lon)
    chart_path = generate_chart(irradiance)

    solar_score = min(100, int(np.mean(irradiance) * 20))
    badge = "Solar Superstar" if solar_score > 90 else "Eco Warrior" if solar_score > 70 else "Sun Starter"
    ai_rec = ai_recommendation(irradiance, energy_cost)
    ar_image = process_ar_image(photo.save(os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(photo.filename)))) if photo else None

    data = {
        "place": place, "lat": lat, "lon": lon, "elevation": elevation,
        "solar_score": solar_score, "badge": badge, "peak_sun_hours": round(np.mean(irradiance), 2),
        "map_html": map_html, "chart_path": chart_path.split('/')[-1],
        "potential_savings": ai_rec["savings"], "recommended_system": ai_rec["size"],
        "roi": round(1000 / ai_rec["savings"], 1), "carbon_offset": solar_score * 5,
        "ar_image": ar_image.split('/')[-1] if ar_image else None
    }
    return render_template('results.html', lang=lang, translations=LANGUAGES[lang], data=data)

@app.route('/live', methods=['GET'])
def live_data():
    lat, lon = float(request.args['lat']), float(request.args['lon'])
    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true"
    data = fetch_with_retry(url)
    return jsonify(data['current_weather'] if data else {})

@app.route('/download', methods=['GET'])
def download():
    data = json.loads(request.args.get('data', '{}'))
    pdf = generate_pdf(data)
    return send_file(pdf, as_attachment=True, download_name="juanuru_report.pdf")

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000, debug=True)