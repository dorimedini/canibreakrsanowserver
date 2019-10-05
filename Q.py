from QFleet import QFleet
from QLogin import QLogin
from qiskit import execute
from qiskit.aqua.algorithms.single_sample.shor.shor import Shor


class Q:
    @staticmethod
    def shors_period_finder(n, a, shots=None):
        QLogin.refresh_login()
        shor = Shor(N=n, a=a)
        circ = shor.construct_circuit(measurement=True)
        fleet = QFleet()
        qcomp = fleet.get_best_backend(circ.n_qubits)
        if not qcomp:
            raise Exception("No viable backend with {} qubits for input N={},a={}".format(circ.n_qubits, n, a))
        kwargs = {'backend': qcomp}
        if shots:
            kwargs['shots'] = shots
        job = execute(circ, **kwargs)
        print("Started job, status is {}".format(job.status()))
        return job, circ
