from flask import Flask, request
from QWorker import QWorker
app = Flask(__name__)


@app.route('/request/<n>')
def server_request(n):
    return QWorker.request(request.remote_addr, n)


@app.route('/response/<n>')
def server_response(n):
    return QWorker.get_response_message(request.remote_addr, n)


@app.route('/cancel/<n>')
def server_cancel(n):
    return QWorker.cancel(request.remote_addr, n)


if __name__ == "__main__":
    worker = QWorker(interval=5)
    worker.start()
    app.run(host='0.0.0.0', use_reloader=False)
    worker.join()
