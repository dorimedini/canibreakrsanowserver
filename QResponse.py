import json
from QStatus import QStatus


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
                 server_response=None,
                 queue_position=-1,
                 result=None,
                 error=None):
        self.key = key
        self.server_response = server_response
        self.queue_position = queue_position
        self.status = status
        self.result = result
        self.error = error
        self._freeze()
        if not server_response:
            self.update_response_from_status()

    def update_response_from_status(self):
        self.server_response = self.status.value

    def __repr__(self):
        return json.dumps({
            'key': self.key,
            'server_response': self.server_response,
            'queue_position': self.queue_position,
            'status': {
                self.status.name: self.status.value
            },
            'result': self.result,
            'error': self.error
        })
