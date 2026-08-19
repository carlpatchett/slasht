from collections import OrderedDict


class LRUCache:
    """A fixed-size cache that evicts the least recently used entry."""

    def __init__(self, capacity):
        self.store = OrderedDict()
        self.capacity = capacity

    def get(self, key):
        if key not in self.store:
            return None
        self.store.move_to_end(key)
        return self.store[key]

    def put(self, key, value):
        if key in self.store:
            self.store.move_to_end(key)
        self.store[key] = value
        if len(self.store) > self.capacity:
            self.store.popitem(last=False)
