from qiskit.providers.ibmq import IBMQ
from qiskit.providers.ibmq.api_v2.exceptions import RequestsApiError
from qiskit.providers.ibmq.exceptions import IBMQAccountError
from time import sleep


IBMQ_TOKEN_FILENAME = "ibmq_api_token"


class QLogin(object):

    CREDENTIAL_REFRESH_INTERVAL = 5.0

    @staticmethod
    def refresh_login():
        def load_account_oneshot():
            try:
                IBMQ.load_account()
            except IBMQAccountError as e:
                print("Couldn't load IBMQ account: {}".format(e))
                print("Try again, loading API key from file...")
                with open(IBMQ_TOKEN_FILENAME, 'r') as file:
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
                        sleep(QLogin.CREDENTIAL_REFRESH_INTERVAL)
            else:
                raise e
