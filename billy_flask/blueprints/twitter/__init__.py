import glob
import os

import requests
from flask import Blueprint, current_app, render_template, request, url_for, jsonify

from billy_flask.db import get_db
from billy_flask.util import download

bp = Blueprint('twitter', __name__,
               url_prefix='/twitter', template_folder='templates', static_folder='static')
cnx = None
config = None


@bp.before_request
def setup():
    global cnx, config
    config = current_app.config['TWITTER']
    cnx = get_db('twitter')


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
    query = 'SELECT username FROM users'
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
        else:
            if not t['delete_reason']:
                t['delete_reason'] = 'User is protected and followed. <a href={0}>Link to tweet</a>'.format(t['link'])
            html += '<p class="tweettext">{0}</p><p>@{1} ({2})</p>'.format(t['text'].replace('\n', '<br>'), t['username'], t['delete_reason'])
            html += '<p>{0}</p>'.format(t['timestamp'])
            html += '<p>No fav/retweet information</p>' if t['favs'] == 0 else '<p>❤️ {0}  ♻️ {1}</p>'.format(t['favs'], t['retweets'])
            directory = os.path.join(current_app.instance_path, 'twitter_media', t['id'])
            if os.path.exists(directory):
                files = sorted(glob.glob(directory + '/*'))
                for f in files:
                    local_file = url_for('.static', filename='twitter_media/{0}/{1}'.format(t['id'], os.path.split(f)[1]))
                    if os.path.splitext(f)[1] == '.mp4':
                        html += '<video class="tweetmedia" src="{0}" type="video/mp4" autoplay controls></video><br>'.format(local_file)
                        html += '<a href="{0}">Link to video</a><br>'.format(local_file)
                    else:
                        html += '<img class="tweetmedia" src="{0}"><br>'.format(local_file)
    return html


def validate_crc(crc_token):
    """CRC validation for Twitter webhooks

    https://developer.twitter.com/en/docs/accounts-and-users/subscribe-account-activity/guides/securing-webhooks.html

    Args:
        crc_token (str): crc_token query argument value
    """
    import base64, hashlib, hmac
    sha256_hash_digest = hmac.new(config['consumer_secret'].encode(),
                                  msg=crc_token.encode(), digestmod=hashlib.sha256).digest()
    return jsonify(response_token='sha256=' + base64.b64encode(sha256_hash_digest).decode())


def save_tweet(tweet):
    import json, datetime, html
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
    import shutil, furl
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
    from requests_oauthlib import OAuth1
    auth = OAuth1(config['consumer_key'], config['consumer_secret'],
                  config['access_key'], config['access_secret'])
    r = requests.get('https://api.twitter.com/1.1/statuses/show.json',
                     auth=auth, params={'id': tweet_id, 'tweet_mode': 'extended'})
    if r.status_code == requests.codes['ok']:
        return r.json()
    return None
