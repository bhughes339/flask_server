import html
import json
import unicodedata

import requests
from flask import Blueprint, current_app, render_template, url_for, request, jsonify


bp = Blueprint('youtube', __name__,
               url_prefix='/youtube', template_folder='templates', static_folder='static')

api_key = None

api_urls = {
    'channel': 'https://www.googleapis.com/youtube/v3/channels',
    'playlistitems': 'https://www.googleapis.com/youtube/v3/playlistItems',
    'videos': 'https://www.googleapis.com/youtube/v3/videos'
}

playlist_params = {
    'key': None,
    'part': 'snippet',
    'maxResults': 50,
    'fields': 'items/snippet/resourceId/videoId,nextPageToken'
}

video_params = {
    'key': None,
    'part': 'statistics,snippet'
}


@bp.before_request
def setup():
    global api_key, playlist_params, video_params
    api_key = current_app.config['YOUTUBE']['api_key']
    playlist_params['key'] = video_params['key'] = api_key


@bp.route('/<channel_id>')
def youtube_likes(channel_id):
    main_css = url_for('static', filename='youtube/main.css')
    sorttable = url_for('static', filename='youtube/sorttable.js')
    table = create_table(channel_id)
    return render_template('youtube/youtube_table.html', table=table, main_css=main_css, sorttable=sorttable)


def create_table(channel_id):
    uploads_params = {
        'key': api_key,
        'part': 'contentDetails',
        'fields': 'items/contentDetails/relatedPlaylists/uploads',
        'id': channel_id
    }
    r = requests.get(api_urls['channel'], params=uploads_params)
    content = r.json()
    try:
        playlist_id = content['items'][0]['contentDetails']['relatedPlaylists']['uploads']
    except:
        del uploads_params['id']
        uploads_params['forUsername'] = channel_id
        r = requests.get(api_urls['channel'], params=uploads_params)
        content = r.json()
        try:
            playlist_id = content['items'][0]['contentDetails']['relatedPlaylists']['uploads']
        except:
            raise ValueError(json.dumps(content))
    return export_html(playlist_id)


def export_html(playlist_id):
    playlist_params = {
        'key': api_key,
        'part': 'snippet',
        'maxResults': 50,
        'fields': 'items/snippet/resourceId/videoId,nextPageToken',
        'playlistId': playlist_id
    }
    text = '<table class="sortable"><tbody><tr><th>Thumbnail</th><th>Title</th><th>Date</th><th>Dislike %</th><th># Ratings</th></tr>'
    items = []
    nextPage = True
    while nextPage:
        r = requests.get(api_urls['playlistitems'], params=playlist_params)
        content = r.json()
        for i in content['items']:
            items.append(i['snippet']['resourceId']['videoId'])
        nextPage = try_next(content)
        playlist_params['pageToken'] = nextPage
    chunks = [','.join(items[i:i+48]) for i in range(0, len(items), 48)]
    for c in chunks:
        video_params['id'] = c
        r = requests.get(api_urls['videos'], params=video_params)
        content = r.json()
        text += parse_ratings_html(content)
    text += '</tbody></table>'
    return text


def try_next(content):
    try:
        return content['nextPageToken']
    except:
        return None


def parse_ratings_html(content):
    table_row = '<tr><td><a href="{0}"><img src="{1}"></a></td><td>{2}</td><td>{3}</td><td>{4:.2%}</td><td>{5}</td></tr>'
    text = ''
    for j in content['items']:
        try:
            total_ratings = int(j['statistics']['likeCount']) + int(j['statistics']['dislikeCount'])
            dislike_ratio = float(j['statistics']['dislikeCount']) / float(total_ratings)
        except:
            pass
        else:
            snip = j['snippet']
            norm_title = unicodedata.normalize('NFC', snip['title']).encode('ascii', 'ignore').decode('utf-8')
            text += table_row.format('https://www.youtube.com/watch?v={0}'.format(j['id']),
                                     snip['thumbnails']['default']['url'], norm_title,
                                     snip['publishedAt'][:10], dislike_ratio, total_ratings)
    return text
