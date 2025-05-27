from flask import Flask
from flask_login import LoginManager
from flask_migrate import Migrate
from models import db, User
import os
from dotenv import load_dotenv
from routes import main as main_bp

load_dotenv()

login_manager = LoginManager()
migrate = Migrate()

def create_app():
    app = Flask(__name__)
    app.config['SECRET_KEY'] = os.getenv("FLASK_SECRET_KEY")
    app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    db.init_app(app)
    login_manager.init_app(app)
    migrate.init_app(app, db)

    login_manager.login_view = 'main.login'
    login_manager.login_message_category = "danger"

    # Register routes
    app.register_blueprint(main_bp)

    return app

app = create_app()

@login_manager.user_loader
def load_user(user_id):
    return db.session.query(User).filter_by(id=user_id).first()

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5000)
