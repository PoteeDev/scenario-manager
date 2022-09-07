storage = dict()


class Storage:
    def __init__(self):
        global storage
        self.storage = storage

    def write(self, *args, result):
        self.storage["_".join(args)] = result

    def read(self, *args):
        return self.storage.get("_".join(args))
