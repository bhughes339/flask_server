import glob
import os

import requests
from billy_flask.db import get_db
from billy_flask.util import download
from flask import (Blueprint, current_app, jsonify, render_template, request,
                   url_for)
from requests_oauthlib import OAuth1

bp = Blueprint('twitter', __name__,
               url_prefix='/twitter', template_folder='templates', static_folder='static')
cnx = None
config = None
auth = None


@bp.before_request
def setup():
    global cnx, config, auth
    config = current_app.config['TWITTER']
    cnx = get_db('twitter')
    auth = OAuth1(config['consumer_key'], config['consumer_secret'],
                  config['access_key'], config['access_secret'])


@bp.route('/favs')
def twitter_likes():
    return render_template('twitter_likes.html')


@bp.route('/_get_fav')
def get_twitter_fav():
    return fetch(request.args.get('search', ''),
                 request.args.get('user', ''),
                 request.args.get('deleted', None),
                 request.args.get('media', None))


@bp.route('/_get_userlist')
def get_twitter_userlist():
    query = 'SELECT username FROM leaderboard'
    with cnx.cursor() as cursor:
        cursor.execute(query)
        users = cursor.fetchall()
    return jsonify([x[0] for x in users])


@bp.route('/webhook', methods=['GET', 'POST'])
def incoming_webhook():
    # webhook id: 1122926445498699780
    if request.method == 'GET':
        crc_token = request.args.get('crc_token', None)
        if crc_token:
            return validate_crc(crc_token)
    else:
        if request.is_json:
            data = request.get_json()
            if 'favorite_events' in data:
                for i in data['favorite_events']:
                    if data['for_user_id'] != i['favorited_status']['user']['id_str']:
                        save_tweet(i['favorited_status'])
            if 'follow_events' in data:
                for i in data['follow_events']:
                    if i['type'].lower() == 'follow':
                        follower_id = i['source']['id']
                        if follower_id != data['for_user_id']:
                            allowed_ids = ['595906410']
                            if follower_id not in allowed_ids:
                                follower_name = i['source']['screen_name']
                                params = { 'user_id': follower_id, 'skip_status': 1 }
                                requests.post('https://api.twitter.com/1.1/blocks/create.json', params=params, auth=auth)
                                requests.post('https://api.twitter.com/1.1/blocks/destroy.json', params=params, auth=auth)
                                query = 'INSERT INTO follow_attempts (timestamp, user_id, screen_name) VALUES (%s, %s, %s)'
                                with cnx.cursor() as cursor:
                                    cursor.execute(query, (i['created_timestamp'], follower_id, follower_name))
                                cnx.commit()

        return jsonify(response='ok')


def fetch(search, username=None, deleted=None, media=None):
    sql_search = r'\b{0}\b'.format(search)
    sql_username = username or '%'
    query = 'SELECT link, id, username, text, favs, retweets, delete_reason, timestamp FROM search_table WHERE text REGEXP %s AND username LIKE %s'
    if deleted:
        query += ' AND delete_reason IS NOT NULL'
    if media:
        query += ' AND has_media=1'
    query += ' ORDER BY RAND() LIMIT 1'
    with cnx.dict_cursor() as cursor:
        cursor.execute(query, (sql_search, sql_username))
        t = cursor.fetchone()
    html = ''
    if not t:
        html = '<p>Nothing Found!</p>'
    else:
        r = requests.get('https://publish.twitter.com/oembed',
                         params={'url': t['link'], 'omit_script': True, 'dnt': True})
        if r.status_code == requests.codes['ok']:
            html = r.json()['html']
            # html += r'<br><button onclick="navigator.share({url: "https://twitter.com"})">test</button>'
            html += f'<button class="share" onclick=\'navigator.share(JSON.parse("{{\\"url\\": \\"{t["link"]}\\"}}"))\'>Share</button>'
            html += f'<button class="share" onclick="location.href=\'{t["link"]}\'">Open</button>'
        else:
            with cnx.dict_cursor() as cursor:
                cursor.execute('SELECT id, displayname FROM users WHERE username=%s', (t['username']))
                data = cursor.fetchone()
                displayname = data['displayname']
                user_id = data['id']
            r = requests.get('https://api.twitter.com/2/users/' + user_id, auth=auth, params={'user.fields': 'profile_image_url'})
            payload = r.json()
            user_image = ''
            if 'data' in payload:
                user_image = payload['data'].get('profile_image_url', '')
            print(user_image)
            if not t['delete_reason']:
                t['delete_reason'] = f"User is protected and followed. <a href={t['link']}>Link to tweet</a>"
            html += (
                '<div class="deletedwrapper">'
                '<div class="deletedheader">'
                '<div class="avatarplaceholder" style="background-image: url({4});"></div>'
                '<div class="headerwrapper">'
                '<div class="headerwrapperinner">'
                '<div class="displayname">{0}</div>'
                '<div class="username">@{1}</div>'
                '</div></div></div>'
                '<div class="tweettext">{2}</div>'
                '</div>'
                '<p>@{1} ({3})</p>'.format(displayname, t['username'], t['text'].replace('\n', '<br>'), t['delete_reason'], user_image)
            )
            html += f"<p>{t['timestamp']}</p>"
            html += '<p>No fav/retweet information</p>' if t['favs'] == 0 else '<p>❤️ {0}  ♻️ {1}</p>'.format(t['favs'], t['retweets'])
            directory = os.path.join(current_app.instance_path, 'twitter_media', t['id'])
            if os.path.exists(directory):
                files = sorted(glob.glob(directory + '/*'))
                for f in files:
                    local_file = url_for('.static', filename='twitter_media/{0}/{1}'.format(t['id'], os.path.split(f)[1]))
                    if os.path.splitext(f)[1] == '.mp4':
                        html += f'<video class="tweetmedia" src="{local_file}#t=0.1" type="video/mp4" controls></video><br>'
                        # html += f'<a href="{local_file}">Link to video</a><br>'
                        html += f'<button class="share" onclick=\'navigator.share(JSON.parse("{{\\"url\\": \\"{local_file}\\"}}"))\'>Share</button>'
                    else:
                        html += f'<img class="tweetmedia" src="{local_file}"><br>'
    return html


def validate_crc(crc_token):
    """CRC validation for Twitter webhooks

    https://developer.twitter.com/en/docs/accounts-and-users/subscribe-account-activity/guides/securing-webhooks.html

    Args:
        crc_token (str): crc_token query argument value
    """
    import base64
    import hashlib
    import hmac
    sha256_hash_digest = hmac.new(config['consumer_secret'].encode(),
                                  msg=crc_token.encode(), digestmod=hashlib.sha256).digest()
    return jsonify(response_token='sha256=' + base64.b64encode(sha256_hash_digest).decode())


def save_tweet(tweet):
    import datetime
    import html
    import json
    favsquery = ('INSERT INTO favorites (id, user_id, text, timestamp, favs, retweets, raw_json, in_reply_to) '
                 'VALUES (%s, %s, %s, %s, %s, %s, %s, %s) '
                 'ON DUPLICATE KEY UPDATE favs=%s, retweets=%s, is_deleted=0, raw_json=%s')
    userquery = 'INSERT INTO users (id, username, displayname) VALUES (%s, %s, %s) ON DUPLICATE KEY UPDATE username=%s, displayname=%s'
    truncated = tweet['truncated']
    timestamp = datetime.datetime.strptime(tweet['created_at'],
                                           '%a %b %d %H:%M:%S %z %Y').strftime('%Y-%m-%d %H:%M:%S')
    user = tweet['user']
    text = tweet['extended_tweet']['full_text'] if truncated else tweet['text']
    text = html.unescape(text)
    json_tweet = json.dumps(tweet)
    reply = None
    if tweet['in_reply_to_status_id_str']:
        reply_object = get_tweet(tweet['in_reply_to_status_id_str'])
        reply = json.dumps(reply_object) if reply_object else None
    with cnx.cursor() as cursor:
        cursor.execute(favsquery, (str(tweet['id_str']), str(user['id_str']), text, timestamp,
                                   str(tweet['favorite_count']), str(tweet['retweet_count']), json_tweet, reply,
                                   str(tweet['favorite_count']), str(tweet['retweet_count']), json_tweet))
        cursor.execute(userquery, (str(user['id_str']), user['screen_name'], user['name'], user['screen_name'], user['name']))
    cnx.commit()
    save_media(tweet)


def save_media(tweet):
    import shutil

    import furl
    try:
        media = (tweet['extended_tweet']['extended_entities']['media']
                 if tweet['truncated']
                 else tweet['extended_entities']['media'])
    except:
        return
    with cnx.cursor() as cursor:
        cursor.execute('UPDATE favorites SET has_media=1 WHERE id={0}'.format(tweet['id_str']))
    cnx.commit()
    for m in media:
        file = m['media_url']
        if m['type'] == 'video':
            # Find the video with the highest bitrate
            file = max(m['video_info']['variants'], key=lambda x: x.get('bitrate', 0))['url']
        if file:
            folder = os.path.join(bp.root_path, 'static/twitter_media', tweet['id_str'])
            download(file, folder, basename=m['id_str'])


def get_tweet(tweet_id):
    r = requests.get('https://api.twitter.com/1.1/statuses/show.json',
                     auth=auth, params={'id': tweet_id, 'tweet_mode': 'extended'})
    if r.status_code == requests.codes['ok']:
        return r.json()
    return None
