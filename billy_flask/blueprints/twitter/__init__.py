import glob
import json
import os
import click

import requests
import pytesseract
from pathlib import Path
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
                 request.args.get('ocr', ''),
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
    print("webhook")
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
            # if 'follow_events' in data:
            #     for i in data['follow_events']:
            #         if i['type'].lower() == 'follow':
            #             follower_id = i['source']['id']
            #             if follower_id != data['for_user_id']:
            #                 allowed_ids = ['595906410']
            #                 if follower_id not in allowed_ids:
            #                     follower_name = i['source']['screen_name']
            #                     params = { 'user_id': follower_id, 'skip_status': 1 }
            #                     requests.post('https://api.twitter.com/1.1/blocks/create.json', params=params, auth=auth)
            #                     requests.post('https://api.twitter.com/1.1/blocks/destroy.json', params=params, auth=auth)
            #                     query = 'INSERT INTO follow_attempts (timestamp, user_id, screen_name) VALUES (%s, %s, %s)'
            #                     with cnx.cursor() as cursor:
            #                         cursor.execute(query, (i['created_timestamp'], follower_id, follower_name))
            #                     cnx.commit()

        return jsonify(response='ok')


def fetch(search, ocr=None, username=None, deleted=None, media=None):
    sql_search = r'\b{0}\b'.format(search)
    sql_username = username or '%'
    search_query = 'SELECT link, id, username, text, favs, retweets, delete_reason, timestamp FROM search_table'
    if ocr:
        ocr_query = 'SELECT tweet_id FROM media_data WHERE raw_ocr REGEXP %s ORDER BY RAND() LIMIT 1'
        with cnx.dict_cursor() as cursor:
            cursor.execute(ocr_query, (ocr,))
            found = cursor.fetchone()
        if found:
            with cnx.dict_cursor() as cursor:
                search_query += ' WHERE id=%s'
                cursor.execute(search_query, (found['tweet_id'],))
                t = cursor.fetchone()
    else:
        search_query += ' WHERE text REGEXP %s AND username LIKE %s'
        if deleted:
            search_query += ' AND delete_reason IS NOT NULL'
        if media:
            search_query += ' AND has_media=1'
        search_query += ' ORDER BY RAND() LIMIT 1'
        with cnx.dict_cursor() as cursor:
            cursor.execute(search_query, (sql_search, sql_username))
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
                '<div id="deletedwrapper" class="deletedwrapper">'
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
            # html += '<button class="share" onclick=\'navigator.share(JSON.parse("{\\"text\\": document.getElementById(\'tweet\').outerHTML}"))\'>Share HTML</button>'
            html += '<button class="share" onclick=\'navigator.share({"text": btoa(encodeURIComponent(document.getElementById("deletedwrapper").outerHTML))})\'>Share HTML</button>'
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
        cursor.execute('UPDATE favorites SET has_media=1 WHERE id=%s', (tweet['id_str'],))
    cnx.commit()
    for m in media:
        file = m['media_url']
        ocr_text = None
        if m['type'] == 'video':
            # Find the video with the highest bitrate
            file = max(m['video_info']['variants'], key=lambda x: x.get('bitrate', 0))['url']
        if file:
            folder = os.path.join(bp.root_path, 'static/twitter_media', tweet['id_str'])
            localfile = Path(download(file, folder, basename=m['id_str']))
            if localfile.suffix != '.mp4':
                ocr_text = pytesseract.image_to_string(str(localfile))
            query = 'INSERT INTO media_data VALUES (%s, %s, %s, %s)'
            with cnx.cursor() as cursor:
                cursor.execute(query, (m['id_str'], tweet['id_str'], localfile.suffix, ocr_text))
    cnx.commit()


def save_tweet_gql(tweet):
    import datetime
    import html
    import json
    favsquery = ('INSERT INTO favorites (id, user_id, text, timestamp, favs, retweets, raw_json, in_reply_to) '
                 'VALUES (%s, %s, %s, %s, %s, %s, %s, %s) '
                 'ON DUPLICATE KEY UPDATE favs=%s, retweets=%s, is_deleted=0, raw_json=%s')
    userquery = 'INSERT INTO users (id, username, displayname) VALUES (%s, %s, %s) ON DUPLICATE KEY UPDATE username=%s, displayname=%s'
    timestamp = datetime.datetime.strptime(tweet['created_at'],
                                           '%a %b %d %H:%M:%S %z %Y').strftime('%Y-%m-%d %H:%M:%S')
    user = tweet['user']
    text = tweet['full_text']
    text = html.unescape(text)
    json_tweet = json.dumps(tweet)
    reply = None
    if reply_obj := tweet.get("reply_to"):
        reply = json.dumps(reply_obj)
    with cnx.cursor() as cursor:
        cursor.execute(favsquery, (str(tweet['id_str']), str(user['id_str']), text, timestamp,
                                   str(tweet['favorite_count']), str(tweet['retweet_count']), json_tweet, reply,
                                   str(tweet['favorite_count']), str(tweet['retweet_count']), json_tweet))
        cursor.execute(userquery, (str(user['id_str']), user['screen_name'], user['name'], user['screen_name'], user['name']))
    cnx.commit()
    save_media_gql(tweet)

def save_media_gql(tweet):
    try:
        media = tweet['extended_entities']['media']
    except:
        return
    with cnx.cursor() as cursor:
        cursor.execute('UPDATE favorites SET has_media=1 WHERE id=%s', (tweet['id_str'],))
    cnx.commit()
    for m in media:
        file = m['media_url_https']
        ocr_text = None
        if m['type'] == 'video':
            # Find the video with the highest bitrate
            file = max(m['video_info']['variants'], key=lambda x: x.get('bitrate', 0))['url']
        if file:
            folder = os.path.join(bp.root_path, 'static/twitter_media', tweet['id_str'])
            localfile = Path(download(file, folder, basename=m['id_str']))
            if localfile.suffix != '.mp4':
                ocr_text = pytesseract.image_to_string(str(localfile))
            query = 'INSERT IGNORE INTO media_data VALUES (%s, %s, %s, %s)'
            with cnx.cursor() as cursor:
                cursor.execute(query, (m['id_str'], tweet['id_str'], localfile.suffix, ocr_text))
    cnx.commit()

def build_tweet_object_gql(content):
    if content["__typename"] == "TweetTombstone":
        return None
    if not content.get("legacy"):
        content = content["tweet"]
    tweet = content["legacy"]
    user = content["core"]["user_results"]["result"]["legacy"]
    user["id_str"] = content["core"]["user_results"]["result"]["rest_id"]
    tweet["user"] = user
    return tweet


def get_tweet(tweet_id):
    r = requests.get('https://api.twitter.com/1.1/statuses/show.json',
                     auth=auth, params={'id': tweet_id, 'tweet_mode': 'extended'})
    if r.status_code == requests.codes['ok']:
        return r.json()
    print(r.json())
    return None

# cd /var/www/flask_server; .venv/bin/python3 -m flask twitter get-favs
@bp.cli.command('get-favs')
def get_favs():

    setup()

    url = "https://twitter.com/i/api/graphql/NpYLg91N41FVTp-5l4Ntow/Likes"

    q_variables = {
        "userId": "1634007006",
        "count": 100,
        "includePromotedContent": False,
        "withClientEventToken": False,
        "withBirdwatchNotes": False,
        "withVoice": True,
        "withV2Timeline": True
    }
    q_features = {
        "responsive_web_graphql_exclude_directive_enabled": True,
        "verified_phone_label_enabled": False,
        "creator_subscriptions_tweet_preview_api_enabled": True,
        "responsive_web_graphql_timeline_navigation_enabled": True,
        "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
        "c9s_tweet_anatomy_moderator_badge_enabled": True,
        "tweetypie_unmention_optimization_enabled": True,
        "responsive_web_edit_tweet_api_enabled": True,
        "graphql_is_translatable_rweb_tweet_is_translatable_enabled": True,
        "view_counts_everywhere_api_enabled": True,
        "longform_notetweets_consumption_enabled": True,
        "responsive_web_twitter_article_tweet_consumption_enabled": False,
        "tweet_awards_web_tipping_enabled": False,
        "freedom_of_speech_not_reach_fetch_enabled": True,
        "standardized_nudges_misinfo": True,
        "tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled": True,
        "rweb_video_timestamps_enabled": True,
        "longform_notetweets_rich_text_read_enabled": True,
        "longform_notetweets_inline_media_enabled": True,
        "responsive_web_media_download_video_enabled": False,
        "responsive_web_enhance_cards_enabled": False
    }

    headers = {
        "cookie": "guest_id_marketing=v1%253A168780805020623218; guest_id_ads=v1%253A168780805020623218; personalization_id=%22v1_N6su6BsOlDgoAGzzmiLMfw%3D%3D%22; guest_id=v1%253A168780805020623218",
        "Host": "twitter.com",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.5",
        "Accept-Encoding": "gzip, deflate, br",
        "Referer": "https://twitter.com/atbilly/likes",
        "content-type": "application/json",
        "X-Client-UUID": "40891ce8-e2e3-4ad0-b12f-161e27edb24e",
        "x-twitter-auth-type": "OAuth2Session",
        "x-csrf-token": "0cd67c7b09efa8d4ee51dd5464032d8057bbbbcc9288578da119fb2f957f45e86c779d14dded96839e9195318d51d2213cc84a458d3d41a609a87bbbcc289bb3e108495bb15d1655df1312407590f4c5",
        "x-twitter-client-language": "en",
        "x-twitter-active-user": "yes",
        "x-client-transaction-id": "g8FzFAgsDNtlf2Xfb8np3Nf/YEqZEUPnQGoAsKgZnktuzbP3CnEp+3CzbFyku/vL955dw4JWRI7clk5VN140sizzBX+lgg",
        "DNT": "1",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
        "authorization": "Bearer AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA",
        "Connection": "keep-alive",
        "Cookie": 'personalization_id="v1_fOHbRWqAQat6mcTyuDHQtQ=="; ct0=0cd67c7b09efa8d4ee51dd5464032d8057bbbbcc9288578da119fb2f957f45e86c779d14dded96839e9195318d51d2213cc84a458d3d41a609a87bbbcc289bb3e108495bb15d1655df1312407590f4c5; dnt=1; ads_prefs="HBISAAA="; remember_checked_on=1; twid=u%3D1634007006; auth_token=3400bb8f4fb001e13ceb8a4c58347865f9a12bb7; night_mode=1; guest_id_marketing=v1%3A168926456667174133; guest_id_ads=v1%3A168926456667174133; mbox=PC#e14e8421abee425080df952249a11ac7.34_0#1755279199|session#cdd4d3a30f8a400088696a60b14b0a72#1692036259; _ga=GA1.2.1501679660.1687807529; des_opt_in=Y; guest_id=v1%3A168926456667174133; lang=en',
        "TE": "trailers"
    }


    def gen():
        select_query = "SELECT id FROM favorites WHERE id=%s"

        while True:
            querystring = {
                "variables": json.dumps(q_variables),
                "features": json.dumps(q_features)
            }
            r = requests.request("GET", url, headers=headers, params=querystring)
            entries = r.json()["data"]["user"]["result"]["timeline_v2"]["timeline"]["instructions"][0]["entries"]
            q_variables["cursor"] = entries[-1]["content"]["value"]
            for i in entries:
                if i["content"]["entryType"] == "TimelineTimelineItem":
                    if not i["content"]["itemContent"].get("tweet_results"):
                        print(f'Failed to fetch tweet: {i["entryId"]}')
                        continue

                    content = i["content"]["itemContent"]["tweet_results"]["result"]
                    try:
                        out = build_tweet_object_gql(content)
                    except:
                        print(json.dumps(content))
                        raise
                    with cnx.cursor() as cursor:
                        cursor.execute(select_query, (out["id_str"],))
                        row = cursor.fetchone()
                        if row:
                            print("Done!")
                            return
                    out["reply_to"] = None
                    if quoted := content.get("quoted_status_result"):
                        out["reply_to"] = build_tweet_object_gql(quoted["result"])
                    print(f'Saving tweet: {out["id_str"]}')
                    yield out

    for i in gen():
        save_tweet_gql(i)
