import base64
import os

import requests
from flask import (Blueprint, current_app, redirect, render_template, request,
                   session, url_for)

bp = Blueprint('spotify', __name__,
               url_prefix='/spotify', template_folder='templates')
config = None

OAUTH_PARAMS = {
    'auth_url': 'https://accounts.spotify.com/authorize',
    'auth_params': {
        'response_type': 'code',
        'scope': 'user-top-read'
    },
    'callback_url': 'https://accounts.spotify.com/api/token',
    'callback_params': { 'grant_type': 'authorization_code' }
}


@bp.before_request
def setup():
    global config
    config = current_app.config['SPOTIFY']


@bp.route('/')
@bp.route('/top_artists')
def get_top_artists():
    if 'oauth_access_token' in session:
        html = process_top(session['oauth_access_token'], 'artists')
        if html:
            return render_template('top.html', top_type='artists', top_list=html)
        del session['oauth_access_token']
    return oauth_flow(url_for(request.endpoint))


@bp.route('/top_tracks')
def get_top_tracks():
    if 'oauth_access_token' in session:
        html = process_top(session['oauth_access_token'], 'tracks')
        if html:
            return render_template('top.html', top_type='tracks', top_list=html)
        del session['oauth_access_token']
    return oauth_flow(url_for(request.endpoint))


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
    dest_url = session['oauth_redirect']
    del session['oauth_redirect']
    return redirect(dest_url)


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
        # url = i['external_urls']['spotify']
        url = i['uri']
        output += f"<li><a href=\"{url}\">{artists}{i['name']}</a></li>"
    output += '</ol></div>'
    return output
