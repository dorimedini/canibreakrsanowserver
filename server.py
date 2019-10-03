from flask import Flask, request
from multiprocessing import Process
from pathlib import Path
from time import sleep
from Q import Q
from qiskit.providers import JobStatus
import os
import asyncio
app = Flask(__name__)


def get_response_message(key):
    response_path = key_to_response_path(key)
    if not os.path.exists(response_path):
        return "No response!"
    with open(response_path, 'r') as file:
        return file.read()


def _update_response_file(key, text):
    with open(key_to_response_path(key), 'w') as file:
        file.truncate(0)
        file.write(text)


async def _worker_compute_circuit(key, query_interval=5.0):
    job, circ = Q.execute_circuit()
    status = job.status()
    prev_status = None
    while status not in [JobStatus.CANCELLED, JobStatus.DONE, JobStatus.ERROR]:
        if status == JobStatus.QUEUED:
            _update_response_file(key, "In queue ({})".format(job.queue_position()))
        elif status == JobStatus.INITIALIZING:
            _update_response_file(key, "Initializing job...")
        elif status == JobStatus.RUNNING:
            _update_response_file(key, "Running job...")
        elif status == JobStatus.VALIDATING:
            _update_response_file(key, "Validating job...")
        else:
            _update_response_file(key, "ERROR: Unhandled status '{}'".format(status.name))
        if prev_status != status:
            prev_status = status
            print("Request {} status updated to {}".format(key, status))
        sleep(query_interval)
        status = job.status()
    msg = "Job ended with message:\n{}".format(status.value)
    if status == JobStatus.DONE:
        msg += "\nResult histogram data:\n{}".format(job.result().get_counts(circ))
    _update_response_file(key, msg)


def handle_request(key):
    response_path = key_to_response_path(key)
    if not os.path.exists(response_path):
        asyncio.run(_worker_compute_circuit(key))


def key_to_request_path(key):
    return os.path.join("requests", "{}".format(key))


def key_to_response_path(key):
    return os.path.join("responses", "{}".format(key))


def get_request_key_list():
    request_dir = key_to_request_path("")
    return [f for f in os.listdir(request_dir) if os.path.isfile(os.path.join(request_dir, f))]


def worker_respond(interval=5):
    while True:
        request_keys = get_request_key_list()
        for key in request_keys:
            handle_request(key)
            os.remove(key_to_request_path(key))
        sleep(interval)


@app.route('/request')
def server_request():
    key = request.remote_addr
    request_path = key_to_request_path(key)
    if not os.path.exists(request_path):
        Path(request_path).touch()
        return "Created file request for {}".format(key)
    return "Already have request active for {}".format(key)


@app.route('/response')
def server_response():
    return get_response_message(request.remote_addr)


if __name__ == "__main__":
    p = Process(target=worker_respond, args=(5, ))
    p.start()
    app.run(host='0.0.0.0', use_reloader=False)
    p.join()
