from QFleet import QFleet
from QLogin import QLogin
from qiskit import execute
from qiskit.aqua.algorithms.single_sample.shor.shor import Shor
from ShorJobDescriptor import ShorJobDescriptor


class QNoBackendException(Exception):
    pass


class Q:
    @staticmethod
    def shors_period_finder(job_descriptor: ShorJobDescriptor, shots=None):
        QLogin.refresh_login()
        n = job_descriptor.n
        a = job_descriptor.a
        shor = Shor(N=n, a=a)
        circ = shor.construct_circuit(measurement=True)
        fleet = QFleet()
        qcomp = fleet.get_best_backend(circ.n_qubits, job_descriptor.allow_simulator)
        if not qcomp:
            raise QNoBackendException("No viable backend with {} qubits for input N={},a={}".format(circ.n_qubits, n, a))
        kwargs = {'backend': qcomp}
        if shots:
            kwargs['shots'] = shots
        job = execute(circ, **kwargs)
        print("Started job, status is {}".format(job.status()))
        return job, circ
