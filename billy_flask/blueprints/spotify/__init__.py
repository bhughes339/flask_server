import base64
from datetime import datetime
import os
import re

from flask.json import jsonify
import requests
from flask import (Blueprint, current_app, redirect, render_template, request,
                   session, url_for)

from flask_cors import CORS

bp = Blueprint('spotify', __name__,
               url_prefix='/spotify', template_folder='templates')
config = None

CORS(bp)

OAUTH_PARAMS = {
    'auth_url': 'https://accounts.spotify.com/authorize',
    'auth_params': {
        'response_type': 'code',
        'scope': 'user-top-read'
    },
    'callback_url': 'https://accounts.spotify.com/api/token',
    'callback_params': { 'grant_type': 'authorization_code' },
}


@bp.before_request
def setup():
    global config
    config = current_app.config['SPOTIFY']
    basic_auth = base64.b64encode(f"{config['client_id']}:{config['client_secret']}".encode('ascii')).decode()
    OAUTH_PARAMS['basic_auth'] = f"Basic {basic_auth}"



@bp.route('/auth')
def oauth_flow(dest_url=None):
    import base64, requests
    if dest_url:
        session['oauth_redirect'] = dest_url
        params = {
            'client_id': config['client_id'],
            'redirect_uri': url_for('.oauth_flow', _external=True),
            **OAUTH_PARAMS['auth_params']
        }
        r = requests.Request('GET', url = OAUTH_PARAMS['auth_url'], params=params).prepare()
        return redirect(r.url)
    code = request.args.get('code')
    payload = {
        'code': code,
        'redirect_uri': url_for('.oauth_flow', _external=True),
        **OAUTH_PARAMS['callback_params']
    }
    b64 = base64.b64encode(f"{config['client_id']}:{config['client_secret']}".encode('ascii'))
    headers = { 'Authorization': f'Basic {b64.decode()}' }
    r = requests.post(OAUTH_PARAMS['callback_url'], headers=headers, data=payload)
    session['oauth_access_token'] = r.json()['access_token']
    session['oauth_refresh_token'] = r.json()['refresh_token']
    dest_url = session['oauth_redirect']
    del session['oauth_redirect']
    return redirect(dest_url)


@bp.route('/')
@bp.route('/top_artists')
def get_top_artists():
    if 'oauth_access_token' in session:
        refresh_token()
    else:
        return oauth_flow(url_for(request.endpoint))
    
    print(session['oauth_access_token'])

    html = process_top(session['oauth_access_token'], 'artists')
    if html:
        return render_template('top.html', top_type='artists', top_list=html)
    


@bp.route('/top_tracks')
def get_top_tracks():
    if 'oauth_access_token' in session:
        refresh_token()
    else:
        return oauth_flow(url_for(request.endpoint))
    
    html = process_top(session['oauth_access_token'], 'tracks')
    if html:
        return render_template('top.html', top_type='tracks', top_list=html)


@bp.route('/new_albums')
def new_albums():
    if 'oauth_access_token' in session:
        refresh_token()
    else:
        return oauth_flow(url_for(request.endpoint))
    
    return render_template("new_albums.html")


@bp.route('/search_for_embed')
def search_for_embed():
    # if 'oauth_access_token' in session:
    #     refresh_token()
    # else:
    #     return oauth_flow(url_for(request.endpoint))
    
    search_term = request.args.get('search')
    
    r = requests.get("https://open.spotify.com/search")
    access_token = re.search(r'{"accessToken":"([^"]+)', r.text).group(1)

    url = 'https://api.spotify.com/v1/search'
    headers = {
        'Authorization': f'Bearer {access_token}'
    }

    params = {"q": search_term, "type": "track"}

    payload = requests.get(url, headers=headers, params=params).json()

    track_id = payload["tracks"]["items"][0]["id"]

    return jsonify({"embed": f"https://open.spotify.com/embed/track/{track_id}"})


@bp.route('/_get_new_albums')
def _get_new_albums():
    this_year = str(datetime.now().year)
    
    url = 'https://api.spotify.com/v1/me/playlists'
    headers = {
        'Authorization': 'Bearer ' + session['oauth_access_token']
    }

    payload = requests.get(url, headers=headers).json()

    yearly_urls = list()
    saved_albums = set()
    for i in payload["items"]:
        if re.match(r"\d{4}", i["name"]):
            if i["name"] == this_year:
                tracks_in_playlist = requests.get(i["tracks"]["href"], headers=headers).json()
                for track in tracks_in_playlist["items"]:
                    saved_albums.add(track["track"]["album"]["id"])
            else:
                yearly_urls.append(i["tracks"]["href"])

    playlist_artists = set()
    new_album_artists = dict()
    
    for i in yearly_urls:
        payload = requests.get(i, headers=headers).json()

        for track in payload["items"]:
            artist = track["track"]["artists"][0]
            if artist["id"]:
                playlist_artists.add((artist["id"], artist["name"]))
    
    for a_id, a_name in playlist_artists:
        url = f"https://api.spotify.com/v1/artists/{a_id}/albums"
        params = {"limit": 50, "include_groups": "album,single"}
        payload = requests.get(url, headers=headers, params=params).json()
        if "items" in payload:
            new_albums = []
            for album in payload["items"]:
                album["added_to_yearly"] = (album["id"] in saved_albums)
                if album["release_date"].startswith(this_year):
                    # new_albums.append({f'{album["name"]} ({album["album_type"]})': album["external_urls"]["spotify"].replace("https://open.spotify.com/", "spotify://")})
                    new_albums.append(album)
            if new_albums:
                new_album_artists[a_name] = list(sorted(new_albums, key=lambda x: int(x["added_to_yearly"])))
        else:
            print(f"[ERROR] artist_id: {a_id} | artist_name: {a_name} | {payload}")
    
    return render_template("new_albums_body.html", new_album_artists=dict(sorted(new_album_artists.items(), key=lambda x: x[0])))


def refresh_token():
    data = {
        "grant_type": "refresh_token",
        "refresh_token": session['oauth_refresh_token'],
        "client_id": config['client_id'],
    }
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Authorization": OAUTH_PARAMS['basic_auth'],
    }
    payload = requests.post(OAUTH_PARAMS['callback_url'], headers=headers, data=data).json()
    session['oauth_access_token'] = payload['access_token']
    if 'refresh_token' in payload:
        session['oauth_refresh_token'] = payload['refresh_token']


def process_top(access_token, top_type):
    if top_type not in ['artists', 'tracks']:
        return None
    timeframes = ['short', 'medium', 'long']
    url = 'https://api.spotify.com/v1/me/top/' + top_type
    headers = {
        'Authorization': 'Bearer ' + access_token
    }
    params = {}
    html = ''
    for t in timeframes:
        params['time_range'] = t + '_term'
        r = requests.get(url, headers=headers, params=params)
        if r.status_code != requests.codes['ok']:
            return None
        response = r.json()
        html += list_to_html('menu' + t, response, t == 'short', genres=True)
    return html


def list_to_html(divname, response, active=False, genres=False):
    output = '<div id="{0}" class="tab-pane{1}"><ol>'.format(divname, ' active' if active else '')
    for i in response['items']:
        artists = (', '.join([x['name'] for x in i['artists']]) + ' - '
                   if 'artists' in i
                   else '')
        # url = i['external_urls']['spotify']
        url = i['uri']
        # output += f"<li><a href=\"{url}\">{artists}{i['name']}</a>"
        # output += f'<div title="{i["popularity"]}" class="pop circle" style="background: conic-gradient(green calc({i["popularity"]}*1%),#0000 0); a"></div>'
        output += f'<li><div title="{i["popularity"]}" class="pop circle" style="background: conic-gradient(green calc({i["popularity"]}*1%),#0000 0); a"></div>'
        output += f"<a href=\"{url}\">{artists}{i['name']}</a>"
        if genres:
            genre_list = [f'<a href="https://everynoise.com/engenremap-{re.sub(r"[^a-zA-Z0-9]", "", x)}.html", target="_blank">{x}</a>' for x in i.get("genres", [])]
            output += f'<span class="genres"> | Genres: {", ".join(genre_list)}</span>'
        output += '</li>'

    total_pop = sum([int(x["popularity"]) for x in response['items']]) / len(response['items'])
    output += f'</ol><span class="pop">Average popularity: <strong>{total_pop}</strong> / 100</span></div>'
    return output
