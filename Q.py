from qiskit import execute
from qiskit.circuit import ClassicalRegister, QuantumRegister, QuantumCircuit
from qiskit.providers import JobStatus
from qiskit.providers.ibmq import IBMQ
from qiskit.tools.visualization import plot_histogram, plot_bloch_multivector
from qiskit.tools.monitor import job_monitor
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from flask import request
from time import sleep


class Q:

    _RESPONSE_MAP = {}
    _CIRCUIT_MAP = {}

    @staticmethod
    def _is_job_done(job):
        return job.status() in [JobStatus.CANCELLED, JobStatus.DONE, JobStatus.ERROR]

    @staticmethod
    def _job_state_response(job):
        status = job.status()
        if status == JobStatus.QUEUED:
            return "In queue ({})".format(job.queue_position())
        if status == JobStatus.INITIALIZING:
            return "Initializing job..."
        if status == JobStatus.RUNNING:
            return "Running job..."
        if status == JobStatus.VALIDATING:
            return "Validating job..."
        return "ERROR: Unhandled status '{}'".format(status.name)

    @staticmethod
    def _job_end_response(job, circ):
        status = job.status()
        msg = "Job ended with message:\n{}".format(status.value)
        if status == JobStatus.DONE:
            msg += "\nResult histogram data:\n{}".format(job.result().get_counts(circ))
        return msg

    @staticmethod
    def execute_circuit(key, circ, provider_name, backend_name, interval=5.0):
        IBMQ.load_account()
        provider = IBMQ.get_provider(provider_name)
        qcomp = provider.get_backend(backend_name)
        job = execute(circ, backend=qcomp)
        while not Q._is_job_done(job):
            Q._RESPONSE_MAP[key] = Q._job_state_response(job)
            sleep(interval)
        Q._RESPONSE_MAP[key] = Q._job_end_response(job, circ)

    @staticmethod
    def test_quantum_run_response():
        key = request.remote_addr
        if key in Q._RESPONSE_MAP:
            return Q._RESPONSE_MAP[key]
        Q._RESPONSE_MAP[key] = "Constructing circuit..."
        qr = QuantumRegister(2)
        cr = ClassicalRegister(2)
        circ = QuantumCircuit(qr, cr)
        circ.h(qr[0])
        circ.cx(qr[0], qr[1])
        circ.measure(qr, cr)
        Q._CIRCUIT_MAP[key] = circ
        Q._RESPONSE_MAP[key] = "Connecting to backend..."
        scheduler = AsyncIOScheduler()
        scheduler.add_job(Q.execute_circuit,
                          args=[key, circ, 'ibm-q', 'ibmq_ourense'],
                          trigger='date')
        scheduler.start()
        return Q._CIRCUIT_MAP[key]
