from datetime import datetime, timedelta
import json
import re
import humanize
import requests


def get_latest_watched(gql_token, user_token, global_headers, only_following=False):
    """https://kawcco.com/twitch-graphql-api/viewedvideosedge.doc.html

    Format of `response.data.currentUser.viewedVideos.edges.[*]`:

    ```
    {
        "history": {
            "position": int,
            "updatedAt": str,
            "__typename": "VideoViewingHistory"
        },
        "node": {
            "animatedPreviewURL": str,
            "game": {
                "boxArtURL": str,
                "id": str,
                "displayName": str,
                "name": str,
                "__typename": "Game"
            },
            "id": str,
            "lengthSeconds": int,
            "owner": {
                "displayName": str,
                "id": str,
                "login": str,
                "profileImageURL": str,
                "primaryColorHex": str,
                "__typename": "User"
            },
            "previewThumbnailURL": str,
            "publishedAt": str,
            "self": {
                "isRestricted": bool,
                "viewingHistory": {
                    "position": int,
                    "updatedAt": str,
                    "__typename": "VideoViewingHistory"
                },
                "__typename": "VideoSelfEdge"
            },
            "title": str,
            "viewCount": int,
            "resourceRestriction": null,
            "contentTags": list,
            "__typename": "Video"
        },
        "__typename": "ViewedVideosEdge"
    }
    ```
    """
    url = "https://gql.twitch.tv/gql"

    payload = {
        "operationName": "FollowedStreamsContinueWatching",
        "variables": {
            "limit": 50
        },
        "extensions": {
            "persistedQuery": {
                "version": 1,
                "sha256Hash": "6b93ac09cd07819062ff8564b9c76e0c0b1d029c4f6474956968514685fdf918"
            }
        }
    }

    headers = {
        "Authorization": f"OAuth {gql_token}",
    }

    done = False

    while not done:
        r = requests.post(url, json=payload, headers=headers)
        done = len(r.json()["data"]["currentUser"]["viewedVideos"]["edges"]) > 0
        if not done:
            payload["variables"]["limit"] -= 5

    out = r.json()["data"]["currentUser"]["viewedVideos"]["edges"]
    if only_following:
        following = get_following(user_token, global_headers)
        out = [x for x in out if x["node"]["owner"]["login"] in following]
    return out


def update_latest_watched(gql_token: str, video_id: str, position: int = 0):
    if not video_id:
        return False
        
    url = "https://gql.twitch.tv/gql"

    payload = {
        "operationName": "updateUserViewedVideo",
        "variables": {
            "input": {
                "userID": "30408914",
                "position": position,
                "videoID": str(video_id),
                "videoType": "VOD"
            }
        },
        "extensions": {
            "persistedQuery": {
                "version": 1,
                "sha256Hash": "bb58b1bd08a4ca0c61f2b8d323381a5f4cd39d763da8698f680ef1dfaea89ca1"
            }
        }
    }

    headers = {
        "Authorization": f"OAuth {gql_token}",
    }

    r = requests.post(url, json=payload, headers=headers)

    return "errors" not in r.json()


def get_following(user_token, addl_headers):
    url = "https://api.twitch.tv/helix/channels/followed"
    params = {"user_id": "30408914"}
    headers = {"Authorization": f"Bearer {user_token}"}
    r = requests.get(url, params=params, headers=addl_headers | headers)
    return [x["broadcaster_login"] for x in r.json()["data"]]


def seconds_to_time(seconds):
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    return (
        (f"{h}h" if h else "") +
        (f"{m:02d}m" if m else "") +
        f"{s:02d}s"
    )

def time_to_seconds(time):
    r = re.match(r"(?:(\d+)h)?(?:(\d+)m)?(\d+)s", time)
    h, m, s = r.groups()
    t = timedelta(hours=int(h or 0), minutes=int(m or 0), seconds=int(s))
    return (t.days * 86400) + t.seconds

def relative_time(isodate):
    return humanize.naturaltime(
        datetime.utcnow() - datetime.fromisoformat(isodate).replace(tzinfo=None)
    )


def gen_video_data(latest_list, follow_list=None):
    MIN_POSITION = 60
    for i in latest_list:
        pos = i["history"]["position"]
        if pos <= MIN_POSITION:
            continue
        node = i["node"]
        user = node["owner"]
        game = node.get("game") or {}
        date = node["publishedAt"]
        vid_len = node["lengthSeconds"]
        yield {
            "user": user["displayName"],
            "following": user["login"].lower() in (follow_list or []),
            "title": node["title"],
            "video_id": node["id"],
            "game": game.get("displayName", "❓❓❓"),
            "url": f'https://twitch.tv/videos/{node["id"]}',
            "date": datetime.fromisoformat(date).strftime("%B %-d, %Y"),
            "epoch_date": datetime.fromisoformat(date).timestamp(),
            "relative_date": relative_time(date),
            "position": seconds_to_time(pos),
            "time": pos,
            "last_watched": datetime.fromisoformat(i["history"]["updatedAt"]).strftime("%B %-d, %Y"),
            "last_watched_relative": relative_time(i["history"]["updatedAt"]),
            "last_watched_epoch": datetime.fromisoformat(i["history"]["updatedAt"]).timestamp(),
            "remaining": seconds_to_time(vid_len - pos),
            "progress": int((pos / vid_len) * 100),
            "raw_json": json.dumps(i)
        }
