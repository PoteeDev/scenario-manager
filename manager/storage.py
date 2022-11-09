storage = dict()

import redis
import os


class Storage:
    def __init__(self):
        self.conn = redis.Redis(
            os.getenv("REDIS_HOST", "localhost"),
            password=os.getenv("REDIS_PASSWORD"),
            db=1,
        )

    def write(self, *args, result):
        self.conn.set("_".join(args), result)

    def read(self, *args):
        value = self.conn.get("_".join(args))
        if value:
            return int(value.decode())

    def search(self, pattern):
        result = self.conn.keys(pattern)
        if result:
            for row in zip(result, self.conn.mget(result)):
                yield row[0].decode(), row[1].decode()

    def clear(self, pattern):
        for key in self.conn.keys(pattern):
            self.conn.delete(key)


if __name__ == "__main__":
    storage = Storage()
    storage.write("test", "test", result=1)
    storage.write("test", "test1", result=0)
    print(dict(storage.search("test_*")))
    storage.clear("test*")
    print(dict(storage.search("test_*")))
