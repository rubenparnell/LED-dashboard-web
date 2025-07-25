from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, session
from flask_login import login_user, login_required, logout_user, current_user
import requests
import json
import os
import paho.mqtt.publish as publish
import ssl
import random
from models import User, Device, UserDeviceLink, Message
from models import db
from incoming_mqtt_handler import start_website_mqtt_listener, shared_state

main = Blueprint('main', __name__)
start_website_mqtt_listener()

MQTT_BROKER = os.getenv('MQTT_BROKER')
MQTT_PORT = int(os.getenv('MQTT_PORT', 1883))
MQTT_USERNAME = os.getenv('MQTT_USERNAME')
MQTT_PWD = os.getenv('MQTT_PWD')

# Fetch station names
stations = json.loads(requests.get("https://metro-rti.nexus.org.uk/api/stations").text)

# utils
def load_settings(board_id):
    settings, size = db.session.query(Device.settings, Device.size).filter_by(board_id=board_id).first()
    if settings != None:
        return settings
    else:
        if size == "large":
            return {
                "station1": "TYN",
                "platform1": "1",
                "station2": "TYN",
                "platform2": "2",
                "lat": 0.0,
                "lon": 0.0,
                "forecast_hours": [9, 12, 15, 18]
            }
        elif size == "small":
            return {
                "station": "TYN"
            }


def convertStationCode(code):
    return stations.get(code, "Unknown")


def get_contrast_background(hex_colour):
    hex_colour = hex_colour.lstrip("#")
    r, g, b = tuple(int(hex_colour[i:i+2], 16) for i in (0, 2, 4))
    brightness = (r * 299 + g * 587 + b * 114) / 1000  # Per W3C standard

    # Light text? Use dark background. Dark text? Use light background.
    return "#000000" if brightness > 128 else "#ffffff"


# Routes
@main.route('/')
def home():
    if current_user.is_authenticated:
        devices = db.session.query(UserDeviceLink).filter_by(user_id=current_user.id).all()
        user_devices = {}
        for device in devices:
            mode = shared_state.board_mode.get(device.device.board_id)
            user_devices[device.device.id] = mode

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
        
        user = User(email=email, colour="#{:06x}".format(random.randint(0, 0xFFFFFF)))
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

        # Handle session-stored board linking
        if session.get('pending_board_id'):
            return redirect(url_for('main.process_device_link'))
        
        next_page = request.args.get('next')
        return redirect(next_page or url_for('main.home'))
    return render_template('login.html')

@main.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('main.home'))


@main.route('/messages', methods=["GET", "POST"])
@login_required
def messages():
    if request.method == "POST":
        form_name = request.form.get("form_name")

        if form_name == "colour_form":
            userColour = request.form.get("userColour")

            # get user board links
            userBoards = UserDeviceLink.query.filter_by(user_id=current_user.id).all()
            for board in userBoards:
                publish.single(
                    f"boards/{board.device.board_id}/message",
                    "colour updated",
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

            current_user.colour = userColour
            db.session.commit()
            flash("Colour Updated.", "success")

        elif form_name == "message_form":
            board_id = request.form.get("board_id")
            message = request.form.get("message")
            if message:
                payload = {
                    "message":message
                }
                publish.single(
                    f"boards/{board_id}/message",
                    json.dumps(payload),
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

                msg = Message(user_id=current_user.id, board_id=board_id, message=message)
                db.session.add(msg)
                db.session.commit()
                flash("Message added.", "success")

        return redirect(url_for("main.messages"))

    # Get all device links for current user
    links = UserDeviceLink.query.filter_by(user_id=current_user.id).all()
    devices = [link.device for link in links]

    # Get messages for each linked device
    messages_by_device = {}
    for device in devices:
        messages = Message.query.filter_by(board_id=device.board_id).order_by(Message.id.desc()).all()
        for message in messages:
            user_colour = message.user.colour
            message.text_bg = get_contrast_background(user_colour)
        messages_by_device[device] = messages

    return render_template("messages.html", messages_by_device=messages_by_device, devices=devices)


@main.route("/messages/delete/<int:message_id>", methods=["POST"])
@login_required
def delete_message(message_id):
    msg = Message.query.get_or_404(message_id)
    if msg.user_id != current_user.id:
        flash("You cannot delete this message.", "danger")
        return redirect(url_for("main.messages"))

    payload = {"delete":message_id}
    publish.single(
        f"boards/{msg.board_id}/message",
        json.dumps(payload),
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
    db.session.delete(msg)
    db.session.commit()
    flash("Message deleted.", "success")
    return redirect(url_for("main.messages"))


@main.route("/get_messages/<board_id>")
def get_messages(board_id):
    messages = Message.query.filter_by(board_id=board_id).all()
    return jsonify({"messages": [{"text": message.message, "colour": message.user.colour} for message in messages]})


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


@main.route('/addBoard/<board_id>')
def new_device_link(board_id):
    session['pending_board_id'] = board_id
    if current_user.is_authenticated:
        return redirect(url_for('main.process_device_link'))
    else:
        # Redirect to login, after login they will be redirected back to process_device_link
        return redirect(url_for('main.login', next=url_for('main.process_device_link')))


@main.route('/process-device-link')
@login_required
def process_device_link():
    board_id = session.pop('pending_board_id', None)
    if not board_id:
        flash('No pending device to link.', 'warning')
        return redirect(url_for('main.link_device'))

    device = Device.query.filter_by(board_id=board_id).first()
    if not device:
        flash('Device not found.', 'danger')
        return redirect(url_for('main.link_device'))

    existing_link = UserDeviceLink.query.filter_by(user_id=current_user.id, device_id=device.id).first()
    if existing_link:
        flash('This device is already linked to your account.', 'info')
    else:
        new_link = UserDeviceLink(user_id=current_user.id, device_id=device.id)
        db.session.add(new_link)
        db.session.commit()
        flash('Device linked successfully!', 'success')

    return redirect(url_for('main.home'))


@main.route('/update_settings', methods=['GET', 'POST'])
def update_settings():
    if request.method == 'POST':
        board_id = request.form.get('board_id')
        device = db.session.query(Device).filter_by(board_id=board_id).first()
        size = request.form.get('size')
        board_name = request.form.get('board_name')
        device.name = board_name
        db.session.commit()

        if size == "large":
            station1 = request.form['station1']
            platform1 = request.form['platform1']
            station2 = request.form['station2']
            platform2 = request.form['platform2']
            lat = request.form.get('lat', 0)
            lon = request.form.get('lon', 0)
            forecast_hours = request.form.get('forecast_hours', "9,12,15,18").split(",")

            settings = {
                "station1": station1,
                "platform1": platform1,
                "station2": station2,
                "platform2": platform2,
                "lat": lat,
                "lon": lon,
                "forecast_hours": forecast_hours,
                "board_name": device.name
            }

        elif size == "small":
            station = request.form['station']

            settings = {
                "station": station,
                "board_name": device.name
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
    
    # Get Request:
    boardSettings = {}
    boards = {}

    devices = db.session.query(UserDeviceLink).filter_by(user_id=current_user.id).all()

    for device in devices:
        board_id = device.device.board_id
        settings = load_settings(board_id)

        if device.device.size == "large":
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
                "forecast_hours": forecast_hours_str,
                "board_name": device.device.name
            }

        elif device.device.size == "small":
            # Convert station codes to names for pre-filled form values
            station_name = convertStationCode(settings["station"])

            boardSettings[board_id] = {
                "station": station_name,
                "station_code": settings["station"],
                "board_name": device.device.name
            }

        boards[board_id] = device.device

    return render_template(
        'update_settings.html',
        stations=stations,
        boardSettings=boardSettings,
        boards=boards,
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
