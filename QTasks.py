from QFleet import QFleet
from qiskit import execute
from qiskit.aqua.algorithms.single_sample.shor.shor import Shor
from qiskit.aqua.aqua_error import AquaError
from QStatus import QStatus, Q_FINAL_STATES, from_job_status
from queue import Queue
from RWLock import RWLock
from ShorJobDescriptor import ShorJobDescriptor
from threading import Thread, Event, Lock
from time import time
import concurrent.futures


def globally_locked(f):
    def run_only_if_locked(self, *args, **kwargs):
        if not self._global_lock.locked():
            print("Not running function {}, global lock is not locked!".format(f.__name__))
            return
        return f(self, *args, **kwargs)
    return run_only_if_locked


class QNoBackendException(Exception):
    pass


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
        self._global_lock = Lock()
        self._worker_thread = Thread(target=self._job_handler, daemon=True)

    def start(self):
        self._worker_thread.start()

    def join(self):
        self._worker_thread.join()

    def abort(self):
        self._abort.set()

    def request_job(self, job_descriptor: ShorJobDescriptor):
        self._global_lock.acquire()
        if str(job_descriptor) in self._locks:
            self._global_lock.release()
            return "Job '{}' already exists in state '{}'" \
                   "".format(str(job_descriptor), self._state_to_response(self._get_state(job_descriptor)))
        self._submit_job(job_descriptor)
        self._global_lock.release()
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

    @globally_locked
    def _submit_job(self, job_descriptor: ShorJobDescriptor):
        k = str(job_descriptor)
        self._locks[k] = RWLock()
        self._locks[k].acquire_write()
        self._cancellation_events[str(job_descriptor)] = Event()
        self._job_states[str(job_descriptor)] = {
            'status': QStatus.REQUESTED,
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
        if status == QStatus.REQUESTED:
            return "Job request has been received, waiting for thread to start"
        if status == QStatus.INITIALIZING:
            return "Job is initializing on backend..."
        elif status == QStatus.QUEUED:
            return "Job is in queue for server. Place in queue: {}".format(state['place_in_queue'])
        elif status == QStatus.RUNNING:
            return "Job is running"
        elif status == QStatus.VALIDATING:
            return "Job is being validated"
        elif status == QStatus.DONE:
            return "Job completed! Results: {}".format(state['results'])
        elif status == QStatus.ERROR:
            return "Job hit an error: {}".format(state['error'])
        elif status == QStatus.CANCELLED:
            return "Job has been cancelled by user, no results available"
        elif status == QStatus.CONSTRUCTING_CIRCUIT:
            return "Job's circuit is under construction"
        elif status == QStatus.FINDING_BACKEND:
            return "Searching for capable backend for job"
        elif status == QStatus.REQUEST_EXECUTE:
            return "Constructing quantum circuit (could take a minute)"
        return "UNKNOWN STATUS"

    def _update_status(self, job_descriptor: ShorJobDescriptor, status, place_in_queue=-1, results=None, error=None):
        if status == QStatus.QUEUED and place_in_queue < 0:
            raise ValueError("Job '{}' updated to QUEUED state but no place in queue provided"
                             "".format(str(job_descriptor)))
        elif status == QStatus.ERROR and not error:
            raise ValueError("Job '{}' updated to ERROR state but no error text provided"
                             "".format(str(job_descriptor)))
        key = str(job_descriptor)
        print("In update_status for job {}. status: {}, queue: {}, error: {}, results: {}"
              "".format(key, status, place_in_queue, error, results))
        self._locks[key].acquire_write()
        self._job_states[str(job_descriptor)]['status'] = status
        if status == QStatus.QUEUED:
            self._job_states[str(job_descriptor)]['place_in_queue'] = place_in_queue
        elif status == QStatus.ERROR:
            self._job_states[str(job_descriptor)]['error'] = error
        elif status == QStatus.DONE:
            self._job_states[str(job_descriptor)]['results'] = results
        self._locks[key].release_write()

    def _update_status_by_job(self, job_descriptor: ShorJobDescriptor, job, circ):
        status = from_job_status(job.status())
        if status == QStatus.QUEUED:
            queue_position = job.queue_position()
            self._update_status(job_descriptor,
                                status=QStatus.QUEUED,
                                place_in_queue=queue_position)
        elif status == QStatus.ERROR:
            self._update_status(job_descriptor,
                                status=status,
                                error=status.value)
        elif status == QStatus.DONE:
            self._update_status(job_descriptor,
                                status=QStatus.DONE,
                                results=job.result().get_counts(circ),
                                error=status.value)
        elif status in [QStatus.REQUESTED,
                        QStatus.INITIALIZING,
                        QStatus.RUNNING,
                        QStatus.VALIDATING,
                        QStatus.CANCELLED,
                        QStatus.CONSTRUCTING_CIRCUIT,
                        QStatus.FINDING_BACKEND,
                        QStatus.REQUEST_EXECUTE]:
            self._update_status(job_descriptor, status=status)
        else:
            self._update_status(job_descriptor,
                                status=QStatus.ERROR,
                                error="ERROR: Unhandled status '{}'".format(status.name))

    def _start_shor_job(self, job_descriptor: ShorJobDescriptor):
        n = job_descriptor.n
        a = job_descriptor.a
        fleet = QFleet()
        if not fleet.has_viable_backend(n.bit_length(), allow_simulator=job_descriptor.allow_simulator):
            self._update_status(job_descriptor,
                                status=QStatus.ERROR,
                                error="No backend viable for {} qubits".format(n.bit_length()))
        else:
            try:
                return self._shors_period_finder(job_descriptor, fleet)
            except QNoBackendException as e:
                print("No backend found, updating response and waiting for cleanup...")
                self._update_status(job_descriptor,
                                    status=QStatus.ERROR,
                                    error="Couldn't get backend for job: {}".format(e))
            except AquaError as e:
                print("Aqua error for N={}, a={}: {}".format(n, a, e))
                self._update_status(job_descriptor,
                                    status=QStatus.ERROR,
                                    error="Aqua didn't like the input N={},a={}: {}".format(n, a, e))
        return None, None

    def _do_job(self, job_descriptor: ShorJobDescriptor):
        key = str(job_descriptor)
        print("In do_job for job {}".format(key))
        self._locks[key].acquire_read()
        cancellation_event = self._cancellation_events[key]
        self._locks[key].release_read()
        job, circ = self._start_shor_job(job_descriptor)
        if not job:
            print("Job {} failed to start (backend error)".format(key))
            return "Failed"
        status = job.status()
        while status not in Q_FINAL_STATES:
            print("do_job iteration for {}, status is {}".format(key, status))
            self._update_status_by_job(job_descriptor, job, circ)
            cancellation_event.wait(timeout=QTasks.INTERNAL_INTERVAL)
            if cancellation_event.is_set():
                job.cancel()
                self._update_status(job_descriptor,
                                    status=QStatus.CANCELLED,
                                    results="Cancelled before completion")
                return "Cancelled"
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
                        print("{} threads done, processing results...".format(len(done)))
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
                cleaned = 0
                while pending_cleanup and pending_cleanup[0]['cleanup_time'] <= int(round(time())):
                    key = pending_cleanup[0]['job']
                    self._locks[key].acquire_write()
                    del self._job_states[key]
                    self._locks[key].release_write()
                    self._global_lock.acquire()
                    del self._locks[key]
                    self._global_lock.release()
                    pending_cleanup.pop(0)
                    cleaned += 1
                if cleaned:
                    print("Cleaned up {} old results from memory".format(cleaned))
                self._abort.wait(timeout=QTasks.EXTERNAL_INTERVAL)

    def _shors_period_finder(self, job_descriptor: ShorJobDescriptor, fleet: QFleet, shots=None):
        key = str(job_descriptor)
        print("Constructing circuit for Shor's algorithm on {}".format(key))
        self._update_status(job_descriptor,
                            status=QStatus.CONSTRUCTING_CIRCUIT)
        n = job_descriptor.n
        a = job_descriptor.a
        shor = Shor(N=n, a=a)
        circ = shor.construct_circuit(measurement=True)
        print("Constructed circuit for {}, finding backend...".format(key))
        self._update_status(job_descriptor,
                            status=QStatus.FINDING_BACKEND)
        qcomp = fleet.get_best_backend(circ.n_qubits, job_descriptor.allow_simulator)
        if not qcomp:
            raise QNoBackendException("No viable backend with {} qubits for job {}".format(circ.n_qubits, key))
        print("Got backend '{}' for job {}. Executing...".format(qcomp.name(), key))
        self._update_status(job_descriptor,
                            status=QStatus.REQUEST_EXECUTE)
        kwargs = {'backend': qcomp}
        if shots:
            kwargs['shots'] = shots
        job = execute(circ, **kwargs)
        print("Started job {}, status is {}".format(key, job.status()))
        self._update_status_by_job(job_descriptor, job, circ)
        return job, circ
