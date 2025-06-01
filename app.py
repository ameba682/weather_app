from flask import Flask, request, render_template, jsonify, session
import requests
import sqlite3
from flask_session import Session

app = Flask(__name__)
app.secret_key = 'your_secret_key'
app.config['SESSION_TYPE'] = 'filesystem'
Session(app)

DATABASE = 'db.sqlite'

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as db:
        db.execute('''
            CREATE TABLE IF NOT EXISTS search_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                city TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        db.execute('''
            CREATE TABLE IF NOT EXISTS city_stats (
                city TEXT PRIMARY KEY,
                count INTEGER DEFAULT 0
            )
        ''')

@app.before_first_request
def initialize():
    init_db()

@app.route('/', methods=['GET', 'POST'])
def index():
    if 'user_id' not in session:
        import uuid
        session['user_id'] = str(uuid.uuid4())

    weather_data = None
    city_name = ''
    if request.method == 'POST':
        city_name = request.form.get('city')
        if city_name:
            weather_data = get_weather(city_name)
            if weather_data:
                save_search(session['user_id'], city_name)
                increment_city_stat(city_name)
    history = get_user_history(session['user_id'])
    return render_template('index.html', weather=weather_data, history=history, last_city=city_name)

def save_search(user_id, city):
    with get_db() as db:
        db.execute('INSERT INTO search_history (user_id, city) VALUES (?, ?)', (user_id, city))

def get_user_history(user_id):
    with get_db() as db:
        rows = db.execute('SELECT DISTINCT city FROM search_history WHERE user_id=? ORDER BY timestamp DESC', (user_id,))
        return [row['city'] for row in rows]

def increment_city_stat(city):
    with get_db() as db:
        cursor = db.execute('SELECT count FROM city_stats WHERE city=?', (city,))
        row = cursor.fetchone()
        if row:
            db.execute('UPDATE city_stats SET count=? WHERE city=?', (row['count'] + 1, city))
        else:
            db.execute('INSERT INTO city_stats (city, count) VALUES (?, ?)', (city, 1))

def get_weather(city):
    geocode_url = f'https://nominatim.openstreetmap.org/search?city={city}&format=json&limit=1'
    response = requests.get(geocode_url)
    if response.status_code != 200:
        return None
    try:
        data = response.json()
    except ValueError:
        return None
    
    if not data:
        return None
    
    lat = data[0]['lat']
    lon = data[0]['lon']
    
    weather_url = f'https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true&hourly=temperature_2m'
    
    weather_response = requests.get(weather_url)
    if weather_response.status_code != 200:
        return None
    
    try:
        weather_json = weather_response.json()
    except ValueError:
        return None
    
    current_weather = weather_json.get('current_weather')
    
    if not current_weather:
        return None
    
    return {
        'temperature': current_weather['temperature'],
        'windspeed': current_weather['windspeed'],
        'time': current_weather['time']
    }

@app.route('/api/stats')
def api_stats():
    with get_db() as db:
        rows = db.execute('SELECT * FROM city_stats').fetchall()
        stats = {row['city']: row['count'] for row in rows}
        return jsonify(stats)

@app.route('/autocomplete')
def autocomplete():
    term = request.args.get('term', '')
    with get_db() as db:
        rows = db.execute("SELECT DISTINCT city FROM search_history WHERE city LIKE ?", (f'%{term}%',)).fetchall()
        suggestions = [row['city'] for row in rows]
        return jsonify(suggestions)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)