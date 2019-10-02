from qiskit import *
from qiskit.providers import JobStatus
from qiskit.tools.visualization import plot_histogram, plot_bloch_multivector
from qiskit.tools.monitor import job_monitor
from time import sleep


class Q:
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
    def _job_end_response(job, circuit):
        status = job.status()
        msg = "Job ended with message:\n{}".format(status.value)
        if status == JobStatus.DONE:
            msg += "\nResult histogram data:\n{}".format(job.result().get_counts(circuit))
        return msg

    @staticmethod
    def test_quantum_run_response():
        qr = QuantumRegister(2)
        cr = ClassicalRegister(2)
        circuit = QuantumCircuit(qr, cr)
        circuit.h(qr[0])
        circuit.cx(qr[0], qr[1])
        circuit.measure(qr, cr)
        IBMQ.load_account()
        provider = IBMQ.get_provider('ibm-q')
        qcomp = provider.get_backend('ibmq_ourense')
        job = execute(circuit, backend=qcomp)
        while not Q._is_job_done(job):
            yield Q._job_state_response(job)
        return Q._job_end_response(job, circuit)

