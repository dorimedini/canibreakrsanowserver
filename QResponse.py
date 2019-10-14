import json
from QFleet import QFleet
from QStatus import QStatus, Q_FINAL_STATES


class FrozenClass(object):
    __is_frozen = False

    def __setattr__(self, key, value):
        if self.__is_frozen and not hasattr(self, key):
            raise TypeError("{}} is a frozen class".format(self))
        object.__setattr__(self, key, value)

    def _freeze(self):
        self.__is_frozen = True


class QResponse(FrozenClass):
    def __init__(self,
                 key,
                 status,
                 backend=None,
                 server_response=None,
                 queue_position=-1,
                 result=None,
                 error=None):
        self.key = key
        self.status = status
        self.server_response = server_response
        self.queue_position = queue_position
        self.result = result
        self.error = error
        self.backend = None
        self.is_simulator = None
        self.n_qubits = None
        self._freeze()
        self.update_backend_fields(backend)
        if not server_response:
            self.update_response_from_status()

    def update_backend_fields(self, backend):
        self.backend = "" if not backend else backend.name()
        self.is_simulator = None if not backend else QFleet.is_simulator(backend)
        self.n_qubits = 0 if not backend else QFleet.n_qubits(backend)

    def update_response_from_status(self):
        self.server_response = self.status.value

    @staticmethod
    def update(qresponse,
               status,
               backend=None,
               server_response=None,
               queue_position=-1,
               result=None,
               error=None):
        qresponse.status = status

        if server_response:
            qresponse.server_response = server_response
        else:
            qresponse.update_response_from_status()

        if backend:
            qresponse.update_backend_fields(backend)
        if int(queue_position) >= 0:
            qresponse.queue_position = queue_position
        if error:
            qresponse.error = error
        if result:
            qresponse.result = result

        return qresponse

    def __repr__(self):
        return json.dumps({
            'key': self.key,
            'status': self.status.name,
            'backend': self.backend,
            'is_simulator': self.is_simulator,
            'n_qubits': self.n_qubits,
            'server_response': self.server_response,
            'queue_position': self.queue_position,
            'result': self.result,
            'error': self.error
        })
