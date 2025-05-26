from flask import Flask, request, jsonify
import paho.mqtt.publish as publish
import json
import os
from models import Device, db
import dotenv

dotenv.load_dotenv()

app = Flask(__name__)

MQTT_BROKER = os.getenv('MQTT_BROKER')
MQTT_PORT = int(os.getenv('MQTT_PORT', 1883))
MQTT_USERNAME = os.getenv('MQTT_USERNAME')
MQTT_PWD = os.getenv('MQTT_PWD')
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)


@app.route('/api/update_settings', methods=['POST'])
def update_settings():
    data = request.json
    board_id = data.get('board_id')
    api_key = data.get('api_key')
    settings = data.get('settings')

    if not board_id or not settings:
        return jsonify({"error": "Missing data"}), 400
    
    board = db.session.query(Device).filter_by(board_id=board_id, api_key=api_key).first()

    if not board:
        return jsonify({"error": "Invalid board_id or api_key"}), 403

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
            }
        )
        return jsonify({"message": "Settings sent via MQTT"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5001)
