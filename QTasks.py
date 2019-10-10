from ShorJobDescriptor import ShorJobDescriptor
from threading import Thread, Event
from Q import Q, QNoBackendException
from QFleet import QFleet
from qiskit.aqua.aqua_error import AquaError
from qiskit.providers import JobStatus
from queue import Queue
from RWLock import RWLock
from time import time
import concurrent.futures


class QTasks(object):

    INTERNAL_INTERVAL = 5.0
    EXTERNAL_INTERVAL = 1.0
    CLEANUP_TIMEOUT = 60 * 15
    _instance = None

    def __init__(self, *args, **kwargs):
        if not QTasks._instance:
            QTasks._instance = _QTasks(*args, **kwargs)

    def __getattr__(self, item):
        return getattr(self._instance, item)


class _QTasks(object):

    def __init__(self, *args, **kwargs):
        self._abort = Event()
        self._job_queue = Queue()
        self._job_states = {}
        self._cancellation_events = {}
        self._locks = {}
        self._worker_thread = Thread(target=self._job_handler, daemon=True)

    def start(self):
        self._worker_thread.start()

    def join(self):
        self._worker_thread.join()

    def abort(self):
        self._abort.set()

    def request_job(self, job_descriptor: ShorJobDescriptor):
        if not self._may_request_job(job_descriptor):
            return "Job '{}' already exists in state '{}'" \
                   "".format(str(job_descriptor), self._state_to_response(self._get_state(job_descriptor)))
        self._submit_job(job_descriptor)
        return "Job '{}' submitted".format(str(job_descriptor))

    def request_cancel(self, job_descriptor: ShorJobDescriptor):
        state = self._get_state(job_descriptor)
        if not state:
            return "Job '{}' doesn't exist, nothing to cancel".format(str(job_descriptor))
        key = str(job_descriptor)
        self._locks[key].acquire_write()
        self._cancellation_events[key].set()
        self._locks[key].release_write()
        return "Cancelling job '{}'".format(key)

    def request_status(self, job_descriptor: ShorJobDescriptor):
        state = self._get_state(job_descriptor)
        if not state:
            return "No such job '{}' found".format(str(job_descriptor))
        return self._state_to_response(state)

    def _submit_job(self, job_descriptor: ShorJobDescriptor):
        k = str(job_descriptor)
        self._locks[k] = RWLock()
        self._locks[k].acquire_write()
        self._cancellation_events[str(job_descriptor)] = Event()
        self._job_states[str(job_descriptor)] = {
            'status': JobStatus.INITIALIZING,
            'place_in_queue': -1,
            'results': None,
            'error': None
        }
        self._job_queue.put(job_descriptor)
        self._locks[k].release_write()

    def _get_state(self, job_descriptor: ShorJobDescriptor):
        key = str(job_descriptor)
        state = None
        self._locks[key].acquire_read()
        if key in self._job_states:
            state = self._job_states[key]
        self._locks[key].release_read()
        return state

    def _state_to_response(self, state):
        status = state['status']
        if status == JobStatus.INITIALIZING:
            return "Job has been submitted for processing, waiting for available thread..."
        elif status == JobStatus.QUEUED:
            return "Job is in queue for server. Place in queue: {}".format(state['place_in_queue'])
        elif status == JobStatus.RUNNING:
            return "Job is running"
        elif status == JobStatus.VALIDATING:
            return "Job is being validated"
        elif status == JobStatus.DONE:
            return "Job completed! Results: {}".format(state['results'])
        elif status == JobStatus.ERROR:
            return "Job hit an error: {}".format(state['error'])
        elif status == JobStatus.CANCELLED:
            return "Job has been cancelled by user, no results available"

    def _may_request_job(self, job_descriptor: ShorJobDescriptor):
        return str(job_descriptor) not in self._locks

    def _update_status(self, job_descriptor: ShorJobDescriptor, status, place_in_queue=-1, results=None, error=None):
        if status == JobStatus.QUEUED and place_in_queue < 0:
            raise ValueError("Job '{}' updated to QUEUED state but no place in queue provided"
                             "".format(str(job_descriptor)))
        elif status == JobStatus.ERROR and not error:
            raise ValueError("Job '{}' updated to ERROR state but no error text provided"
                             "".format(str(job_descriptor)))
        key = str(job_descriptor)
        self._locks[key].acquire_write()
        self._job_states[str(job_descriptor)]['status'] = status
        if status == JobStatus.QUEUED:
            self._job_states[str(job_descriptor)]['place_in_queue'] = place_in_queue
        elif status == JobStatus.ERROR:
            self._job_states[str(job_descriptor)]['error'] = error
        elif status == JobStatus.DONE:
            self._job_states[str(job_descriptor)]['results'] = results
        self._locks[key].release_write()

    def _update_status_by_job(self, job_descriptor: ShorJobDescriptor, job, circ):
        status = job.status()
        if status == JobStatus.QUEUED:
            queue_position = job.queue_position()
            self._update_status(job_descriptor,
                                status=JobStatus.QUEUED,
                                place_in_queue=queue_position)
        elif status == JobStatus.ERROR:
            self._update_status(job_descriptor,
                                status=status,
                                error=status.value)
        elif status == JobStatus.DONE:
            self._update_status(job_descriptor,
                                status=JobStatus.DONE,
                                results=job.result().get_counts(circ),
                                error=status.value)
        elif status in [JobStatus.INITIALIZING,
                        JobStatus.RUNNING,
                        JobStatus.VALIDATING,
                        JobStatus.CANCELLED]:
            self._update_status(job_descriptor, status=status)
        else:
            self._update_status(job_descriptor,
                                status=JobStatus.ERROR,
                                error="ERROR: Unhandled status '{}'".format(status.name))

    def _start_shor_job(self, job_descriptor: ShorJobDescriptor):
        n = job_descriptor.n
        a = job_descriptor.a
        fleet = QFleet()
        if not fleet.has_viable_backend(n.bit_length(), allow_simulator=job_descriptor.allow_simulator):
            self._update_status(job_descriptor,
                                status=JobStatus.ERROR,
                                error="No backend viable for {} qubits".format(n.bit_length()))
        else:
            try:
                return Q.shors_period_finder(job_descriptor)
            except QNoBackendException as e:
                print("No backend found, updating response and waiting for cleanup...")
                self._update_status(job_descriptor,
                                    status=JobStatus.ERROR,
                                    error="Couldn't get backend for job: {}".format(e))
            except AquaError as e:
                print("Aqua error for N={}, a={}: {}".format(n, a, e))
                self._update_status(job_descriptor,
                                    status=JobStatus.ERROR,
                                    error="Aqua didn't like the input N={},a={}: {}".format(n, a, e))
        return None, None

    def _do_job(self, job_descriptor: ShorJobDescriptor):
        key = str(job_descriptor)
        self._locks[key].acquire_read()
        cancellation_event = self._cancellation_events[key]
        self._locks[key].release_read()
        job, circ = self._start_shor_job(job_descriptor)
        if not job:
            return "Failed to start Shor job"
        status = job.status()
        prev_status = None
        prev_queue_position = -1
        queue_position = -1
        while status not in [JobStatus.CANCELLED, JobStatus.DONE, JobStatus.ERROR]:
            self._update_status_by_job(job_descriptor, job, circ)
            if prev_status != status:
                prev_status = status
                print("Request {} status updated to {}".format(str(job_descriptor), status))
            if status == JobStatus.QUEUED and prev_queue_position != queue_position:
                prev_queue_position = queue_position
                print("Request {} queued ({})".format(str(job_descriptor), queue_position))
            cancellation_event.wait(timeout=QTasks.INTERNAL_INTERVAL)
            if cancellation_event.is_set():
                job.cancel()
                self._update_status(job_descriptor,
                                    status=JobStatus.CANCELLED,
                                    results="Cancelled before completion")
                return
            status = job.status()
        self._update_status_by_job(job_descriptor, job, circ)
        return "Done"

    def _job_handler(self):
        with concurrent.futures.ThreadPoolExecutor() as executor:
            futures = {}
            pending_cleanup = []
            while not self._abort.is_set():
                while not self._job_queue.empty():
                    job_descriptor = self._job_queue.get()
                    futures[executor.submit(self._do_job, job_descriptor)] = str(job_descriptor)
                if futures:
                    # Check for status of the futures which are currently working
                    done, not_done = concurrent.futures.wait(futures,
                                                             timeout=0.25,
                                                             return_when=concurrent.futures.FIRST_COMPLETED)
                    for future in done:
                        key = str(futures[future])
                        data = None
                        try:
                            data = future.result()
                        except Exception as e:
                            print("Job {} failed with data: {}\n\nException:\n{}".format(key, data, e))
                        pending_cleanup.append({
                            'job': key,
                            'cleanup_time': QTasks.CLEANUP_TIMEOUT + int(round(time()))
                        })
                        self._locks[key].acquire_write()
                        del futures[future]
                        del self._cancellation_events[key]
                        self._locks[key].release_write()
                while pending_cleanup and pending_cleanup[0]['cleanup_time'] <= int(round(time())):
                    key = pending_cleanup[0]['job']
                    self._locks[key].acquire_write()
                    del self._job_states[key]
                    self._locks[key].release_write()
                    del self._locks[key]
                    pending_cleanup.pop(0)
                self._abort.wait(timeout=QTasks.EXTERNAL_INTERVAL)
