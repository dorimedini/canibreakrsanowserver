from flask import Flask, request
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


if __name__ == "__main__":
    app_thread = Thread(target=app.run,
                        kwargs={'host': '0.0.0.0', 'use_reloader': False},
                        daemon=True)
    app_thread.start()
    tasks = QTasks()
    tasks.start()
    tasks.join()
