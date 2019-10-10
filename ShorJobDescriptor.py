import re


class ShorJobDescriptor(object):
    _regex = '^(?P<ip>.+)_(?P<n>[0-9]+)_(?P<a>[0-9]+)(?P<allow_simulator>_sim)?$'

    def __init__(self, source_ip: str, n: int, a: int, allow_simulator=True):
        self._ip = source_ip
        self._n = int(n)
        self._a = int(a)
        self._allow_simulator = allow_simulator

    def __repr__(self):
        base = "{}_{}_{}".format(self._ip, self._n, self._a)
        if self._allow_simulator:
            base += "_sim"
        return base

    @staticmethod
    def from_str(job_description: str):
        match = re.search(ShorJobDescriptor._regex, job_description)
        if not match:
            raise ValueError("Job description '{}' doesn't match regex pattern '{}'"
                             "".format(job_description, ShorJobDescriptor._regex))
        return ShorJobDescriptor(match['ip'], int(match['n']), int(match['a']), bool(match['allow_simulator']))

    @property
    def n(self):
        return self._n

    @property
    def a(self):
        return self._a

    @property
    def allow_simulator(self):
        return self._allow_simulator
