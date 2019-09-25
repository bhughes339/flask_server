import re
from datetime import datetime
from warnings import filterwarnings

import requests
from flask import Blueprint, current_app, jsonify, request

from .db import get_db, mysql_warning
from .util import download

bp = Blueprint('slack', __name__, url_prefix='/slack')
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
    query = ('SELECT pins.text, users.name, users.avatar, channels.name as channel, pins.timestamp'
             ' FROM pins INNER JOIN users ON pins.userid=users.id'
             ' INNER JOIN channels ON pins.channel=channels.id')
    args = []
    potd = request.args.get('potd', None)
    if potd:
        today = datetime.today()
        query += (' WHERE day(FROM_UNIXTIME(pins.timestamp))=%s'
                  ' AND month(FROM_UNIXTIME(pins.timestamp))=%s'
                  ' AND year(FROM_UNIXTIME(pins.timestamp))!=%s'
                  ' ORDER BY pins.timestamp ASC')
        args.extend([today.day, today.month, today.year])
    else:
        text = request.form.get('text', '')
        match = re.match(r'^(?:-u +([\S]+))?(.*)', text)
        search = (r'\b{0}\b'.format(match.groups()[1].strip())) if match.groups()[1] else ''
        query += ' WHERE pins.text REGEXP %s'
        args.append(search)
        if match.groups()[0]:
            query += ' AND users.name=%s'
            args.append(match.groups()[0])
        query += ' ORDER BY RAND() LIMIT 1'
    with cnx.dict_cursor() as cursor:
        cursor.execute(query, args)
        pins = cursor.fetchall()
    if pins:
        slack_object = {
            'response_type': 'in_channel',
            'attachments': []
        }
        for p in pins:
            slack_object['attachments'].append({
                'author_name': p['name'],
                'author_icon': p['avatar'],
                'text': p['text'],
                'footer': 'Posted in #' + p['channel'],
                'ts': p['timestamp']
            })
    else:
        slack_object = {
            'response_type': 'ephemeral',
            'text': 'No POTDs for today.' if potd else 'Nothing found for "{0}"'.format(text)
        }
    return jsonify(slack_object)


@bp.route('/events', methods=['POST'])
def process_event():
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
            import html
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
                            import os
                            file = i['url_private']
                            folder = os.path.join(current_app.root_path, 'static/slack_media', msg['ts'])
                            download(file, folder, headers={'Authorization': 'Bearer ' + config['app_token']})
            cnx.commit()
    return jsonify('ok')


def validate(flask_request):
    import hmac, hashlib
    body = flask_request.get_data(as_text=True)
    secret = bytes(config['app_secret'], 'utf-8')
    ts = flask_request.headers.get('X-Slack-Request-Timestamp')
    basestring = bytes('v0:{0}:{1}'.format(ts, body), 'utf-8')
    signature = 'v0=' + hmac.new(secret, basestring, digestmod=hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature, flask_request.headers.get('X-Slack-Signature'))


def flush_pin(channel):
    r = requests.get('https://slack.com/api/pins.list',
                     params={'token': config['app_token'], 'channel': channel})
    if r.status_code != requests.codes['ok']:
        return
    data = r.json()
    first_pin = data['items'].pop()
    while 'message' not in first_pin:
        first_pin = data['items'].pop()
    requests.post('https://slack.com/api/pins.remove',
                  data={'token': config['app_token'], 'channel': channel,
                        'timestamp': first_pin['message']['ts']})
