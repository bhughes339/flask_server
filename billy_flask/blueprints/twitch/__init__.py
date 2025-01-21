import random
import re

import requests
from flask import (Blueprint, Response, current_app, jsonify, render_template, redirect,
                   request, session, url_for)

from billy_flask.db import get_db
from billy_flask.util import seconds_to_time
from .util import get_following, get_latest_watched, gen_video_data, update_latest_watched

bp = Blueprint('twitch', __name__,
               url_prefix='/twitch', template_folder='templates', static_folder='static')

config = None
cnx = None
global_headers = {'Accept': 'application/vnd.twitchtv.v5+json'}

OAUTH_PARAMS = {
    'auth_url': 'https://id.twitch.tv/oauth2/authorize',
    'auth_params': {
        "response_type": "code",
        "scope": "user"
    },
    'callback_url': 'https://example.com/api/oauth.access',
    'callback_params': {}
}


@bp.before_request
def setup():
    global config, cnx, global_headers
    config = current_app.config['TWITCH']
    cnx = get_db('twitch')
    global_headers['Client-Id'] = config['client_id']
    if not session.get('access_token'):
        r = requests.post('https://id.twitch.tv/oauth2/token', params={
            'client_id': config['client_id'],
            'client_secret': config['client_secret'],
            'grant_type': 'client_credentials'
        })
        session['access_token'] = r.json()['access_token']
    global_headers['Authorization'] = f"Bearer {session['access_token']}"


@bp.route('/recent', methods=['GET', 'POST'])
def twitch_recent():
    print(request.remote_addr)
    if gql_headers := request.values.get("headers"):
        if gql_headers.strip() == "Billbill39":
            session["graphql_token"] = config["graphql_token"]
            session["graphql_client_id"] = config["graphql_client_id"]
        if match := re.search(r"Authorization: OAuth (\S+)", gql_headers):
            session["graphql_token"] = match.group(1)
        if match := re.search(r"Client-Id: (\S+)", gql_headers):
            session["graphql_client_id"] = match.group(1)
    if not (gql_token := session.get("graphql_token")):
        if request.remote_addr == "127.0.0.1":
            session["graphql_token"] = config["graphql_token"]
            session["graphql_client_id"] = config["graphql_client_id"]
        else:
            return render_template('twitch_auth.html')
    try:
        latest = get_latest_watched(gql_token, config['user_token'], global_headers)
    except KeyError:
        return render_template('twitch_auth.html')
    following = get_following(config['user_token'], global_headers)
    vids = list(gen_video_data(latest, following))
    users = list(dict.fromkeys({x["user"]: True for x in vids}))
    return render_template('twitch_latest.html', vids=vids, users=users)


@bp.route('/remove_recent', methods=['POST'])
def twitch_remove_recent():
    video_id = request.json.get("video_id")
    r = requests.get("https://api.twitch.tv/helix/videos", params={"id": str(video_id)}, headers=global_headers)
    if "error" in r.json():
        return jsonify({"ok": False, "error": "Invalid video_id"})
    res = update_latest_watched(session.get("graphql_token"), video_id)
    return jsonify({"ok": res})


@bp.route('/ff')
def twitch_ff():
    with cnx.cursor() as cursor:
        cursor.execute("SELECT filename, time FROM ff WHERE id=%s", ("saved_position",))
        if row := cursor.fetchone():
            filename, time = row
        else:
            cursor.execute("SELECT filename, time FROM ff WHERE id=%s", ("current_vid",))
            filename, time = cursor.fetchone()
            time = max(int(time) - 1260, 0)
    
    url = url_for('.static', filename=f"ff/{filename}/master.m3u8")
    return render_template('ff.html', url=url, resumed_time=time, timestamp=seconds_to_time(time))

@bp.route('ffupdate')
def twitch_ffupdate():
    time = int(float(request.args.get("time", 0)))
    with cnx.cursor() as cursor:
        cursor.execute("UPDATE ff SET time=%s WHERE id=%s", (time, "current_vid"))
    cnx.commit()
    return jsonify("ok")

@bp.route('ffclear')
def twitch_ffclear():
    with cnx.cursor() as cursor:
        cursor.execute("DELETE FROM ff WHERE id=%s", ("saved_position",))
    cnx.commit()
    return jsonify("ok")

@bp.route('ffsave', methods=['POST'])
def twitch_ffsave():
    with cnx.cursor() as cursor:
        cursor.execute("SELECT filename, time FROM ff WHERE id=%s", ("current_vid",))
        filename, time = cursor.fetchone()
        cursor.execute("INSERT INTO ff VALUES (%s, %s, %s) ON DUPLICATE KEY UPDATE filename=%s, time=%s", ("saved_position", filename, time, filename, time))
        latest = list(gen_video_data(get_latest_watched(config["graphql_token"], config['user_token'], global_headers)))[0]
        cursor.execute("INSERT INTO sleep_stream VALUES (%s, %s, %s) ON DUPLICATE KEY UPDATE video_id=%s, time=%s", ("saved_position", latest["video_id"], latest["time"], latest["video_id"], latest["time"]))
    cnx.commit()
    return jsonify("ok")


@bp.route('sleep_resume')
def twitch_sleep_resume():
    with cnx.cursor() as cursor:
        cursor.execute("SELECT video_id, time FROM sleep_stream WHERE id=%s", ("saved_position",))
        row = cursor.fetchone()
        if row:
            video_id, time = row
            update_latest_watched(config["graphql_token"], video_id, time)
            cursor.execute("DELETE FROM sleep_stream WHERE id=%s", ("saved_position",))
        else:
            video_id = list(gen_video_data(get_latest_watched(config["graphql_token"], config['user_token'], global_headers, True)))[0]["video_id"]
    cnx.commit()
    if "applewebkit" in str(request.user_agent).casefold():
        url = f"twitch://video/{video_id}"
    else:
        url = f"https://www.twitch.tv/videos/{video_id}"
    return redirect(url)

@bp.route('vod_resume/<string:video_id>')
def twitch_vod_resume(video_id):
    with cnx.cursor() as cursor:
        cursor.execute("SELECT time FROM sleep_stream WHERE id=%s AND video_id=%s", ("saved_position", video_id))
        row = cursor.fetchone()
        if row:
            time, = row
            update_latest_watched(config["graphql_token"], video_id, time)
            cursor.execute("DELETE FROM sleep_stream WHERE id=%s", ("saved_position",))
    cnx.commit()
    return redirect(f"https://www.twitch.tv/videos/{video_id}")

@bp.route('/fftest')
def twitch_fftest():
    url = url_for('.static', filename=f"ff/hls-test/filename.m3u8")
    return render_template('hls-test.html', url=url)

# ======================================================================
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
    r = requests.get(url, params=query, headers=global_headers)
    if r.status_code != requests.codes['ok']:
        return jsonify('error')
    response = r.json()
    from pprint import pprint
    if '_total' not in response:
        return jsonify('error')
    query['offset'] = random.randrange(int(response['_total']))
    r = requests.get(url, params=query, headers=global_headers)
    if r.status_code != requests.codes['ok']:
        return jsonify('error')
    response = r.json()
    if str(response['streams'][0]['channel']['_id']) == previd and int(response['_total']) > 1:
        offset_choice = list(filter(lambda x: x != int(query['offset']), range(int(response['_total']))))
        query['offset'] = random.choice(offset_choice)
        r = requests.get(url, params=query, headers=global_headers)
        if r.status_code != requests.codes['ok']:
            return jsonify('error')
        response = r.json()
    # Get Helix stream object
    payload = None
    print(response)
    try:
        payload = get_helix_stream(response['streams'][0]['channel']['_id'])
    except:
        payload = {}
    print(payload)
    return jsonify(payload)


@bp.route('/_search_streams', methods=['GET'])
def search_streams():
    url = 'https://api.twitch.tv/kraken/search/streams'
    query = {
        'limit': 10,
        'query': request.args.get('query', None)
    }
    response = requests.get(url, params=query, headers=global_headers).json()
    stream_list = response.get('streams', None) or []
    # return jsonify([x['channel']['name'] for x in stream_list])
    return jsonify(stream_list)


@bp.route('/_get_top_games', methods=['GET'])
def get_top_games():
    url = 'https://api.twitch.tv/kraken/games/top'
    query = {'limit': 100, 'offset': 0}
    response = requests.get(url, params=query, headers=global_headers).json()
    return jsonify([x['game']['name'] for x in response['top']])


@bp.route('/_search_games', methods=['GET'])
def search_games():
    url = 'https://api.twitch.tv/kraken/search/games'
    query = {
        'type': 'suggest',
        'live': True,
        'query': request.args.get('query', None)
    }
    response = requests.get(url, params=query, headers=global_headers).json()
    gamelist = response.get('games', None) or []
    return jsonify([x['name'] for x in gamelist])


@bp.route('/_get_game_name')
def get_game_name():
    game_id = request.args.get('game_id', '')
    if not game_id:
        return jsonify('error')
    query = { 'id': game_id }
    url = 'https://api.twitch.tv/helix/games'
    r = requests.get(url, headers=global_headers, params=query)
    try:
        game_name = r.json()['data'][0]['name']
    except:
        game_name = 'n/a'
    return Response(game_name, mimetype='text/plain')


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
    r = requests.get(url, headers=global_headers, params=query)
    if r.status_code != requests.codes['ok']:
        return None
    try:
        payload = r.json()['data'][0]
    except:
        return None
    query = { 'id': payload['game_id'] }
    url = 'https://api.twitch.tv/helix/games'
    r = requests.get(url, headers=global_headers, params=query)
    if r.status_code != requests.codes['ok']:
        return None
    try:
        payload['game_name'] = r.json()['data'][0]['name']
    except:
        payload['game_name'] = 'n/a'
    return payload
