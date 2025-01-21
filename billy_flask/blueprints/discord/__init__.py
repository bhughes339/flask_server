
from datetime import datetime
import json
from warnings import filterwarnings
import click

import requests
from flask import Blueprint, current_app, jsonify, request, session

from billy_flask.db import get_db, mysql_warning
from billy_flask.util import download

bp = Blueprint('discord', __name__, url_prefix='/discord', static_folder='static')
cnx = None
config = None


@bp.before_request
def setup():
    global cnx, config
    config = current_app.config['DISCORD']
    cnx = get_db('slack')
    filterwarnings('ignore', category=mysql_warning())


@bp.route('/interactions', methods=['POST', 'GET'])
def process_interaction():
    if not validate(request):
        return jsonify({'error': 'Secret validation failed.'}), 401
    int_id = request.json['data']['id']

    # Pinhit
    if int_id == '900178417058713620':
        args = {x['name']: x['value'] for x in request.json['data'].get('options', [])}
        embeds = get_pin(text=args.get('text', ''), user=args.get('user', ''))
        if not embeds:
            return jsonify({
                'type': 4,
                'data': {
                    'content': 'No pins found.',
                    'flags': 1<<6
                }
            })
        return jsonify({
            'type': 4,
            'data': {
                'embeds': embeds
            }
        })

    # POTD
    elif int_id == '900091392615923832':
        embeds = get_pin(potd=True)
        if not embeds:
            return jsonify({
                'type': 4,
                'data': {
                    'content': 'No POTDs today :('
                }
            })
        return jsonify({
            'type': 4,
            'data': {
                'embeds': embeds
            }
        })
    
    # cigs
    elif int_id == '900415835590520893':
        url = 'https://www.reddit.com/api/v1/access_token'
        reddit_config = current_app.config['REDDIT']
        headers = {
            'user-agent': reddit_config['user_agent']
        }
        from requests.auth import HTTPBasicAuth
        r = requests.post(
            url,
            headers=headers,
            data={'grant_type': 'client_credentials'},
            auth=HTTPBasicAuth(reddit_config['client_id'], reddit_config['client_secret'])
        )
        token_cnx = get_db('tokens')
        with token_cnx.dict_cursor() as cursor:
            try:
                token = r.json()['access_token']
                query = "UPDATE oauth_tokens SET token=%s WHERE service='reddit'"
                cursor.execute(query, (token))
            except:
                query = "SELECT token FROM oauth_tokens WHERE service='reddit'"
                cursor.execute(query)
                token = cursor.fetchone()['token']

        url = 'https://oauth.reddit.com/r/cigarettes/random'
        headers = {
            'Authorization': f'bearer {token}',
            'Content-Type': 'application/json',
            'user-agent': reddit_config['user_agent']
        }
        r = requests.get(url, headers=headers)
        payload = r.json()
        post = payload[0]['data']['children'][0]['data']
        # data = {'embeds': [{
        #     'title': post['title'],
        #     'description': post.get('selftext', ''),
        #     'timestamp': datetime.fromtimestamp(float(post['created_utc'])).isoformat(),
        #     'url': f'https://reddit.com{post["permalink"]}',
        #     'author': {
        #         'name': post["author"]
        #     }}]
        # }
        embed = {
            'title': post['title'],
            'description': post.get('selftext', ''),
            'timestamp': datetime.fromtimestamp(float(post['created_utc'])).isoformat(),
            'url': f'https://reddit.com{post["permalink"]}',
            'author': {
                'name': post["author"]
            }
        }
        if post.get('post_hint', None) == 'image':
            embed['image'] = {'url': post['url']}
        return jsonify({
            'type': 4,
            'data': {'embeds': [embed]}
        })
    
    # reddit
    elif int_id == '981906140696813618':
        subreddit = request.json['data']['options'][0]['value']
        url = 'https://www.reddit.com/api/v1/access_token'
        reddit_config = current_app.config['REDDIT']
        headers = {
            'user-agent': reddit_config['user_agent']
        }
        from requests.auth import HTTPBasicAuth
        r = requests.post(
            url,
            headers=headers,
            data={'grant_type': 'client_credentials'},
            auth=HTTPBasicAuth(
                reddit_config['client_id'], reddit_config['client_secret'])
        )
        token_cnx = get_db('tokens')
        with token_cnx.dict_cursor() as cursor:
            try:
                reddit_token = r.json()['access_token']
                query = "UPDATE oauth_tokens SET token=%s WHERE service='reddit'"
                cursor.execute(query, (reddit_token))
            except Exception as e:
                print(str(e))
                query = "SELECT token FROM oauth_tokens WHERE service='reddit'"
                cursor.execute(query)
                reddit_token = cursor.fetchone()['token']

        url = f'https://oauth.reddit.com/r/{subreddit}/random'
        headers = {
            'Authorization': f'bearer {reddit_token}',
            'Content-Type': 'application/json',
            'user-agent': reddit_config['user_agent']
        }
        r = requests.get(url, headers=headers)
        payload = r.json()
        if isinstance(payload, list):
            payload = payload[0]
        try:
            posts_list = payload['data']['children']
            post = posts_list[1]['data'] if len(posts_list) > 1 else posts_list[0]['data']
            assert post["permalink"]
        except:
            if payload.get("reason", "").lower() == "private":
                msg = f"r/{subreddit} is private"
            else:
                msg = f"Can't find r/{subreddit}"
            return jsonify({
                'type': 4,
                'data': {
                    'content': msg
                }
            })

        # data = {'embeds': [{
        #     'title': post['title'],
        #     'description': post.get('selftext', ''),
        #     'timestamp': datetime.fromtimestamp(float(post['created_utc'])).isoformat(),
        #     'url': f'https://reddit.com{post["permalink"]}',
        #     'author': {
        #         'name': post["author"]
        #     }}]
        # }
        embed = {
            'title': post['title'],
            'description': post.get('selftext', ''),
            'timestamp': datetime.fromtimestamp(float(post['created_utc'])).isoformat(),
            'url': f'https://reddit.com{post["permalink"]}',
            'footer': {
                "text": f'🔼 {post["score"]} • 💬 {post["num_comments"]}'
            },
            'author': {
                'name': f"r/{subreddit}"
            }
        }
        post_hint = post.get('post_hint', '')
        if post_hint == 'image':
            embed['image'] = {'url': post['url']}
        elif 'hosted:video' in post_hint:
            embed['image'] = {
                'url': post['preview']['images'][0]['source']['url'],
                'proxy_url': "google.com"
            }
            embed['description'] += f"\n{post['url']}"
        elif 'video' in post_hint:
            embed['image'] = {
                'url': post['media']['oembed']['thumbnail_url'],
                'proxy_url': "google.com"
            }
            embed['description'] += f"\n{post['url']}"
        
        embed['description'] = embed['description'][:4096]

        if post["over_18"] and 'image' in embed:
            url = embed.pop("image")['url']
            embed['description'] = F"[Potentially NSFW link]({url})\n\n{embed['description']}"
            embed['description'] = embed['description'][:4096]
        # except Exception as e:
        #     import traceback
        #     from pprint import pprint
        #     pprint(payload)
        #     return jsonify({
        #         'type': 4,
        #         'data': {
        #             'content': traceback.format_exc()
        #         }
        #     })

        return jsonify({
            'type': 4,
            'data': {'embeds': [embed]}
        })


    # Pin
    elif int_id == '900732779367645214':
        import json, html
        payload = request.json['data']
        pin_id = payload['target_id']
        pin_obj = payload['resolved']['messages'][pin_id]
        query = (
            "INSERT IGNORE INTO pins (id, text, user_id, pinned_by, channel_id, timestamp, raw_json)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s)"
        )
        args = (
            pin_id,
            html.unescape(pin_obj['content']), # Might not be needed
            pin_obj['author']['id'],
            request.json['member']['user']['id'],
            pin_obj['channel_id'],
            pin_obj['timestamp'],
            json.dumps(request.json, separators=(',', ':'))
        )
        discord_cnx = get_db('discord')
        with discord_cnx.cursor() as cursor:
            cursor.execute(query, args)
        discord_cnx.commit()
        link = f"https://discord.com/channels/{request.json['guild_id']}/{pin_obj['channel_id']}/{pin_id}"
        return jsonify({
            'type': 4,
            'data': {
                'content': f"<@{request.json['member']['user']['id']}> pinned a message: [Link]({link})"
            }
        })
    
    elif int_id == '905437083601076294':
        from pprint import pprint
        pprint(request.json['data'])
    elif request.json['type'] == 1:
        return jsonify({'type': 1})


def validate(flask_request):
    from nacl.signing import VerifyKey
    from nacl.exceptions import BadSignatureError

    public_key = config['public_key']
    verify_key = VerifyKey(bytes.fromhex(public_key))

    sig = flask_request.headers.get('X-Signature-Ed25519')
    ts = flask_request.headers.get('X-Signature-Timestamp')
    body = flask_request.get_data(as_text=True)

    try:
        return verify_key.verify(f'{ts}{body}'.encode(), bytes.fromhex(sig))
    except BadSignatureError:
        return None


def get_pin(potd=False, text='', user=''):
    args = []
    query = (
        'SELECT pins.text, u1.name, u1.avatar, channels.name as channel, pins.timestamp, u2.name as pinnedby'
        ' FROM pins'
        ' INNER JOIN users u1 ON pins.userid=u1.id'
        ' INNER JOIN users u2 ON pins.pinnedby=u2.id'
        ' INNER JOIN channels ON pins.channel=channels.id'
    )
    if potd:
        today = datetime.today()
        query += (
            ' WHERE day(FROM_UNIXTIME(pins.timestamp))=%s'
            ' AND month(FROM_UNIXTIME(pins.timestamp))=%s'
            ' AND year(FROM_UNIXTIME(pins.timestamp))!=%s'
            ' ORDER BY pins.timestamp ASC LIMIT 10'
        )
        args.extend([today.day, today.month, today.year])
    else:
        if text:
            query += ' WHERE pins.text REGEXP %s'
            args.append(f'\\b{text.strip()}\\b')
        if user:
            query += ' AND u1.id=%s'
            args.append(user.strip())
        query += ' ORDER BY pins.timestamp DESC LIMIT 10' if text else ' ORDER BY RAND() LIMIT 1'
    with cnx.dict_cursor() as cursor:
        cursor.execute(query, args)
        pins = cursor.fetchall()
    embeds = []
    for p in pins:
        embeds.append({
            'description': p['text'],
            'timestamp': datetime.fromtimestamp(float(p['timestamp'])).isoformat(),
            'author': {
                'name': p['name'],
                'icon_url': p['avatar']
            },
            'footer': {
                'text': f'📌 by {p["pinnedby"]}'
            }
        })
    return embeds


@bp.cli.command("update")
def update_user_list():
    setup()
    slack_config = current_app.config['SLACK']
    token = slack_config['bot_token']
    with cnx.cursor() as cursor:
        # Update users
        result = requests.get('https://slack.com/api/users.list', params={'token': token}).json()
        for i in result['members']:
            avi = i['profile']['image_192']
            user = i['profile']['display_name'] or i['name']
            query = "INSERT INTO users (id, name, avatar) VALUES (%s, %s, %s) ON DUPLICATE KEY UPDATE name=%s, avatar=%s"
            cursor.execute(query, (i['id'], user, avi, user, avi))

    query = (
        'SELECT users.name AS name, users.id AS id, COUNT(*) AS ct'
        ' FROM (pins JOIN users ON (pins.userid = users.id))'
        ' GROUP BY users.name ORDER BY COUNT(*) DESC'
    )
    with cnx.dict_cursor() as cursor:
        cursor.execute(query)
        users = cursor.fetchall()
    userlist = [{'name': x['name'], 'value': x['id']} for x in users]

    url = (
        f"{config['api_endpoint']}"
        f"/applications/{config['app_id']}"
        f"/guilds/{config['dvvi_id']}"
        "/commands"
    )
    opts = {
        "name": "pinhit",
        "description": "Pinhit",
        "type": 1,
        "options": [{
            "name": "text",
            "description": "Text to search",
            "type": 3
        },{
            "name": "user",
            "description": "Filter by user",
            "type": 3,
            "choices": userlist
        }]
    }

    headers = {
        "Authorization": f"Bearer {config['cred_token']}"
    }

    r = requests.post(url, headers=headers, json=opts)

    print(r.json())


@bp.cli.command("upsert-command")
@click.argument('name', nargs=1)
@click.argument('description', nargs=1)
@click.argument('cmd_type', nargs=1)
@click.argument('options', nargs=1)
def upsert_command(name, description, cmd_type, options=None):
    """
    Usage:
    ```
    FLASK_APP=billy_flask flask discord upsert-command reddit "bad website" 1 '[{"type": "3", "name": "subreddit", "description": "which one", "required": "true"}]'
    ```
    """
    setup()
    token = get_token()
    url = (
        f"{config['api_endpoint']}"
        f"/applications/{config['app_id']}"
        f"/guilds/{config['dvvi_id']}"
        "/commands"
    )
    headers = {
        "Authorization": f"Bearer {token}"
    }
    opts = {
        "name": name,
        "description": description,
        "type": cmd_type
    }

    if options:
        opts["options"] = json.loads(options)

    r = requests.post(url, headers=headers, json=opts)

    print(r.json())


def get_token():
    """
    Usage:
    ```
    FLASK_APP=billy_flask flask discord get-token
    ```
    """
    if not config:
        setup()
    url = f"{config['api_endpoint']}/oauth2/token"
    data = {
        'grant_type': 'client_credentials',
        'scope': 'applications.commands.update'
    }
    headers = {
        'Content-Type': 'application/x-www-form-urlencoded'
    }

    r = requests.post(url, data=data, headers=headers, auth=(config['client_id'], config['client_secret']))
    return r.json()["access_token"]
