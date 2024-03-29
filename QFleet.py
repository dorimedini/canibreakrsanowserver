import json
from QLogin import QLogin
from qiskit import IBMQ


class QFleet(object):
    def __init__(self):
        QLogin.refresh_login()
        self._providers = IBMQ.providers()
        self._backends = {}
        for provider in self._providers:
            self._backends[str(provider)] = provider.backends()

    @staticmethod
    def is_simulator(backend):
        return backend.configuration().simulator

    def _pending_jobs(self, backend):
        return backend.status().pending_jobs

    @staticmethod
    def n_qubits(backend):
        return backend.configuration().n_qubits

    def _is_real_viable(self, backend, min_qubits):
        return (not QFleet.is_simulator(backend)) and min_qubits <= QFleet.n_qubits(backend)

    def _is_sim_viable(self, backend, min_qubits):
        return QFleet.is_simulator(backend) and min_qubits <= QFleet.n_qubits(backend)

    def _is_viable(self, backend, min_qubits, allow_simulator):
        return self._is_real_viable(backend, min_qubits) or (allow_simulator and self._is_sim_viable(backend, min_qubits))

    def _best_valid_backend(self, candidates):
        best_real = None
        best_sim = None
        for backend in candidates:
            if QFleet.is_simulator(backend):
                if not best_sim or self._pending_jobs(best_sim) > self._pending_jobs(backend):
                    best_sim = backend
            else:
                if not best_real or self._pending_jobs(best_real) > self._pending_jobs(backend):
                    best_real = backend
        if best_real:
            return best_real
        return best_sim

    def get_backends_list_json(self):
        return json.dumps([{
            'name': str(backend.name()),
            'simulator': bool(QFleet.is_simulator(backend)),
            'n_qubits': int(QFleet.n_qubits(backend)),
            'pending_jobs': int(self._pending_jobs(backend))
        } for backend in self.get_backends_list()])

    def get_backends_list(self):
        return [backend for provider in self._providers for backend in self._backends[str(provider)]]

    def get_best_backend(self, min_qubits, allow_simulator):
        candidates = []
        for backend in self.get_backends_list():
            if self._is_viable(backend, min_qubits, allow_simulator):
                print("Adding backend with {} pending jobs ({} qubits)"
                      "".format(self._pending_jobs(backend),
                                QFleet.n_qubits(backend)))
                candidates.append(backend)
        if not candidates:
            print("No backend has at least {} qubits!".format(min_qubits))
            return None
        chosen = self._best_valid_backend(candidates)
        print("Chose backend with {} pending jobs ({} qubits{})"
              "".format(self._pending_jobs(chosen),
                        QFleet.n_qubits(chosen),
                        ", simulator" if QFleet.is_simulator(chosen) else ""))
        return chosen

    def has_viable_backend(self, min_qubits, allow_simulator):
        for backend in self.get_backends_list():
            if self._is_viable(backend, min_qubits, allow_simulator):
                return True
        return False
