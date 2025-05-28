from flask_login import UserMixin
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(150), unique=True)
    password_hash = db.Column(db.String(200))

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Device(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    board_id = db.Column(db.String(64), unique=True, nullable=False)
    api_key = db.Column(db.String(128), unique=True, nullable=False)
    settings = db.Column(db.JSON)
    size = db.Column(db.String(12))
    name = db.Column(db.String(128))

class UserDeviceLink(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    device_id = db.Column(db.Integer, db.ForeignKey('device.id'), nullable=False)
    user = db.relationship('User', backref='user_device_links')
    device = db.relationship('Device', backref='user_device_links')

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    board_id = db.Column(db.String(64), db.ForeignKey('device.board_id'), nullable=False)
    message = db.Column(db.Text)
    user = db.relationship('User', backref='user_message')
    device = db.relationship('Device', backref='user_message')
