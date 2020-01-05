from flask import Blueprint, render_template, request

import re
import json

bp = Blueprint('mtga', __name__,
               url_prefix='/mtga',
               template_folder='templates',
               static_folder='static')

@bp.route('/', methods=['GET', 'POST'])
def rank_info():
    result = None
    if request.method == 'POST':
        f = request.files['mtga_log']
        result = get_rank_from_log(f)
    return render_template('rankinfo.html', result=result)


def get_rank_from_log(logfile):
    last_match = None
    result = None
    for line in logfile:
        test = str(line)
        if 'constructedMatchesWon' in test:
            last_match = test

    if last_match:
        match = re.search(r'"payload":(\{[^}]+})', last_match)
        if match:
            result = json.loads(match.group(1))

    return result
