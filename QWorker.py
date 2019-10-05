from multiprocessing import Process
from pathlib import Path
from Q import Q, QNoBackendException
from QFleet import QFleet
from qiskit.aqua.aqua_error import AquaError
from qiskit.providers import JobStatus
from time import sleep
import asyncio
import os
import re


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
            requests = QWorker.get_request_key_list()
            for key, n, a in requests:
                self._handle_request(key, n, a)
                os.remove(QWorker.key_to_request_path(key, n, a))
            cancellation_requests = self.get_cancellation_key_list()
            for key, n, a in cancellation_requests:
                self._handle_cancel(key, n, a)
            sleep(self._interval)

    @staticmethod
    def request(key, n, a):
        request_path = QWorker.key_to_request_path(key, n, a)
        if not os.path.exists(request_path):
            Path(request_path).touch()
            return "Created file request for {}, number {}, a={}".format(key, n, a)
        return "Already have request active for {}, number {}, a={}".format(key, n, a)

    @staticmethod
    def cancel(key, n, a):
        if not QWorker._does_job_exist(key, n, a):
            return "No pending job for {} (num {}, a={})".format(key, n, a)
        QWorker._handle_cancel(key, n, a)
        return "Cancelling job {} (num {}, a={})".format(key, n, a)

    @staticmethod
    def get_response_message(key, n, a):
        response_path = QWorker.key_to_response_path(key, n, a)
        if not os.path.exists(response_path):
            return "No response!"
        with open(response_path, 'r') as file:
            return file.read()

    @staticmethod
    def _update_response_file(key, n, a, text):
        with open(QWorker.key_to_response_path(key, n, a), 'w') as file:
            file.truncate(0)
            file.write(text)

    @staticmethod
    def _delete_response_file(key, n, a):
        path_to_response = QWorker.key_to_response_path(key, n, a)
        if os.path.exists(path_to_response):
            os.remove(path_to_response)

    @staticmethod
    def _delete_request_file(key, n, a):
        path_to_request = QWorker.key_to_request_path(key, n, a)
        if os.path.exists(path_to_request):
            os.remove(path_to_request)

    @staticmethod
    def _delete_cancellation_file(key, n, a):
        path_to_cancellation = QWorker.key_to_cancellation_path(key, n, a)
        if os.path.exists(path_to_cancellation):
            os.remove(path_to_cancellation)

    @staticmethod
    async def _worker_compute_circuit(key, n, a, query_interval=5.0):
        def cleanup_after_timeout():
            try:
                for _ in range(QWorker.RESPONSE_FILE_LIFESPAN // int(query_interval)):
                    sleep(int(query_interval))
                    if QWorker._should_cancel(key, n, a):
                        print("Not waiting for cleanup {} (n={}, a={}), cancelling...".format(key, n, a))
                        break
            except KeyboardInterrupt as e:
                print("Stopped waiting to cleanup {} due to KeyboardInterrupt, cleaning up and propagating...".format(key))
                QWorker._cleanup_files(key, n, a)
                raise e
            print("Cleaning up files for {} (num {}, a={})".format(key, n, a))
            QWorker._cleanup_files(key, n, a)

        job_cancelled = False
        fleet = QFleet()
        if not fleet.has_viable_backend(n.bit_length()):
            QWorker._update_response_file(key, n, a, "No backend viable for {} qubits".format(n.bit_length()))
        else:
            try:
                job, circ = Q.shors_period_finder(n, a)
            except QNoBackendException as e:
                QWorker._update_response_file(key, n, a, "Couldn't get backend for job: {}".format(e))
                cleanup_after_timeout()
                return
            except AquaError as e:
                QWorker._update_response_file(key, n, a, "Aqua didn't like the input N={},a={}: {}".format(n, a, e))
                cleanup_after_timeout()
                return
            status = job.status()
            prev_status = None
            prev_queue_position = -1
            queue_position = -1
            while status not in [JobStatus.CANCELLED, JobStatus.DONE, JobStatus.ERROR]:
                if QWorker._should_cancel(key, n, a):
                    job_cancelled = True
                    break
                if status == JobStatus.QUEUED:
                    queue_position = job.queue_position()
                    QWorker._update_response_file(key, n, a, "In queue ({})".format(queue_position))
                elif status == JobStatus.INITIALIZING:
                    QWorker._update_response_file(key, n, a, "Initializing job...")
                elif status == JobStatus.RUNNING:
                    QWorker._update_response_file(key, n, a, "Running job...")
                elif status == JobStatus.VALIDATING:
                    QWorker._update_response_file(key, n, a, "Validating job...")
                else:
                    QWorker._update_response_file(key, n, a, "ERROR: Unhandled status '{}'".format(status.name))
                if prev_status != status:
                    prev_status = status
                    print("Request {} (num {}, a={}) status updated to {}".format(key, n, a, status))
                if status == JobStatus.QUEUED and prev_queue_position != queue_position:
                    prev_queue_position = queue_position
                    print("Request {} (num {}, a={}) queued ({})".format(key, n, a, queue_position))
                sleep(query_interval)
                status = job.status()
            if job_cancelled:
                print("Job {} (num {}) cancelled".format(key, n))
                QWorker._update_response_file(key, n, a, "Job {} (num {}, a={}) cancelled".format(key, n, a))
            else:
                msg = "Job ended with message:\n{}".format(status.value)
                if status == JobStatus.DONE:
                    msg += "\nResult histogram data:\n{}".format(job.result().get_counts(circ))
                print("Job {} (num {}, a={}) final message: {}".format(key, n, a, msg))
                QWorker._update_response_file(key, n, a, msg)
        print("Job {} (num {}, a={}) done, cleanup in {} seconds".format(key, n, a, QWorker.RESPONSE_FILE_LIFESPAN))
        cleanup_after_timeout()

    def _handle_request(self, key, n, a):
        response_path = QWorker.key_to_response_path(key, n, a)
        if not os.path.exists(response_path):
            asyncio.run(QWorker._worker_compute_circuit(key, n, a, query_interval=self._interval))

    @staticmethod
    def _handle_cancel(key, n, a):
        cancel_path = QWorker.key_to_cancellation_path(key, n, a)
        if not os.path.exists(cancel_path) and QWorker._does_job_exist(key, n, a):
            print("Cancelling job {}, number {}, a={}".format(key, n, a))
            Path(cancel_path).touch()

    @staticmethod
    def _cleanup_files(key, n, a):
        QWorker._delete_response_file(key, n, a)
        QWorker._delete_request_file(key, n, a)
        QWorker._delete_cancellation_file(key, n, a)

    @staticmethod
    def _should_cancel(key, n, a):
        return os.path.exists(QWorker.key_to_cancellation_path(key, n, a))

    @staticmethod
    def _does_job_exist(key, n, a):
        return os.path.exists(QWorker.key_to_request_path(key, n, a))

    @staticmethod
    def _construct_filename(key, n, a):
        return "{}_{}_{}".format(key, n, a)

    @staticmethod
    def request_dir():
        return "requests"

    @staticmethod
    def key_to_request_path(key, n, a):
        return os.path.join(QWorker.request_dir(), QWorker._construct_filename(key, n, a))

    @staticmethod
    def response_dir():
        return "responses"

    @staticmethod
    def key_to_response_path(key, n, a):
        return os.path.join(QWorker.response_dir(), QWorker._construct_filename(key, n, a))

    @staticmethod
    def cancellation_dir():
        return "cancellations"

    @staticmethod
    def key_to_cancellation_path(key, n, a):
        return os.path.join(QWorker.cancellation_dir(), QWorker._construct_filename(key, n, a))

    @staticmethod
    def is_valid_key_file(basedir, filename):
        return os.path.isfile(os.path.join(basedir, filename)) and re.search("^.+_[0-9]+_[0-9]+", filename)

    @staticmethod
    def split_key_filename(name):
        return name.split("_")[0], int(name.split("_")[1]), int(name.split("_")[2])

    @staticmethod
    def get_request_key_list():
        request_dir = QWorker.request_dir()
        names = [f for f in os.listdir(request_dir) if QWorker.is_valid_key_file(request_dir, f)]
        return [QWorker.split_key_filename(name) for name in names]

    @staticmethod
    def get_cancellation_key_list():
        cancellation_dir = QWorker.cancellation_dir()
        names = [f for f in os.listdir(cancellation_dir) if QWorker.is_valid_key_file(cancellation_dir, f)]
        return [QWorker.split_key_filename(name) for name in names]
