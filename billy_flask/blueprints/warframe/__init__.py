import os
import json
import datetime

import requests
from flask import Blueprint, current_app, render_template, request, url_for, jsonify

from billy_flask.db import get_db

bp = Blueprint('warframe', __name__,
               url_prefix='/warframe', template_folder='templates')
cnx = None

ROWS = 5

DECIMAL = False

row_html = ('<div class="wrapper">'
            '<div class="typeahead__container">'
            '<div class="typeahead__field">'
            '<span class="typeahead__query">'
            '<input class="item" name="item[query]" type="search" placeholder="Item name" autocomplete="off">'
            '</span></div></div>'
            '<img src="" class="thumb">'
            '<div class="price"></div>'
            '</div>')


@bp.before_request
def setup():
    global cnx
    cnx = get_db('warframe')


@bp.route('/price_check')
def price_check():
    html_temp = ''
    for _ in range(ROWS):
        html_temp += row_html

    return render_template('price_check.html', row_html=html_temp)


@bp.route('/_get_row_html')
def get_row_html():
    return jsonify({'row_html': row_html})


@bp.route('/_get_itemlist')
def get_itemlist():
    with cnx.cursor() as cursor:
        cursor.execute('SELECT item_name FROM market_items')
        items = cursor.fetchall()
    return jsonify([x[0] for x in items])


@bp.route('/_get_setlist')
def get_setlist():
    with cnx.cursor() as cursor:
        cursor.execute("SELECT item_name FROM market_items WHERE item_name REGEXP '.*Set$'")
        sets = cursor.fetchall()
    return jsonify([x[0].replace(' Set', '') for x in sets])


@bp.route('/_get_itemset')
def get_itemset():
    basename = request.args.get('base', '')
    if not basename:
        return jsonify(False)
    with cnx.cursor() as cursor:
        cursor.execute('SELECT item_name FROM market_items WHERE item_name LIKE CONCAT(%s, %s)', (basename, '%'))
        parts = [x[0] for x in cursor.fetchall()]
    parts.remove(basename + ' Set')
    parts.insert(0, basename + ' Set')
    return jsonify(parts)


@bp.route('/_get_avg_price')
def get_avg_price():
    item = request.args.get('item', '')
    data = price_data(item)
    return jsonify(data)


def price_data(item):
    data = {}
    if not item:
        data['status'] = 'noitem'
        return data
    with cnx.dict_cursor() as cursor:
        cursor.execute('SELECT url_name, thumb, item_name, ducats, wiki_link FROM market_items WHERE item_name=%s', (item))
        fetch = cursor.fetchone()
    if not fetch:
        data['status'] = 'notfound'
        return data
    stats_url = 'https://api.warframe.market/v1/items/{0}/statistics'
    url_name = fetch['url_name']
    data = {
        'name': fetch['item_name'],
        'link': 'https://warframe.market/items/' + url_name,
        'thumb': 'https://warframe.market/static/assets/' + fetch['thumb'],
        'wiki_link': fetch['wiki_link']
    }
    ducats = fetch['ducats']
    r = requests.get(stats_url.format(url_name))
    if r.status_code != requests.codes['ok']:
        data['status'] = 'notfound'
        return data
    payload = r.json()
    daystats = payload['payload']['statistics_closed']['90days']
    try:
        days = int(request.args.get('days', '7'))
    except:
        days = 7
    from_date = (datetime.datetime.now() - datetime.timedelta(days=days+1)).isoformat()
    filtered_list = list(filter(lambda x: x.get('mod_rank', 0) == 0 and x['datetime'] > from_date, daystats))
    try:
        volume = sum([x['volume'] for x in filtered_list])
        # avg_price = sum([x['moving_avg'] for x in filtered_list]) / len(filtered_list)
        avg_price = sum([(x['avg_price'] * x['volume']) for x in filtered_list]) / volume
        if days != len(filtered_list):
            data['days'] = str(len(filtered_list))
        data['price'] = str(round(avg_price, 2) if DECIMAL else int(avg_price))
        data['volume'] = str(volume)
        if ducats:
            data['ducats'] = str(round(int(ducats) / avg_price, 2))
        data['status'] = 'ok'
        return data
    except Exception as e:
        print(e)
        data['status'] = 'nodata'
        return data
