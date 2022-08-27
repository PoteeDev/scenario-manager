import redis
import os

class FlagStorage:
    def __init__(self) -> None:
        self.conn = redis.Redis(
            os.getenv("REDIS_HOST", "localhost"), password=os.getenv("REDIS_PASSWORD")
        )

    def put(self, _id, service_name, checker, flag, uniq):
        pair = {"flag": flag, "id": uniq}
        self.conn.hset(f"{_id}_{service_name}_{checker}", mapping=pair)

    def get_uniq(self, _id, service_name, checker):
        pair = self.conn.hgetall(f"{_id}_{service_name}_{checker}")
        if pair:
            return pair.get(b"id").decode()

    def validate(self, _id, service_name, checker, flag):
        pair = self.conn.hgetall(f"{_id}_{service_name}_{checker}")
        if pair:
            if pair.get(b"flag").decode() == flag:
                return True