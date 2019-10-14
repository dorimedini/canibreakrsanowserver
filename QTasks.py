from QFleet import QFleet
from qiskit import execute
from qiskit.aqua.algorithms.single_sample.shor.shor import Shor
from qiskit.aqua.aqua_error import AquaError
from QResponse import QResponse
from QStatus import QStatus, Q_FINAL_STATES, from_job_status
from queue import Queue
from RWLock import RWLock
from ShorJobDescriptor import ShorJobDescriptor
from threading import Thread, Event
from time import time
from verbose import Verbose
import concurrent.futures


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


class _QTasks(Verbose):

    def __init__(self, *args, **kwargs):
        super(_QTasks, self).__init__(name="QTasks")
        self._abort = Event()
        self._job_queue = Queue()
        self._job_states = {}
        self._cancellation_events = {}
        self._rw_lock = RWLock()
        self._worker_thread = Thread(target=self._job_handler, daemon=True)

    def start(self):
        self._worker_thread.start()

    def join(self):
        self._worker_thread.join()

    def abort(self):
        self._abort.set()

    def request_job(self, job_descriptor: ShorJobDescriptor):
        key = str(job_descriptor)
        self._rw_lock.acquire_read()
        if key in self._job_states:
            state = self._job_states[key]
            self._rw_lock.release_read()
            return str(state)
        self._rw_lock.release_read()
        self._rw_lock.acquire_write()
        self._submit_job(job_descriptor)
        self._rw_lock.release_write()
        return str(self._get_state(job_descriptor))

    def request_cancel(self, job_descriptor: ShorJobDescriptor):
        key = str(job_descriptor)
        state = self._get_state(job_descriptor)
        if not state:
            return str(QResponse(key,
                                 status=QStatus.JOB_NOT_FOUND,
                                 server_response="Job not found. nothing to cancel"))
        self._rw_lock.acquire_write()
        self._cancellation_events[key].set()
        self._rw_lock.release_write()
        return str(QResponse(key,
                             status=QStatus.CANCELLED,
                             server_response="Cancelling job"))

    def request_status(self, job_descriptor: ShorJobDescriptor):
        key = job_descriptor
        state = self._get_state(job_descriptor)
        if not state:
            return str(QResponse(key, status=QStatus.JOB_NOT_FOUND))
        return str(state)

    def _submit_job(self, job_descriptor: ShorJobDescriptor):
        k = str(job_descriptor)
        self._rw_lock.acquire_write()
        self._cancellation_events[k] = Event()
        self._job_states[k] = QResponse(key=k, status=QStatus.REQUESTED)
        self._job_queue.put(job_descriptor)
        self._rw_lock.release_write()

    def _get_state(self, job_descriptor: ShorJobDescriptor) -> QResponse:
        key = str(job_descriptor)
        state = None
        self._rw_lock.acquire_read()
        if key in self._job_states:
            state = self._job_states[key]
        self._rw_lock.release_read()
        return state

    def _update_status(self,
                       job_descriptor: ShorJobDescriptor,
                       status: QStatus,
                       place_in_queue=-1,
                       results=None,
                       error=None):
        if status == QStatus.QUEUED and place_in_queue < 0:
            raise ValueError("Job '{}' updated to QUEUED state but no place in queue provided"
                             "".format(str(job_descriptor)))
        elif status == QStatus.ERROR and not error:
            raise ValueError("Job '{}' updated to ERROR state but no error text provided"
                             "".format(str(job_descriptor)))
        key = str(job_descriptor)
        self.logger.debug("In update_status for job {}. status: {}, queue: {}, error: {}, results: {}"
                          "".format(key, status, place_in_queue, error, results))
        self._rw_lock.acquire_write()
        self._job_states[key].status = status
        self._job_states[key].update_response_from_status()
        if status == QStatus.QUEUED:
            self._job_states[key].queue_position = int(place_in_queue)
        elif status == QStatus.ERROR:
            self._job_states[key].error = error
        elif status == QStatus.DONE:
            self._job_states[key].result = results
        self._rw_lock.release_write()

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
                self.logger.debug("No backend found, updating response and waiting for cleanup...")
                self._update_status(job_descriptor,
                                    status=QStatus.ERROR,
                                    error="Couldn't get backend for job: {}".format(e))
            except AquaError as e:
                self.logger.debug("Aqua error for N={}, a={}: {}".format(n, a, e))
                self._update_status(job_descriptor,
                                    status=QStatus.ERROR,
                                    error="Aqua didn't like the input N={},a={}: {}".format(n, a, e))
        return None, None

    def _do_job(self, job_descriptor: ShorJobDescriptor):
        key = str(job_descriptor)
        self.logger.debug("In do_job for job {}".format(key))
        self._rw_lock.acquire_read()
        cancellation_event = self._cancellation_events[key]
        self._rw_lock.release_read()
        job, circ = self._start_shor_job(job_descriptor)
        if not job:
            self.logger.debug("Job {} failed to start (backend error)".format(key))
            return "Failed"
        status = job.status()
        while status not in Q_FINAL_STATES:
            self.logger.debug("do_job iteration for {}, status is {}".format(key, status))
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
        self.logger.debug("do_job done for {}".format(key))
        return "Done"

    def _job_handler(self):
        with concurrent.futures.ThreadPoolExecutor() as executor:
            futures = {}
            pending_cleanup = []
            log_every_n_iterations = 100
            iteration = 0
            handled_queue_items = 0
            done_futures = 0
            cleaned = 0
            self.logger.debug("Starting main handler loop")
            while not self._abort.is_set():
                while not self._job_queue.empty():
                    job_descriptor = self._job_queue.get()
                    futures[executor.submit(self._do_job, job_descriptor)] = str(job_descriptor)
                    handled_queue_items += 1
                if futures:
                    # Check for status of the futures which are currently working
                    done, not_done = concurrent.futures.wait(futures,
                                                             timeout=0.25,
                                                             return_when=concurrent.futures.FIRST_COMPLETED)
                    for future in done:
                        self.logger.debug("{} threads done, processing results...".format(len(done)))
                        key = str(futures[future])
                        data = None
                        try:
                            data = future.result()
                        except Exception as e:
                            self.logger.debug("Job {} failed with data: {}\n\nException:\n{}".format(key, data, e))
                        pending_cleanup.append({
                            'job': key,
                            'cleanup_time': QTasks.CLEANUP_TIMEOUT + int(round(time()))
                        })
                        self._rw_lock.acquire_write()
                        del futures[future]
                        del self._cancellation_events[key]
                        self._rw_lock.release_write()
                        done_futures += 1
                while pending_cleanup and pending_cleanup[0]['cleanup_time'] <= int(round(time())):
                    key = pending_cleanup[0]['job']
                    self._rw_lock.acquire_write()
                    del self._job_states[key]
                    self._rw_lock.release_write()
                    pending_cleanup.pop(0)
                    cleaned += 1
                if iteration == log_every_n_iterations:
                    self.logger.debug("Reached {} handler iterations. Got {} queue items, {} done futures, {} cleaned "
                                      "responses".format(log_every_n_iterations, handled_queue_items, done_futures,
                                                         cleaned))
                    handled_queue_items = 0
                    done_futures = 0
                    cleaned = 0
                    iteration = 0
                iteration += 1
                self._abort.wait(timeout=QTasks.EXTERNAL_INTERVAL)

    def _shors_period_finder(self, job_descriptor: ShorJobDescriptor, fleet: QFleet, shots=None):
        key = str(job_descriptor)
        self.logger.debug("Constructing circuit for Shor's algorithm on {}".format(key))
        self._update_status(job_descriptor,
                            status=QStatus.CONSTRUCTING_CIRCUIT)
        n = job_descriptor.n
        a = job_descriptor.a
        shor = Shor(N=n, a=a)
        circ = shor.construct_circuit(measurement=True)
        self.logger.debug("Constructed circuit for {}, finding backend...".format(key))
        self._update_status(job_descriptor,
                            status=QStatus.FINDING_BACKEND)
        qcomp = fleet.get_best_backend(circ.n_qubits, job_descriptor.allow_simulator)
        if not qcomp:
            raise QNoBackendException("No viable backend with {} qubits for job {}".format(circ.n_qubits, key))
        self.logger.debug("Got backend '{}' for job {}. Executing...".format(qcomp.name(), key))
        self._update_status(job_descriptor,
                            status=QStatus.REQUEST_EXECUTE)
        kwargs = {'backend': qcomp}
        if shots:
            kwargs['shots'] = shots
        job = execute(circ, **kwargs)
        self.logger.debug("Started job {}, status is {}".format(key, job.status()))
        self._update_status_by_job(job_descriptor, job, circ)
        return job, circ
