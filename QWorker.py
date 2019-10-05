from multiprocessing import Process
from pathlib import Path
from Q import Q
from QFleet import QFleet
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
            for key, n in requests:
                self._handle_request(key, n)
                os.remove(QWorker.key_to_request_path(key, n))
            cancellation_requests = self.get_cancellation_key_list()
            for key, n in cancellation_requests:
                self._handle_cancel(key, n)
            sleep(self._interval)

    @staticmethod
    def request(key, n):
        request_path = QWorker.key_to_request_path(key, n)
        if not os.path.exists(request_path):
            Path(request_path).touch()
            return "Created file request for {}, number {}".format(key, n)
        return "Already have request active for {}, number {}".format(key, n)

    @staticmethod
    def cancel(key, n):
        if not QWorker._does_job_exist(key, n):
            return "No pending job for {} (num {})".format(key, n)
        QWorker._handle_cancel(key, n)
        return "Cancelling job {} (num {})".format(key, n)

    @staticmethod
    def get_response_message(key, n):
        response_path = QWorker.key_to_response_path(key, n)
        if not os.path.exists(response_path):
            return "No response!"
        with open(response_path, 'r') as file:
            return file.read()

    @staticmethod
    def _update_response_file(key, n, text):
        with open(QWorker.key_to_response_path(key, n), 'w') as file:
            file.truncate(0)
            file.write(text)

    @staticmethod
    def _delete_response_file(key, n):
        path_to_response = QWorker.key_to_response_path(key, n)
        if os.path.exists(path_to_response):
            os.remove(path_to_response)

    @staticmethod
    def _delete_request_file(key, n):
        path_to_request = QWorker.key_to_request_path(key, n)
        if os.path.exists(path_to_request):
            os.remove(path_to_request)

    @staticmethod
    def _delete_cancellation_file(key, n):
        path_to_cancellation = QWorker.key_to_cancellation_path(key, n)
        if os.path.exists(path_to_cancellation):
            os.remove(path_to_cancellation)

    @staticmethod
    async def _worker_compute_circuit(key, n, query_interval=5.0):
        job_cancelled = False
        fleet = QFleet()
        if not fleet.has_viable_backend(n.bit_length()):
            QWorker._update_response_file(key, n, "No backend viable for {} qubits".format(n.bit_length()))
        else:
            job, circ = Q.execute_circuit(n)
            status = job.status()
            prev_status = None
            prev_queue_position = -1
            queue_position = -1
            while status not in [JobStatus.CANCELLED, JobStatus.DONE, JobStatus.ERROR]:
                if QWorker._should_cancel(key, n):
                    job_cancelled = True
                    break
                if status == JobStatus.QUEUED:
                    queue_position = job.queue_position()
                    QWorker._update_response_file(key, n, "In queue ({})".format(queue_position))
                elif status == JobStatus.INITIALIZING:
                    QWorker._update_response_file(key, n, "Initializing job...")
                elif status == JobStatus.RUNNING:
                    QWorker._update_response_file(key, n, "Running job...")
                elif status == JobStatus.VALIDATING:
                    QWorker._update_response_file(key, n, "Validating job...")
                else:
                    QWorker._update_response_file(key, n, "ERROR: Unhandled status '{}'".format(status.name))
                if prev_status != status:
                    prev_status = status
                    print("Request {} (num {}) status updated to {}".format(key, n, status))
                if status == JobStatus.QUEUED and prev_queue_position != queue_position:
                    prev_queue_position = queue_position
                    print("Request {} (num {}) queued ({})".format(key, n, queue_position))
                sleep(query_interval)
                status = job.status()
            if job_cancelled:
                print("Job {} (num {}) cancelled".format(key, n))
                QWorker._update_response_file(key, n, "Job {} (num {}) cancelled".format(key, n))
            else:
                msg = "Job ended with message:\n{}".format(status.value)
                if status == JobStatus.DONE:
                    msg += "\nResult histogram data:\n{}".format(job.result().get_counts(circ))
                print("Job {} (num {}) final message: {}".format(key, n, msg))
                QWorker._update_response_file(key, n, msg)
        print("Job {} (num {}) done, cleanup in {} seconds".format(key, n, QWorker.RESPONSE_FILE_LIFESPAN))
        # Cleanup
        try:
            for _ in range(QWorker.RESPONSE_FILE_LIFESPAN // int(query_interval)):
                sleep(int(query_interval))
                if QWorker._should_cancel(key, n):
                    print("Not waiting for cleanup {} (n={}), cancelling...".format(key, n))
                    break
        except KeyboardInterrupt as e:
            print("Stopped waiting to cleanup {} due to KeyboardInterrupt, cleaning up and propagating...".format(key))
            QWorker._cleanup_files(key, n)
            raise e
        print("Cleaning up files for {} (num {})".format(key, n))
        QWorker._cleanup_files(key, n)

    def _handle_request(self, key, n):
        response_path = QWorker.key_to_response_path(key, n)
        if not os.path.exists(response_path):
            asyncio.run(QWorker._worker_compute_circuit(key, n, query_interval=self._interval))

    @staticmethod
    def _handle_cancel(key, n):
        cancel_path = QWorker.key_to_cancellation_path(key, n)
        if not os.path.exists(cancel_path) and QWorker._does_job_exist(key, n):
            print("Cancelling job {}, number {}".format(key, n))
            Path(cancel_path).touch()

    @staticmethod
    def _cleanup_files(key, n):
        QWorker._delete_response_file(key, n)
        QWorker._delete_request_file(key, n)
        QWorker._delete_cancellation_file(key, n)

    @staticmethod
    def _should_cancel(key, n):
        return os.path.exists(QWorker.key_to_cancellation_path(key, n))

    @staticmethod
    def _does_job_exist(key, n):
        return os.path.exists(QWorker.key_to_request_path(key, n))

    @staticmethod
    def request_dir():
        return "requests"

    @staticmethod
    def key_to_request_path(key, n):
        return os.path.join(QWorker.request_dir(), "{}_{}".format(key, n))

    @staticmethod
    def response_dir():
        return "responses"

    @staticmethod
    def key_to_response_path(key, n):
        return os.path.join(QWorker.response_dir(), "{}_{}".format(key, n))

    @staticmethod
    def cancellation_dir():
        return "cancellations"

    @staticmethod
    def key_to_cancellation_path(key, n):
        return os.path.join(QWorker.cancellation_dir(), "{}_{}".format(key, n))

    @staticmethod
    def is_valid_key_file(basedir, filename):
        return os.path.isfile(os.path.join(basedir, filename)) and re.search("^.+_[0-9]+", filename)

    @staticmethod
    def get_request_key_list():
        request_dir = QWorker.request_dir()
        names = [f for f in os.listdir(request_dir) if QWorker.is_valid_key_file(request_dir, f)]
        return [(name.split("_")[0], int(name.split("_")[1])) for name in names]

    @staticmethod
    def get_cancellation_key_list():
        cancellation_dir = QWorker.cancellation_dir()
        names = [f for f in os.listdir(cancellation_dir) if QWorker.is_valid_key_file(cancellation_dir, f)]
        return [(name.split("_")[0], int(name.split("_")[1])) for name in names]
