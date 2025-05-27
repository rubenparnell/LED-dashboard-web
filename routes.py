from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_user, login_required, logout_user, current_user
import requests
import json
import os
import paho.mqtt.publish as publish
import ssl
from models import User, Device, UserDeviceLink
from models import db

main = Blueprint('main', __name__)

MQTT_BROKER = os.getenv('MQTT_BROKER')
MQTT_PORT = int(os.getenv('MQTT_PORT', 1883))
MQTT_USERNAME = os.getenv('MQTT_USERNAME')
MQTT_PWD = os.getenv('MQTT_PWD')

# Fetch station names
stations = json.loads(requests.get("https://metro-rti.nexus.org.uk/api/stations").text)

# utils
def load_settings(board_id):
    settings = db.session.query(Device.settings).filter_by(board_id=board_id).first()
    if settings[0] != None:
        return settings[0]
    else:
        return {
            "station1": "TYN",
            "platform1": "1",
            "station2": "TYN",
            "platform2": "2",
            "lat": 0.0,
            "lon": 0.0,
            "forecast_hours": [9, 12, 15, 18]
        }


def convertStationCode(code):
    return stations.get(code, "Unknown")


# Routes
@main.route('/')
def home():
    if current_user.is_authenticated:
        devices = db.session.query(UserDeviceLink).filter_by(user_id=current_user.id).all()
        user_devices = [device.device for device in devices]

        return render_template('dashboard.html', devices=user_devices)
    else:
        return render_template('home.html')


@main.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        password2 = request.form['password2']
        if User.query.filter_by(email=email).first():
            flash('Email address already exists', 'danger')
            return redirect(url_for('main.register'))
        
        if password != password2:
            flash('The passwords entered do not match!', 'danger')
            return redirect(url_for('main.register'))
        
        user = User(email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        flash('Registration successful. Please log in.', 'success')
        return redirect(url_for('main.login'))
    return render_template('register.html')

@main.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        user = User.query.filter_by(email=email).first()
        if not user or not user.check_password(password):
            flash('Invalid credentials', 'danger')
            return redirect(url_for('main.login'))
        login_user(user)
        return redirect(url_for('main.home'))
    return render_template('login.html')

@main.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('main.home'))


@main.route('/link-device', methods=['GET', 'POST'])
@login_required
def link_device():
    if request.method == 'POST':
        board_id = request.form.get('board_id')

        device = Device.query.filter_by(board_id=board_id).first()

        if not device:
            flash('Device not found.', 'danger')
        else:
            currentDevices = UserDeviceLink.query.filter_by(user_id=current_user.id, device_id=device.id).all()

            if len(currentDevices) > 0:
                flash('You have already linked that board to your account!', 'danger')
                return redirect(url_for('main.link_device'))
            
            new_link = UserDeviceLink(user_id=current_user.id, device_id=device.id)
            db.session.add(new_link)
            db.session.commit()
            flash('Device linked successfully.', 'success')
            return redirect(url_for('main.link_device'))

    return render_template('link_device.html')



@main.route('/update_settings', methods=['GET', 'POST'])
def update_settings():
    if request.method == 'POST':
        station1 = request.form['station1']
        platform1 = request.form['platform1']
        station2 = request.form['station2']
        platform2 = request.form['platform2']
        lat = request.form.get('lat', 0)
        lon = request.form.get('lon', 0)
        forecast_hours = request.form.get('forecast_hours', "9,12,15,18").split(",")
        board_id = request.form.get('board_id')

        device = db.session.query(Device).filter_by(board_id=board_id).first()

        settings = {
            "station1": station1,
            "platform1": platform1,
            "station2": station2,
            "platform2": platform2,
            "lat": lat,
            "lon": lon,
            "forecast_hours": forecast_hours 
        }

        topic = f"boards/{board_id}/settings"
        payload = json.dumps(settings)

        try:
            publish.single(
                topic,
                payload,
                hostname=MQTT_BROKER,
                port=MQTT_PORT,
                auth={
                    'username': MQTT_USERNAME,
                    'password': MQTT_PWD
                },
                tls={
                    'tls_version': ssl.PROTOCOL_TLSv1_2
                }
            )

            device.settings = settings
            db.session.commit()

            flash('Settings sent successfully!', 'success')
        except Exception as e:
            flash('Failed to send settings.', 'danger')

        return redirect('/update_settings')
    
    boardSettings = {}

    devices = db.session.query(UserDeviceLink).filter_by(user_id=current_user.id).all()

    for device in devices:
        board_id = device.device.board_id
        settings = load_settings(board_id)

        # Convert station codes to names for pre-filled form values
        station1_name = convertStationCode(settings["station1"])
        station2_name = convertStationCode(settings["station2"])

        # Convert forecast hours list to comma-separated string for form input
        forecast_hours_str = ",".join(str(h) for h in settings.get("forecast_hours", []))

        boardSettings[board_id] = {
            "station1": station1_name,
            "station1_code": settings["station1"],
            "platform1": settings["platform1"],
            "station2": station2_name,
            "station2_code": settings["station2"],
            "platform2": settings["platform2"],
            "lat": settings["lat"],
            "lon": settings["lon"],
            "forecast_hours": forecast_hours_str
        }
    


    return render_template(
        'update_settings.html',
        stations=stations,
        boardSettings=boardSettings,
        )


@main.route("/api/register-device", methods=["POST"])
def api_register_device():
    data = request.get_json()

    board_id = data.get("board_id")
    api_key = data.get("api_key")

    if not board_id or not api_key:
        return jsonify({"error": "Missing board_id or api_key"}), 400

    existing = Device.query.filter_by(board_id=board_id).first()
    if existing:
        return jsonify({"message": "Device already registered"}), 200

    new_device = Device(board_id=board_id, api_key=api_key)
    db.session.add(new_device)
    db.session.commit()

    return jsonify({"message": "Device registered"}), 200
