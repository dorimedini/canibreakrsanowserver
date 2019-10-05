from QFleet import QFleet
from QLogin import QLogin
from qiskit import execute
from qiskit.circuit import ClassicalRegister, QuantumRegister, QuantumCircuit


class Q:
    @staticmethod
    def execute_circuit(n, a):
        QLogin.refresh_login()
        fleet = QFleet()
        required_bits = n.bit_length()
        qcomp = fleet.get_best_backend(required_bits)
        if not qcomp:
            raise Exception("No viable backend with {} qubits!".format(required_bits))
        qr = QuantumRegister(required_bits)
        cr = ClassicalRegister(required_bits)
        circ = QuantumCircuit(qr, cr)
        for i in range(required_bits):
            circ.h(qr[i])
            if i > 0:
                circ.cx(qr[i - 1], qr[i])
        circ.measure(qr, cr)
        job = execute(circ, backend=qcomp)
        print("Started job, status is {}".format(job.status()))
        return job, circ
