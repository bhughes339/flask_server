import re
from datetime import datetime
from warnings import filterwarnings

import requests
from flask import Blueprint, current_app, jsonify, request

from billy_flask.db import get_db, mysql_warning
from billy_flask.util import download

bp = Blueprint('slack', __name__, url_prefix='/slack', static_folder='static')
cnx = None
config = None


@bp.before_request
def setup():
    global cnx, config
    config = current_app.config['SLACK']
    cnx = get_db('slack')
    filterwarnings('ignore', category=mysql_warning())


@bp.route('/pinhit', methods=['GET', 'POST'])
def pinhit():
    if not validate(request):
        return jsonify({'error': 'Secret validation failed.'})
    potd = request.args.get('potd', False)
    text = request.form.get('text', '')
    return jsonify(get_pin(potd, text))


@bp.route('/events', methods=['POST'])
def process_event():
    import html, os
    if not request.is_json:
        return jsonify({'error': 'Invalid request.'})
    if not validate(request):
        return jsonify({'error': 'Secret validation failed.'})
    data = request.get_json()
    if 'challenge' in data:
        return jsonify({'challenge': data['challenge']})
    event = data['event']
    if event['type'] == 'pin_added':
        query = "INSERT IGNORE INTO pins (timestamp, text, userid, channel, pinnedby) VALUES (%s, %s, %s, %s, %s)"
        pin = event['item']
        if pin['type'] == 'message':
            msg = pin['message']
            user = msg.get('user', None)
            fixed_text = html.unescape(msg['text'])
            with cnx.cursor() as cursor:
                cursor.execute('SELECT timestamp FROM pins WHERE timestamp=%s', (msg['ts']))
                if not cursor.fetchone():
                    cursor.execute(query, (msg['ts'], fixed_text, user, pin['channel'], pin['created_by']))
                    flush_pin(pin['channel'])
                    if 'files' in msg:
                        for i in msg['files']:
                            file = i['url_private']
                            folder = os.path.join(bp.root_path, 'static/slack_media', msg['ts'])
                            download(file, folder, headers={'Authorization': 'Bearer ' + config['bot_token']})
            cnx.commit()
    return jsonify('ok')


@bp.route('/actions', methods=['POST', 'GET'])
def process_action():
    import json
    if not validate(request):
        return jsonify({'error': 'Secret validation failed.'})
    payload = json.loads(request.form['payload'])
    if payload['callback_id'] == 'uncaps':
        message = payload['message']
        fixed_text = message['text'].lower()
        if message['text'] != fixed_text:
            params = {
                'token': config['user_token'],
                'channel': payload['channel']['id'],
                'text': fixed_text,
                'ts': message['ts']
            }
            requests.post('https://slack.com/api/chat.update', params=params)
    elif payload['callback_id'] == 'potd':
        potd_obj = get_pin(potd=True)
        potd_obj['channel'] = 'C101M20BT'
        headers = {'Authorization': 'Bearer ' + config['bot_token']}
        requests.post('https://slack.com/api/chat.postMessage', json=potd_obj, headers=headers)
    elif payload['callback_id'] == 'pinhit':
        pin_obj = get_pin()
        pin_obj['channel'] = 'C101M20BT'
        headers = {'Authorization': 'Bearer ' + config['bot_token']}
        requests.post('https://slack.com/api/chat.postMessage', json=pin_obj, headers=headers)
    return jsonify('ok')


def validate(flask_request):
    import hmac, hashlib
    body = flask_request.get_data(as_text=True)
    ts = flask_request.headers.get('X-Slack-Request-Timestamp')
    basestring = bytes(f'v0:{ts}:{body}', 'utf-8')
    secret = bytes(config['signing_secret'], 'utf-8')
    signature = f'v0={hmac.new(secret, basestring, digestmod=hashlib.sha256).hexdigest()}'
    return hmac.compare_digest(signature, flask_request.headers.get('X-Slack-Signature'))


def get_pin(potd=False, text=''):
    args = []
    query = ('SELECT pins.text, u1.name, u1.avatar, channels.name as channel, pins.timestamp, u2.name as pinnedby'
             ' FROM pins'
             ' INNER JOIN users u1 ON pins.userid=u1.id'
             ' INNER JOIN users u2 ON pins.pinnedby=u2.id'
             ' INNER JOIN channels ON pins.channel=channels.id')
    if potd:
        today = datetime.today()
        query += (' WHERE day(FROM_UNIXTIME(pins.timestamp))=%s'
                  ' AND month(FROM_UNIXTIME(pins.timestamp))=%s'
                  ' AND year(FROM_UNIXTIME(pins.timestamp))!=%s'
                  ' ORDER BY pins.timestamp ASC')
        args.extend([today.day, today.month, today.year])
    else:
        match = re.match(r'^(?:-u +@?([\S]+))?(.*)', text)
        search = match.group(2).strip()
        query += ' WHERE pins.text REGEXP %s'
        args.append(f'\\b{search}\\b')
        if match.group(1):
            query += ' AND u1.name=%s'
            args.append(match.group(1))
        query += ' ORDER BY pins.timestamp DESC LIMIT 10' if search else ' ORDER BY RAND() LIMIT 1'
    with cnx.dict_cursor() as cursor:
        cursor.execute(query, args)
        pins = cursor.fetchall()
    if pins:
        slack_object = {
            'text': '*Pins of the Day*' if potd else ':pushpin: *Pinhit* :pushpin:',
            'response_type': 'in_channel',
            'attachments': []
        }
        for p in pins:
            slack_object['attachments'].append({
                'author_name': p['name'],
                'author_icon': p['avatar'],
                'text': p['text'],
                'footer': f"Pinned by {p['pinnedby']}",
                'ts': p['timestamp']
            })
    else:
        slack_object = {
            'response_type': 'ephemeral',
            'text': 'No POTDs for today.' if potd else f'Nothing found for "{text}"'
        }
    return slack_object


def flush_pin(channel):
    r = requests.get('https://slack.com/api/pins.list',
                     params={'token': config['bot_token'], 'channel': channel})
    if r.status_code != requests.codes['ok']:
        return
    data = r.json()
    first_pin = data['items'].pop()
    while 'message' not in first_pin:
        first_pin = data['items'].pop()
    requests.post('https://slack.com/api/pins.remove',
                  data={'token': config['bot_token'], 'channel': channel,
                        'timestamp': first_pin['message']['ts']})
