from config import Config
from damf.web import DAMFWebApp

try:
    from flask import Flask
    from flask_sqlalchemy import SQLAlchemy
    from flask_migrate import Migrate

    app = Flask(__name__)
    app.config.from_object(Config)

    db = SQLAlchemy(app)
    migrate = Migrate(app, db)

    from app import routes, models  # noqa: E402,F401
except ImportError:
    # Fallback when Flask is not installed: expose the standalone DAMFWebApp instance
    app = DAMFWebApp()
    db = None
    migrate = None
