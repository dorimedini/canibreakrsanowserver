from multiprocessing import Process
from pathlib import Path
from Q import Q
from qiskit.providers import JobStatus
from time import sleep
import asyncio
import os


class QWorker(object):

    RESPONSE_FILE_LIFESPAN = 60 * 60

    def __init__(self, interval=5.0):
        self._interval = interval
        self._p = Process(target=self._main)

    def start(self):
        return self._p.start()

    def join(self, *args, **kwargs):
        return self._p.join(*args, **kwargs)

    def _main(self):
        while True:
            request_keys = QWorker.get_request_key_list()
            for key in request_keys:
                self._handle_request(key)
                os.remove(QWorker.key_to_request_path(key))
            sleep(self._interval)

    @staticmethod
    def request(key):
        request_path = QWorker.key_to_request_path(key)
        if not os.path.exists(request_path):
            Path(request_path).touch()
            return "Created file request for {}".format(key)
        return "Already have request active for {}".format(key)

    @staticmethod
    def get_response_message(key):
        response_path = QWorker.key_to_response_path(key)
        if not os.path.exists(response_path):
            return "No response!"
        with open(response_path, 'r') as file:
            return file.read()

    @staticmethod
    def _update_response_file(key, text):
        with open(QWorker.key_to_response_path(key), 'w') as file:
            file.truncate(0)
            file.write(text)

    @staticmethod
    def _delete_response_file(key):
        path_to_response = QWorker.key_to_response_path(key)
        if os.path.exists(path_to_response):
            os.remove(path_to_response)

    @staticmethod
    async def _worker_compute_circuit(key, query_interval=5.0):
        job, circ = Q.execute_circuit()
        status = job.status()
        prev_status = None
        prev_queue_position = -1
        queue_position = -1
        while status not in [JobStatus.CANCELLED, JobStatus.DONE, JobStatus.ERROR]:
            if status == JobStatus.QUEUED:
                queue_position = job.queue_position()
                QWorker._update_response_file(key, "In queue ({})".format(queue_position))
            elif status == JobStatus.INITIALIZING:
                QWorker._update_response_file(key, "Initializing job...")
            elif status == JobStatus.RUNNING:
                QWorker._update_response_file(key, "Running job...")
            elif status == JobStatus.VALIDATING:
                QWorker._update_response_file(key, "Validating job...")
            else:
                QWorker._update_response_file(key, "ERROR: Unhandled status '{}'".format(status.name))
            if prev_status != status:
                prev_status = status
                print("Request {} status updated to {}".format(key, status))
            if status == JobStatus.QUEUED and prev_queue_position != queue_position:
                prev_queue_position = queue_position
                print("Request {} queued ({})".format(key, queue_position))
            sleep(query_interval)
            status = job.status()
        msg = "Job ended with message:\n{}".format(status.value)
        if status == JobStatus.DONE:
            msg += "\nResult histogram data:\n{}".format(job.result().get_counts(circ))
        self._update_response_file(key, msg)
        # Cleanup
        sleep(QWorker.RESPONSE_FILE_LIFESPAN)
        self._delete_response_file(key)

    def _handle_request(self, key):
        response_path = QWorker.key_to_response_path(key)
        if not os.path.exists(response_path):
            asyncio.run(QWorker._worker_compute_circuit(key, query_interval=self._interval))

    @staticmethod
    def request_dir():
        return "requests"

    @staticmethod
    def key_to_request_path(key):
        return os.path.join(QWorker.request_dir(), str(key))

    @staticmethod
    def response_dir():
        return "responses"

    @staticmethod
    def key_to_response_path(key):
        return os.path.join(QWorker.response_dir(), str(key))

    @staticmethod
    def get_request_key_list():
        request_dir = QWorker.request_dir()
        return [f for f in os.listdir(request_dir) if os.path.isfile(os.path.join(request_dir, f))]
