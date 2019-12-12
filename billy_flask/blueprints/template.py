from flask import Blueprint, current_app

from billy_flask.db import get_db

bp = Blueprint('blueprint_name', __name__,
               url_prefix='/blueprint_name',
               template_folder='templates',
               static_folder='static')
cnx = None
config = None


@bp.before_request
def setup():
    global cnx, config
    config = current_app.config['BLUEPRINT_NAME']
    cnx = get_db('blueprint_name')
