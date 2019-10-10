from QLogin import QLogin
from qiskit import IBMQ


class QFleet(object):
    def __init__(self):
        QLogin.refresh_login()
        self._providers = IBMQ.providers()
        self._backends = {}
        for provider in self._providers:
            self._backends[str(provider)] = provider.backends()

    def _is_real_viable(self, backend, min_qubits):
        return (not backend.configuration().simulator) and min_qubits <= backend.configuration().n_qubits

    def _is_sim_viable(self, backend, min_qubits):
        return backend.configuration().simulator and min_qubits <= backend.configuration().n_qubits

    def _is_viable(self, backend, min_qubits, allow_simulator):
        return self._is_real_viable(backend, min_qubits) or (allow_simulator and self._is_sim_viable(backend, min_qubits))

    def get_best_backend(self, min_qubits, allow_simulator):
        candidates = []
        for provider in self._providers:
            for backend in self._backends[str(provider)]:
                if self._is_viable(backend, min_qubits, allow_simulator):
                    print("Adding backend with {} pending jobs ({} qubits)"
                          "".format(backend.status().pending_jobs,
                                    backend.configuration().n_qubits))
                    candidates.append(backend)
        if not candidates:
            print("No backend has at least {} qubits!".format(min_qubits))
            return None
        chosen = min(candidates, key=lambda backend: backend.status().pending_jobs)
        print("Chose backend with {} pending jobs ({} qubits{})"
              "".format(chosen.status().pending_jobs,
                        chosen.configuration().n_qubits,
                        ", simulator" if chosen.configuration().simulator else ""))
        return chosen

    def has_viable_backend(self, min_qubits, allow_simulator):
        for provider in self._providers:
            for backend in self._backends[str(provider)]:
                if self._is_viable(backend, min_qubits, allow_simulator):
                    return True
        return False
