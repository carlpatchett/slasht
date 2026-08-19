from collections import OrderedDict


class EntryStore:
    """A bounded store that drops the oldest touched record."""

    def __init__(self, limit):
        self.entries = OrderedDict()
        self.limit = limit

    def lookup(self, name):
        if name not in self.entries:
            return None
        self.entries.move_to_end(name)
        return self.entries[name]

    def record(self, name, payload):
        if name in self.entries:
            self.entries.move_to_end(name)
        self.entries[name] = payload
        if len(self.entries) > self.limit:
            self.entries.popitem(last=False)
