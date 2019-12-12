import base64
import os

import requests
from flask import (Blueprint, current_app, redirect, render_template, request,
                   session, url_for)

bp = Blueprint('spotify', __name__,
               url_prefix='/spotify', template_folder='templates')
config = None


@bp.before_request
def setup():
    global config
    config = current_app.config['SPOTIFY']


@bp.route('/top_artists')
def get_top_artists():
    if 'spotify_access_token' in session:
        html = process_top(session['spotify_access_token'], 'artists')
        if html:
            return render_template('top.html', top_type='artists', top_list=html)
        del session['spotify_access_token']
    session['spotify_redirect'] = url_for('.get_top_artists')
    return redirect(auth(url_for('.get_auth', _external=True)))


@bp.route('/top_tracks')
def get_top_tracks():
    if 'spotify_access_token' in session:
        html = process_top(session['spotify_access_token'], 'tracks')
        if html:
            return render_template('top.html', top_type='tracks', top_list=html)
        del session['spotify_access_token']
    session['spotify_redirect'] = url_for('.get_top_tracks')
    return redirect(auth(url_for('.get_auth', _external=True)))


@bp.route('/auth')
def get_auth():
    code = request.args.get('code')
    access_token = callback(url_for('.get_auth', _external=True), code)
    session['spotify_access_token'] = access_token
    return redirect(session['spotify_redirect'])


def auth(uri):
    url = 'https://accounts.spotify.com/authorize'
    params = {
        'client_id': config['client_id'],
        'response_type': 'code',
        'scope': 'user-top-read',
        'redirect_uri': uri
    }
    r = requests.Request('GET', url, params=params).prepare()
    return r.url


def callback(uri, code):
    url = 'https://accounts.spotify.com/api/token'
    payload = {
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': uri
    }
    b64 = base64.b64encode('{0}:{1}'.format(config['client_id'], config['client_secret']).encode('ascii'))
    headers = {
        'Authorization': 'Basic ' + b64.decode()
    }
    r = requests.post(url, headers=headers, data=payload)
    response = r.json()
    return response['access_token']


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
        else:
            response = r.json()
            html += list_to_html('menu' + t, response, t == 'short')
    return html


def list_to_html(divname, response, active=False):
    output = '<div id="{0}" class="tab-pane{1}"><ol>'.format(divname, ' active' if active else '')
    for i in response['items']:
        artists = (', '.join([x['name'] for x in i['artists']]) + ' - '
                   if 'artists' in i
                   else '')
        url = i['external_urls']['spotify']
        output += '<li><a href="{0}">{1}{2}</a></li>'.format(url, artists, i['name'])
    output += '</ol></div>'
    return output
