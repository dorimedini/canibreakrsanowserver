from qiskit import execute
from qiskit.circuit import ClassicalRegister, QuantumRegister, QuantumCircuit
from qiskit.providers.ibmq import IBMQ
from qiskit.providers.ibmq.exceptions import IBMQAccountError


class Q:
    @staticmethod
    def execute_circuit():
        qr = QuantumRegister(2)
        cr = ClassicalRegister(2)
        circ = QuantumCircuit(qr, cr)
        circ.h(qr[0])
        circ.cx(qr[0], qr[1])
        circ.measure(qr, cr)
        try:
            IBMQ.load_account()
        except IBMQAccountError as e:
            print("Couldn't load IBMQ account: {}".format(e))
            print("Loading API key from file...")
            with open("ibmq_api_token", 'r') as file:
                IBMQ.save_account(file.read())
            IBMQ.load_account()
        provider = IBMQ.get_provider('ibm-q')
        qcomp = provider.get_backend('ibmq_ourense')
        job = execute(circ, backend=qcomp)
        print("Started job, status is {}".format(job.status()))
        return job, circ
