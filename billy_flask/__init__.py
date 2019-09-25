from flask import Flask
import os

# Flask development server:
#   cd to flask_server root
#   . venv/bin/activate ; export FLASK_APP=billy_flask ; export FLASK_DEBUG=1 ; python3 -m flask run --host 0.0.0.0 ; deactivate

def create_app():
    app = Flask(__name__, instance_relative_config=True)

    try:
        os.makedirs(app.instance_path)
    except OSError:
        pass
    
    app.config.from_pyfile('config.cfg')
    
    from billy_flask import spotify, twitter, youtube, twitch, slack
    app.register_blueprint(spotify.bp)
    app.register_blueprint(twitter.bp)
    app.register_blueprint(youtube.bp)
    app.register_blueprint(twitch.bp)
    app.register_blueprint(slack.bp)


    return app
