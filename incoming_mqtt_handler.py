import paho.mqtt.client as mqtt
import ssl
import json
import os

MQTT_BROKER = os.getenv("MQTT_BROKER")
MQTT_PORT = int(os.getenv("MQTT_PORT"))
MQTT_USERNAME = os.getenv("MQTT_USERNAME")
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD")
BOARD_ID = os.getenv("BOARD_ID")

last_response = None  # Store for Flask access

def on_connect(client, userdata, flags, rc):
    print("Website MQTT client connected with result code", rc)
    client.subscribe("#")

def on_message(client, userdata, msg):
    global last_response
    try:
        payload = json.loads(msg.payload.decode())
        print(f"Response from device: {payload}")
        last_response = payload  # Save to variable or DB/log as needed
    except Exception as e:
        print("Failed to parse response:", e)

def start_website_mqtt_listener():
    client = mqtt.Client()
    client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
    client.tls_set(tls_version=ssl.PROTOCOL_TLSv1_2)
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(MQTT_BROKER, MQTT_PORT, 60)
    client.loop_start()  # Non-blocking
