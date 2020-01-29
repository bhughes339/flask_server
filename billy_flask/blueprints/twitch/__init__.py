import random

import requests
from flask import (Blueprint, Response, current_app, jsonify, render_template,
                   request, url_for)

from billy_flask.db import get_db

bp = Blueprint('twitch', __name__,
               url_prefix='/twitch', template_folder='templates', static_folder='static')

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
    payload = get_helix_stream(channel_id)
    return jsonify(payload)


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
    # Get Helix stream object
    payload = None
    try:
        payload = get_helix_stream(response['streams'][0]['channel']['_id'])
    except:
        pass
    return jsonify(payload if payload else {})


@bp.route('/_search_streams', methods=['GET'])
def search_streams():
    url = 'https://api.twitch.tv/kraken/search/streams'
    query = {
        'limit': 10,
        'query': request.args.get('query', None)
    }
    response = requests.get(url, params=query, headers=headers).json()
    stream_list = response.get('streams', None) or []
    # return jsonify([x['channel']['name'] for x in stream_list])
    return jsonify(stream_list)


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


@bp.route('/_get_game_name')
def get_game_name():
    game_id = request.args.get('game_id', '')
    if not game_id:
        return jsonify('error')
    query = { 'id': game_id }
    url = 'https://api.twitch.tv/helix/games'
    r = requests.get(url, headers=headers, params=query)
    try:
        game_name = r.json()['data'][0]['name']
    except:
        game_name = ''
    return Response(game_name,
                    mimetype='text/plain'
    )


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
            f'data: {stream}\n\n',
            mimetype='text/event-stream'
        )


@bp.route('/_channel_event_stream')
def channel_event_stream():
    import json
    channel_id = request.args.get('channel_id', '')
    if channel_id:
        payload = get_helix_stream(channel_id)
        return Response(
            f'data: {json.dumps(payload)}\n\n',
            mimetype='text/event-stream'
        )


def get_helix_stream(channel_id):
    if not channel_id:
        return None
    query = { 'user_id': channel_id }
    url = 'https://api.twitch.tv/helix/streams'
    r = requests.get(url, headers=headers, params=query)
    if r.status_code != requests.codes['ok']:
        return None
    try:
        payload = r.json()['data'][0]
    except:
        return None
    query = { 'id': payload['game_id'] }
    url = 'https://api.twitch.tv/helix/games'
    r = requests.get(url, headers=headers, params=query)
    if r.status_code != requests.codes['ok']:
        return None
    payload['game_name'] = r.json()['data'][0]['name']
    return payload


@bp.route('/_webhook_test', methods=['GET', 'POST'])
def webhook_test():
    print('hello???')
    if request.method == 'GET':
        return Response(request.args.get('hub.challenge', ''),
                        mimetype='text/plain')
    else:
        if request.is_json:
            print(request.get_json())
        else:
            print('no')
    return jsonify('ok')
