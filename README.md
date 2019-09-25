# Personal Flask server

This repository is provided as documentation and source control for my personal Flask server project. This project is not intended to be run by anybody but myself, and I cannot provide support for it.

## Components

### <span>spotify.py</span>

Show a user's most played artists and tracks using the `v1/me/top` Spotify API.

### <span>slack.py</span>

Functions for Slack workspaces that abuse the pin feature by pinning amusing messages.

Can be set up to provide real-time storage of new pinned messages in a Slack workspace to a database.

Slash commands:
- `/pinhit` - Selects a random pinned message from the database and prints it to a Slack channel
- `/potd` - "Pinhit of the day" selects a random pin from the current day in prior years and prints it to a Slack channel, similar to the "memories" feature of other social media sites

### <span>twitch.py</span>

TwitchSurf: Twitch.tv stream randomizer. Displays a random Twitch stream every time the "Surf" button is pressed.

### <span>youtube.py</span>

Usage format: http://example.com/youtube/<channel_id>

## Setup

Create new venv in the project root and activate:

```shell
cd /path/to/flask_server
python3 -m venv venv
. venv/bin/activate
```

Install project and its dependencies:

```shell
pip3 install -e .
```

At this point the root project folder `flask_server` should have at least these components:

```
flask_server/
    billy_flask/
    instance/
        config.cfg.example
    setup.py
```

Copy `instance/config.cfg.example` to `instance/config.cfg` and set config options

Create media folders (symbolic links are fine with proper permissions)

  * `instance/slack_media`
  * `instance/twitter_media`

Create relative symbolic links from the `instance` folders to the `static` folder:

```shell
cd billy_flask/static/
ln -s ../../instance/twitter_media .
ln -s ../../instance/slack_media .
```

Create databases using schemas in the `schemas` folder. Pymysql doesn't have a good way of doing this, so do it manually for now:

```shell
cat billy_flask/schema/*.sql | mysql -u username -p
```

## Deployment

### Gunicorn3

Install gunicorn within the virtual environment:

```shell
. venv/bin/activate
pip3 install -U gunicorn
deactivate
```

Deploy: 

```shell
./venv/bin/gunicorn -b127.0.0.1:5000 'billy_flask:create_app()'
```

### systemd integration

As root:

```shell
touch /etc/systemd/system/flask_server.service
```

Edit the service file using this template:

```properties
[Unit]
Description=Flask server on port 5000 using gunicorn3
After=network.target

[Service]
WorkingDirectory=/full/path/to/flask_server
ExecStart=/full/path/to/flask_server/venv/bin/gunicorn -b127.0.0.1:5000 'billy_flask:create_app()'
KillMode=process
User=user
Group=group

[Install]
WantedBy=multi-user.target
```
- `User` and `Group` should have read/write permissions on all project files and folders

Reload systemd after editing service (as root):

```shell
systemctl daemon-reload
```

### Example nginx configuration

```nginx
server {
    listen 443 ssl;
    server_name         flask.example.com;
    ssl_certificate     /full/path/to/fullchain.pem;
    ssl_certificate_key /full/path/to/privkey.pem;

    access_log  /var/log/nginx/access.log;
    error_log   /var/log/nginx/error.log;

    location / {
        proxy_pass         http://127.0.0.1:5000;
        proxy_set_header   Host                     $host;
        proxy_set_header   X-Real-IP                $remote_addr;
        proxy_set_header   X-Forwarded-For          $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Host         $server_name;
        proxy_read_timeout 1200s;
    }
}
```
