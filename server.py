from argparse import ArgumentParser
from flask import Flask, request
from QLogin import IBMQ_TOKEN_FILENAME
from QTasks import QTasks
from ShorJobDescriptor import ShorJobDescriptor
from threading import Thread
app = Flask(__name__)


@app.route('/new_job/<n>/<a>')
def new_job(n, a):
    tasks = QTasks()
    return tasks.request_job(ShorJobDescriptor(request.remote_addr, n, a))


@app.route('/status/<n>/<a>')
def status(n, a):
    tasks = QTasks()
    return tasks.request_status(ShorJobDescriptor(request.remote_addr, n, a))


@app.route('/cancel/<n>/<a>')
def cancel(n, a):
    tasks = QTasks()
    return tasks.request_cancel(ShorJobDescriptor(request.remote_addr, n, a))


@app.route('/get_backends')
def get_backends():
    tasks = QTasks()
    return tasks.request_backend_list()


def dump_api_token(token):
    with open(IBMQ_TOKEN_FILENAME, 'w') as file:
        file.write(token)


if __name__ == "__main__":
    parser = ArgumentParser(description='"Can I break RSA now?" server')
    parser.add_argument('-p', '--port', type=str)
    parser.add_argument('-t', '--api-token', type=str)
    parser.add_argument('-H', '--host', type=str, default='0.0.0.0')
    args = parser.parse_args()

    if args.api_token:
        dump_api_token(args.api_token)

    host = "{}:{}".format(args.host, args.port)
    app_thread = Thread(target=app.run,
                        kwargs={'host': host, 'use_reloader': False},
                        daemon=True)
    app_thread.start()

    tasks = QTasks()
    tasks.start()
    tasks.join()
