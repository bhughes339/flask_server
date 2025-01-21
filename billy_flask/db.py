import pymysql
import click
from flask import current_app, g
from flask.cli import with_appcontext

class Connection(pymysql.connections.Connection):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
    
    def dict_cursor(self):
        return pymysql.cursors.DictCursor(self)


def mysql_warning():
    return pymysql.Warning


def get_db(database=None):
    with current_app.app_context():
        if 'db' not in g:
            conf = current_app.config['MYSQL']
            g.db = Connection(host=conf['host'], user=conf['user'],
                            password=conf['passwd'], db=database, charset='utf8mb4')
        else:
            if g.db.db.decode() != database:
                g.db.select_db(database)
        
        return g.db

# TODO: init-db code
# @click.command('init-db')
# @with_appcontext
# def init_db():
#     """Create tables."""
#     db = get_db()

#     click.echo('Initialized the database.')
