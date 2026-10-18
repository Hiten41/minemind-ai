"""Bounded process-local cache; scope/version keys are checked against DB each request."""
from collections import OrderedDict
from copy import deepcopy
from time import monotonic


class TTLCache:
    def __init__(self, maxsize=128, ttl=120, clock=monotonic):
        self.maxsize, self.ttl, self.clock = maxsize, ttl, clock
        self.entries = OrderedDict()

    def prune(self):
        now = self.clock()
        for key, (expires, _) in list(self.entries.items()):
            if expires <= now:
                del self.entries[key]

    def get(self, key):
        self.prune()
        item = self.entries.get(key)
        if item is None:
            return None
        self.entries.move_to_end(key)
        return deepcopy(item[1])

    def set(self, key, value):
        self.prune()
        self.entries[key] = (self.clock()+self.ttl, deepcopy(value))
        self.entries.move_to_end(key)
        while len(self.entries) > self.maxsize:
            self.entries.popitem(last=False)

    def invalidate_user(self, user_id):
        for key in list(self.entries):
            if key[0] == user_id:
                del self.entries[key]


answers = TTLCache()
