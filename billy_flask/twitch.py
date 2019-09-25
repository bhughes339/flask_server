import random

import requests
from flask import (Blueprint, Response, current_app, jsonify, render_template,
                   request, url_for)

from .db import get_db

bp = Blueprint('twitch', __name__,
               url_prefix='/twitch', template_folder='templates/twitch')

config = None
cnx = None
headers = {'Accept': 'application/vnd.twitchtv.v5+json'}

@bp.before_request
def setup():
    global config, cnx, headers
    config = current_app.config['TWITCH']
    cnx = get_db('twitch')
    headers['Client-ID'] = config['client_id']


@bp.route('/surf')
def twitch_surf():
    room = request.args.get('room', '')
    return render_template('twitch_surf.html', room=room)


@bp.route('/_get_stream', methods=['GET'])
def get_stream():
    channel_id = request.args.get('channel', None)
    if not channel_id:
        return jsonify('error')
    url = 'https://api.twitch.tv/kraken/streams/' + channel_id
    r = requests.get(url, headers=headers)
    if r.status_code != requests.codes['ok']:
        return jsonify('error')
    return jsonify(r.json())



@bp.route('/_get_random_stream', methods=['GET'])
def get_random_stream():
    query = {'limit': 1, 'offset': 0}
    query['broadcaster_language'] = request.args.get('lang', None)
    query['game'] = request.args.get('game', None)
    previd = request.args.get('previd', None)

    url = 'https://api.twitch.tv/kraken/streams'
    r = requests.get(url, params=query, headers=headers)
    if r.status_code != requests.codes['ok']:
        return jsonify('error')
    response = r.json()
    if '_total' not in response:
        return jsonify('error')
    query['offset'] = random.randrange(int(response['_total']))
    r = requests.get(url, params=query, headers=headers)
    if r.status_code != requests.codes['ok']:
        return jsonify('error')
    response = r.json()
    if str(response['streams'][0]['channel']['_id']) == previd and int(response['_total']) > 1:
        offset_choice = list(filter(lambda x: x != int(query['offset']), range(int(response['_total']))))
        query['offset'] = random.choice(offset_choice)
        r = requests.get(url, params=query, headers=headers)
        if r.status_code != requests.codes['ok']:
            return jsonify('error')
        response = r.json()
    return jsonify(response['streams'][0] if response['streams'] else [])


@bp.route('/_get_top_games', methods=['GET'])
def get_top_games():
    url = 'https://api.twitch.tv/kraken/games/top'
    query = {'limit': 100, 'offset': 0}
    response = requests.get(url, params=query, headers=headers).json()
    return jsonify([x['game']['name'] for x in response['top']])


@bp.route('/_search_games', methods=['GET'])
def search_games():
    url = 'https://api.twitch.tv/kraken/search/games'
    query = {
        'type': 'suggest',
        'live': True,
        'query': request.args.get('query', None)
    }
    response = requests.get(url, params=query, headers=headers).json()
    gamelist = response.get('games', None) or []
    return jsonify([x['name'] for x in gamelist])


@bp.route('/_group_update')
def group_update():
    import re
    room = request.args.get('room', '')[:20]
    if room:
        stream = request.args.get('stream', '')
        # Rough estimate of channelid structure, can change if needed
        if re.fullmatch(r'\d{1,20}', stream):
            query = 'INSERT INTO stream (room, stream_id) VALUES (%s, %s) ON DUPLICATE KEY UPDATE stream_id=%s'
            with cnx.cursor() as cursor:
                cursor.execute(query, (room, stream, stream))
            cnx.commit()
    return jsonify('ok')


@bp.route('/_group_event_stream')
def group_event_stream():
    room = request.args.get('room', '')[:20]
    if room:
        query = 'SELECT stream_id FROM stream WHERE room=%s'
        with cnx.cursor() as cursor:
            cursor.execute(query, (room))
            result = cursor.fetchone()
            stream = result[0] if result else 0
        return Response(
            'data: {0}\n\n'.format(stream),
            mimetype='text/event-stream'
        )
