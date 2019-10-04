from qiskit import execute
from qiskit.circuit import ClassicalRegister, QuantumRegister, QuantumCircuit
from qiskit.providers.ibmq import IBMQ
from qiskit.providers.ibmq.api_v2.exceptions import RequestsApiError
from qiskit.providers.ibmq.exceptions import IBMQAccountError
from time import sleep


class Q:

    CREDENTIAL_REFRESH_INTERVAL = 5.0

    @staticmethod
    def refresh_login():
        def load_account_oneshot():
            try:
                IBMQ.load_account()
            except IBMQAccountError as e:
                print("Couldn't load IBMQ account: {}".format(e))
                print("Try again, loading API key from file...")
                with open("ibmq_api_token", 'r') as file:
                    IBMQ.save_account(file.read())
                IBMQ.load_account()
        try:
            load_account_oneshot()
        except RequestsApiError as e:
            if "Origin Time-out" in "{}".format(e):
                print("TOKEN TIMED OUT... re-reading token file in a loop")
                successful_login = False
                while not successful_login:
                    try:
                        load_account_oneshot()
                        successful_login = True
                    except Exception as e:
                        print("Couldn't load account (maybe API token file is out of date?): {}".format(e))
                        sleep(Q.CREDENTIAL_REFRESH_INTERVAL)
            else:
                raise e

    @staticmethod
    def execute_circuit():
        Q.refresh_login()
        qr = QuantumRegister(2)
        cr = ClassicalRegister(2)
        circ = QuantumCircuit(qr, cr)
        circ.h(qr[0])
        circ.cx(qr[0], qr[1])
        circ.measure(qr, cr)
        provider = IBMQ.get_provider('ibm-q')
        qcomp = provider.get_backend('ibmq_ourense')
        job = execute(circ, backend=qcomp)
        print("Started job, status is {}".format(job.status()))
        return job, circ
