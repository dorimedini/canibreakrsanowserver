from QLogin import QLogin
from qiskit import IBMQ


class QFleet(object):
    def __init__(self):
        QLogin.refresh_login()
        self._providers = IBMQ.providers()
        self._backends = {}
        for provider in self._providers:
            self._backends[str(provider)] = provider.backends()

    def get_best_backend(self, min_qubits):
        candidates = []
        for provider in self._providers:
            for backend in self._backends[str(provider)]:
                if backend.properties() \
                        and min_qubits <= len(backend.properties().to_dict()['qubits']) \
                        and not backend.configuration().simulator:
                    print("Adding backend with {} pending jobs ({} qubits)"
                          "".format(backend.status().to_dict()['pending_jobs'],
                                    len(backend.properties().to_dict()['qubits'])))
                    candidates.append(backend)
        if not candidates:
            print("No backend has at least {} qubits!".format(min_qubits))
            return None
        chosen = min(candidates, key=lambda backend: backend.status().to_dict()['pending_jobs'])
        print("Chose backend with {} pending jobs ({} qubits)"
              "".format(chosen.status().to_dict()['pending_jobs'],
                        len(chosen.properties().to_dict()['qubits'])))
        return chosen

    def has_viable_backend(self, min_qubits):
        for provider in self._providers:
            for backend in self._backends[str(provider)]:
                if backend.properties() \
                        and min_qubits <= len(backend.properties().to_dict()['qubits']) \
                        and not backend.configuration().simulator:
                    return True
        return False
