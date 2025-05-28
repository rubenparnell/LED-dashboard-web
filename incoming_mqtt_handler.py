import paho.mqtt.client as mqtt
import ssl
import json
import os

class SharedState:
    board_mode = {}

shared_state = SharedState()

MQTT_BROKER = os.getenv("MQTT_BROKER")
MQTT_PORT = int(os.getenv("MQTT_PORT"))
MQTT_USERNAME = os.getenv("MQTT_USERNAME")
MQTT_PWD = os.getenv("MQTT_PWD")
BOARD_ID = os.getenv("BOARD_ID")

def on_connect(client, userdata, flags, rc):
    print("Website MQTT client connected with result code", rc)
    client.subscribe("#")

def on_message(client, userdata, msg):
    if msg.topic.startswith("board") and msg.topic.endswith("status"):
        board_id = msg.topic.split("/")[1]
        payload = json.loads(msg.payload.decode())
        shared_state.board_mode[board_id] = payload['mode']


def start_website_mqtt_listener():
    client = mqtt.Client()
    client.username_pw_set(MQTT_USERNAME, MQTT_PWD)
    client.tls_set(tls_version=ssl.PROTOCOL_TLSv1_2)
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(MQTT_BROKER, MQTT_PORT, 60)
    client.loop_start()  # Non-blocking
