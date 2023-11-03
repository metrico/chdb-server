import os
import tempfile

import chdb
from chdb import session as chs
from flask import Flask, request
from flask_httpauth import HTTPBasicAuth

app = Flask(__name__, static_folder="public", static_url_path="")
auth = HTTPBasicAuth()
driver = chdb

# session support: basic username + password as unique datapath
@auth.verify_password
def verify(username, password):
    if not (username and password):
        print('stateless session')
        globals()["driver"] = chdb
    else:
        path = globals()["path"] + "/" + str(hash(username + password))
        print('stateful session ' + path)
        globals()["driver"] = chs.Session(path)
    return True

# run chdb.query(query, format), get result from return and collect stderr
def chdb_query_with_errmsg(query, format):
    # Redirect stdout and stderr to the buffers
    try:
        new_stderr = tempfile.TemporaryFile()
        old_stderr_fd = os.dup(2)
        os.dup2(new_stderr.fileno(), 2)
        # Call the function
        output = driver.query(query, format).bytes()

        new_stderr.flush()
        new_stderr.seek(0)
        errmsg = new_stderr.read()

        # cleanup and recover
        new_stderr.close()
        os.dup2(old_stderr_fd, 2)
    except Exception as e:
        # An error occurred, print it to stderr
        print(f"An error occurred: {e}")
    return output, errmsg

@app.route('/', methods=["GET"])
@auth.login_required
def clickhouse():
    query = request.args.get('query', default="", type=str)
    format = request.args.get('default_format', default="TSV", type=str)
    database = request.args.get('database', default="", type=str)
    if not query:
        return app.send_static_file('play.html')

    if database:
        query = f"USE {database}; {query}".encode()

    result, errmsg = chdb_query_with_errmsg(query, format)
    if len(errmsg) == 0:
        return result, 200
    return errmsg, 400

@app.route('/', methods=["POST"])
@auth.login_required
def play():
    query = request.args.get('query', default=None, type=str)
    body = request.get_data() or None
    format = request.args.get('default_format', default="TSV", type=str)
    database = request.args.get('database', default="", type=str)

    if query is None:
        query = b""
    else:
        query = bytes(query)
    if body is not None:
        query = query + body

    if not query:
        return "Error: no query parameter provided", 400

    if database:
        database = f"USE {database}; ".encode()
        query = database + query

    result, errmsg = chdb_query_with_errmsg(query, format)
    if len(errmsg) == 0:
        return result, 200
    return errmsg, 400


@app.route('/play', methods=["GET"])
def handle_play():
    return app.send_static_file('play.html')

@app.route('/ping', methods=["GET"])
def handle_ping():
    return "Ok", 200

@app.errorhandler(404)
def handle_404(e):
    return app.send_static_file('play.html')

host = os.getenv('HOST', '0.0.0.0')
port = os.getenv('PORT', 8123)
path = os.getenv('DATA', '.chdb_data')
app.run(host=host, port=port)
