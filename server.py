from flask import Flask, request
from QWorker import QWorker
app = Flask(__name__)


@app.route('/request')
def server_request():
    return QWorker.request(request.remote_addr)


@app.route('/response')
def server_response():
    return QWorker.get_response_message(request.remote_addr)


@app.route('/cancel')
def server_cancel():
    return QWorker.cancel(request.remote_addr)


if __name__ == "__main__":
    worker = QWorker(interval=5)
    worker.start()
    app.run(host='0.0.0.0', use_reloader=False)
    worker.join()
