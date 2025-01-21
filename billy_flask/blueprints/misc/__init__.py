import json
import subprocess
from tempfile import NamedTemporaryFile, TemporaryDirectory
from flask import (Blueprint, current_app, redirect, render_template, request,
                   session, url_for, jsonify)

from billy_flask.db import get_db

import base64

from pathlib import Path

bp = Blueprint('misc', __name__,
               url_prefix='/misc', template_folder='templates', static_folder='static')
config = None


@bp.before_request
def setup():
    global cnx
    cnx = get_db('misc')

@bp.route('/gin')
def gin():
    session_score = session.get("session_score", "")
    return render_template('gin.html', session_score=session_score)

@bp.route('/ginsave', methods=["POST"])
def ginsave():
    scores = request.get_json()
    session["session_score"] = base64.b64encode(json.dumps(scores).encode()).decode()
    try:
        print(f"saving score: {len(scores['rounds'])}")
    except Exception as e:
        print(e)
    if max(scores["total"]["1"], scores["total"]["2"]) > 100:
        rounds = json.dumps(scores["rounds"])
        with cnx.cursor() as cursor:
            query = r"INSERT INTO ginscores VALUES (%s, %s, %s, %s, %s, %s) ON DUPLICATE KEY UPDATE rounds=%s, player1score=%s, player2score=%s"
            cursor.execute(query, (
                scores["date"],
                scores["names"]["1"],
                scores["names"]["2"],
                rounds,
                scores["total"]["1"],
                scores["total"]["2"],
                rounds,
                scores["total"]["1"],
                scores["total"]["2"],
            ))
        cnx.commit()
    return jsonify("ok")

@bp.route('/video')
def video():
    return render_template("video_plyr.html", video_url=url_for(".static", filename="kick.mp4"), video_ext="mp4")

@bp.route('/social', methods=['GET', 'POST'])
def social():
    if ssn := request.values.get("social"):
        print(ssn)
        return render_template('thanksmom.html')
    return render_template('social.html')
