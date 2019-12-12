import glob
import os
import random

import requests
from flask import Blueprint, current_app, render_template, request, url_for, jsonify

from billy_flask.db import get_db

bp = Blueprint('vine', __name__,
               url_prefix='/vine', template_folder='templates', static_folder='static')
cnx = None


@bp.route('/ripvine')
def ripvine():
    return render_template('ripvine.html')

@bp.route('/_get_random_vine')
def get_random_vine():
    files = glob.glob(os.path.join(bp.static_folder, 'vines/*.*'))
    v = files[random.randrange(0, len(files))]
    return jsonify(os.path.relpath(v, bp.root_path))
