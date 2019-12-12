from flask import Flask
import os

# Flask development server:
#   cd to flask_server root
#   . venv/bin/activate ; export FLASK_APP=billy_flask ; export FLASK_DEBUG=1 ; python3 -m flask run --host 0.0.0.0 ; deactivate

def create_app():
    app = Flask(__name__, instance_relative_config=True)

    os.makedirs(app.instance_path, exist_ok=True)
    
    app.config.from_pyfile('config.cfg')

    register_blueprints(app)

    return app

def register_blueprints(app):
    import setuptools, importlib
    exclude = app.config['BP_EXCLUDE']
    path = os.path.join(app.root_path, 'blueprints')
    for p in setuptools.find_packages(path):
        if p not in exclude:
            try:
                module = '{0}.blueprints.{1}'.format(__name__, p)
                bp = importlib.import_module(module).bp
                app.register_blueprint(bp)
            except Exception as e:
                print(e)
