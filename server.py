from flask import Flask, request
from QWorker import QWorker
app = Flask(__name__)


@app.route('/request/<n>/<a>')
def server_request(n, a):
    return QWorker.request(request.remote_addr, n, a)


@app.route('/response/<n>/<a>')
def server_response(n, a):
    return QWorker.get_response_message(request.remote_addr, n, a)


@app.route('/cancel/<n>/<a>')
def server_cancel(n, a):
    return QWorker.cancel(request.remote_addr, n, a)


if __name__ == "__main__":
    worker = QWorker(interval=5)
    worker.start()
    app.run(host='0.0.0.0', use_reloader=False)
    worker.join()
