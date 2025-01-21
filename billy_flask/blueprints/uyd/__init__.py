from flask import (
    Blueprint,
    url_for,
    redirect,
    render_template,
    request,
    make_response,
    jsonify,
    send_file,
)
from flask_cors import CORS
from pathlib import Path
from billy_flask.db import get_db
import random
from datetime import timedelta
import mimetypes

BP_NAME = "uyd"

bp = Blueprint(
    BP_NAME,
    __name__,
    url_prefix=f"/{BP_NAME}",
    template_folder="templates",
    static_folder="static",
)
cnx = None
config = None

eps_folder = Path(bp.static_folder) / "uyd"

LAST_EPISODE = 803

CORS(bp)


@bp.before_request
def setup():
    global cnx
    cnx = get_db("uyd")


def get_episode_file(episode):
    ep_file = eps_folder / f"{int(episode):03d}.mp3"
    return ep_file


def static_ep(episode):
    ep_file = get_episode_file(episode)
    return url_for(".static", filename=f"uyd/{ep_file.name}")


def next_episode(episode):
    next_ep = int(episode)
    while True:
        next_ep += 1
        if next_ep > LAST_EPISODE:
            next_ep = 1
        if next_ep == 89:  # skip the gas leak episode lol
            next_ep += 1
        ep_file = get_episode_file(next_ep)
        if ep_file.is_file():
            break

    return next_ep, ep_file


@bp.route("/random", methods=["GET"])
def random_ep():
    # file_list = list(eps_folder.glob('*'))
    # rand_ep = random.choice(file_list).relative_to(bp.static_folder)
    query = "SELECT * FROM episodes ORDER BY RAND() LIMIT 1;"
    with cnx.cursor() as cursor:
        ep_file = eps_folder / "not_a_file.mp3"
        while not ep_file.is_file():
            cursor.execute(query)
            ep_num, date_str, url = cursor.fetchone()
            ep_file = eps_folder / f"{int(ep_num):03d}.mp3"

    # date_fmt = datetime.strptime(date_str, "%Y-%m-%d").strftime("%B %d %Y")
    date_fmt = date_str.strftime("%d %b %Y")
    rand_time = random.randrange(300, 2400)
    src = url_for(".static", filename=f"uyd/{ep_file.name}")
    # src = url + f'#t={str(rand_time)}'
    return render_template("player.html", src=src, ep=ep_num, date=date_fmt)
    # return redirect(url_for('.static', filename=rand_ep) + f'#t={str(rand_time)}')


@bp.route("/play/<int:episode>", methods=["GET"])
def play(episode):
    query = "SELECT * FROM episodes WHERE episode_number=%s"
    with cnx.cursor() as cursor:
        cursor.execute(query, (episode,))
        res = cursor.fetchone()
        if res:
            ep_num, date_str, url = res
        else:
            return jsonify("Episode not found!")

    date_fmt = date_str.strftime("%d %b %Y")

    # response = make_response(render_template('player.html', src=url, ep=ep_num, date=date_fmt))
    # response.headers.add('Access-Control-Allow-Origin', '*')
    # return response
    return render_template("player.html", src=url, ep=ep_num, date=date_fmt)


@bp.route("/episode/<int:episode>", methods=["GET"])
def episode(episode):
    file = eps_folder / "compressed" / f"{int(episode):03d}.mp3"
    if not file.exists():
        file = eps_folder / f"{int(episode):03d}.mp3"
    return send_file(file)


@bp.route("/replay", methods=["GET"])
def replay():
    with cnx.cursor() as cursor:
        cursor.execute("SELECT episode, time FROM replay WHERE id=%s", ("current_ep",))
        episode, time = cursor.fetchone()
        cursor.execute(
            "SELECT date FROM episodes WHERE episode_number=%s", (str(episode),)
        )
        ep_date = cursor.fetchone()[0]

    ep_file = eps_folder / f"{int(episode):03d}.mp3"
    url = url_for(".static", filename=f"uyd/compressed/{ep_file.name}")

    return render_template(
        "replay.html",
        url=url,
        url_full=url_for(".static", filename=f"uyd/compressed/{ep_file.name}", _external=True),
        time=time,
        longtime=seconds_to_time(time),
        mime=mimetypes.guess_type(ep_file)[0],
        ep_num=episode,
        ep_date=ep_date,
    )


@bp.route("replay_update")
def replay_update():
    time = int(float(request.args.get("time", 0)))
    with cnx.cursor() as cursor:
        cursor.execute("UPDATE replay SET time=%s WHERE id=%s", (time, "current_ep"))
    cnx.commit()
    return jsonify({"formatted_time": str(timedelta(seconds=time))})


@bp.route("replay_update_start")
def replay_update_start():
    episode = request.args.get("episode")
    time = int(float(request.args.get("time", 0)))
    with cnx.cursor() as cursor:
        cursor.execute(
            "UPDATE episodes SET start_time=%s WHERE episode_number=%s", (time, episode)
        )
    cnx.commit()
    return jsonify({"formatted_time": str(timedelta(seconds=time))})


@bp.route("replay_skip")
def replay_skip():
    with cnx.cursor() as cursor:
        cursor.execute("SELECT episode FROM replay WHERE id=%s", ("current_ep",))
        episode = cursor.fetchone()[0]

    episode += 1
    # skip the gas leak episode lol
    if episode == 89:
        episode += 1
    ep_file = eps_folder / f"{int(episode):03d}.mp3"
    while not ep_file.is_file():
        episode += 1
        ep_file = eps_folder / f"{int(episode):03d}.mp3"

    with cnx.cursor() as cursor:
        cursor.execute(
            "SELECT start_time FROM episodes WHERE episode_number=%s", (episode,)
        )
        result = cursor.fetchone()
        time = result[0] if result else 0
        cursor.execute(
            "UPDATE replay SET episode=%s, time=%s WHERE id=%s",
            (episode, time, "current_ep"),
        )
    cnx.commit()

    return jsonify("ok")


@bp.route("fixstart")
def fixstart():
    episode = request.args.get("ep")
    with cnx.cursor() as cursor:
        cursor.execute(
            "SELECT start_time FROM episodes WHERE episode_number=%s", (episode,)
        )
        result = cursor.fetchone()
        time = result[0] if result else 0
    mime = mimetypes.guess_type(get_episode_file(episode))[0]
    return render_template(
        "fixstart.html", ep_num=episode, url=static_ep(episode), time=time, mime=mime
    )


@bp.route("fixstart_skip")
def fixstart_skip():
    episode = request.args.get("ep")
    new_ep, ep_file = next_episode(episode)
    return jsonify({"next_ep": new_ep})


def seconds_to_time(seconds):
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    return (f"{h}h" if h else "") + (f"{m:02d}m" if m else "") + f"{s:02d}s"
