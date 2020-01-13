from flask import Blueprint, render_template, request

import re
import json

bp = Blueprint('mtga', __name__,
               url_prefix='/mtga',
               template_folder='templates',
               static_folder='static')

RANK_COLORS = {
    'Bronze': ('#cd7f32', 'black'),
    'Silver': ('#c0c0c0', 'black'),
    'Gold': ('#ffd700', 'black'),
    'Platinum': ('#e5e4e2', 'black'),
    'Diamond': ('#70d1f4', 'black'),
    'Mythic': ('#e67316', 'black')
}

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
            result['constructedWinPercent'] = result['limitedWinPercent'] = 0
            if (result['constructedMatchesWon'] + result['constructedMatchesLost']) > 0:
                result['constructedWinPercent'] = int(result['constructedMatchesWon'] / (result['constructedMatchesWon'] + result['constructedMatchesLost']) * 100)
            if (result['limitedMatchesWon'] + result['limitedMatchesLost']) > 0:
                result['limitedWinPercent'] = int(result['limitedMatchesWon'] / (result['limitedMatchesWon'] + result['limitedMatchesLost']) * 100)
            
            result['constructedColors'] = RANK_COLORS.get(result['constructedClass'], ('', 'black'))
            result['limitedColors'] = RANK_COLORS.get(result['limitedClass'], ('', 'black'))

    return result
