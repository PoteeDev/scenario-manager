import asyncio
import importlib
import os
import re
import time
import redis
import random
import string
from pathlib import Path
from pymongo import MongoClient, DESCENDING, ASCENDING
from storage import Storage


class Settings:
    def __init__(self) -> None:
        self.client = MongoClient(
            os.getenv("MONGO_HOST", "localhost"),
            username="admin",
            password=os.getenv("MONGO_PASS", "admin"),
        )
        self.settings = self.client["ad"]["settings"]
        self.upload_settings()

    def upload_settings(self):
        settings = self.settings.find_one({"id": "scenario"})
        if settings:
            self.period = convert_time(settings.get("period"))
            self.actions = settings.get("actions")
            self.services = settings.get("services")


class RoundStatus:
    def __init__(self) -> None:
        self.client = MongoClient(
            os.getenv("MONGO_HOST", "localhost"),
            username="admin",
            password=os.getenv("MONGO_PASS"),
        )
        self.status = self.client["ad"]["status"]

    def increment_round(self):
        self.status.update_one({"_id": "status"}, {"$inc": {"round": 1}}, upsert=True)

    def get_round(self):
        result = self.status.find_one({"_id": "status"}, {"round": 1})
        if result:
            return result["round"]
        return 0


def convert_time(value):
    amount, suffix = value[:-1], value[-1]
    if suffix == "s":
        return float(amount)
    elif suffix == "m":
        return float(amount) * 60.0


class Scenario:
    rounds: int
    period: int
    scenario: dict
    entities: list
    full_entities: list
    actions: list
    global_actions: list
    services: dict

    def __init__(self) -> None:
        self.client = MongoClient(
            os.getenv("MONGO_HOST", "localhost"),
            username="admin",
            password=os.getenv("MONGO_PASS"),
        )
        self.get_entities()
        self.load_scenario()

    def load_scenario(self):
        collection = self.client["ad"]["settings"]
        self.scenario = collection.find_one({"id": "scenario"})
        self.period = convert_time(self.scenario["period"])
        self.actions = self.scenario["actions"]
        self.global_actions =  self.scenario["global_actions"]
        self.services = self.scenario["services"]

    def get_entities(self):
        db_entities = self.client["ad"]["entities"]
        self.full_entities = list(
            db_entities.find({"blocked": {"$ne": True}, "login": {"$ne": "admin"}})
        )
        if self.full_entities:
            self.entities = list(map(lambda x: x["login"], self.full_entities))
        else:
            self.entities = []


storage = Storage()


class Score(Scenario):
    def __init__(self) -> None:
        super().__init__()

        self.round = RoundStatus().get_round()
        self.scoreboard = self.client["ad"]["scoreboard"]
        for entity in self.full_entities:
            services = dict()
            for name, service in self.services.items():
                services[f"srv.{name}"] = {
                    "reputation": service["reputation"],
                    "gained": 0,
                    "lost": 0,
                    "score": 0,
                    "sla": 0,
                }
            print(entity["login"])
            self.scoreboard.update_one(
                {"id": entity["login"], "name": entity["name"]},
                {"$setOnInsert": services},
                upsert=True,
            )

    def get_status(self, entity):
        print(dict(storage.search("*")))
        for service in self.services:
            if storage.read("ping", entity, service) == 0:
                yield service, -1
            else:
                pattern = f"???_{entity}_{service}_*"
                results = map(int, dict(storage.search(pattern)).values())
                print(results)
                if all(results):
                    yield service, 1
                elif any(results):
                    yield service, 0
                else:
                    yield service, -1

    def get_exploits(self, entity):
        for service in self.services:
            pattern = f"exploit_{entity}_{service}_*"
            yield service, dict(
                map(lambda kv: (kv[0].split("_")[-1], kv[1]), storage.search(pattern))
            )

    def update_services(self, entity, services):
        for service_name, status in services.items():
            service = self.scoreboard.find_one(
                {"id": entity}, {f"srv.{service_name}": 1}
            )
            print(entity, service)
            service = service["srv"][service_name]
            service_state = 1 if status == 1 else 0
            if service:
                if self.round > 0:
                    service["sla"] = (
                        service["sla"] * (self.round - 1) + service_state
                    ) / self.round
                else:
                    service["sla"] = service_state
                service["status"] = status
                service["score"] = service["reputation"] * service["sla"]
                self.scoreboard.update_one(
                    {"id": entity}, {"$set": {f"srv.{service_name}": service}}
                )

    def update_exploits(self, _id, exploits):
        for service_name, result in exploits.items():
            for name, status in result.items():
                print(name, status)
                exploit_cost = self.services[service_name]["exploits"][name]["cost"]
                if status == 0:
                    self.scoreboard.update_one(
                        {"id": _id}, {"$inc": {f"srv.{service_name}.gained": 1}}
                    )
                else:
                    self.scoreboard.update_one(
                        {"id": _id},
                        {
                            "$inc": {
                                f"srv.{service_name}.lost": 1,
                                f"srv.{service_name}.reputation": -exploit_cost,
                            }
                        },
                    )

    def update_places(self):
        scores = self.scoreboard.find().sort(
            [("total_score", DESCENDING), ("total_lost", ASCENDING)],
        )
        for i, score in enumerate(scores, 1):
            self.scoreboard.update_one(
                {"id": score["id"]},
                {
                    "$set": {
                        "place": i,
                        "last_place": score.get("place", 0),
                    }
                },
            )

    def update_scoreboard(self):
        for entity in self.entities:
            status = self.get_status(entity)
            self.update_services(entity, dict(status))
            exploits = self.get_exploits(entity)
            self.update_exploits(entity, dict(exploits))

            score = self.scoreboard.find_one({"id": entity})
            total_score, total_gained, total_lost = 0, 0, 0
            for service in score["srv"].values():
                total_score += service["score"]
                total_gained += service["gained"]
                total_lost += service["lost"]
            # total_score = sum(map(lambda x: x["score"], score["srv"].values()))
            self.scoreboard.update_one(
                {"id": entity},
                {
                    "$set": {
                        "total_score": total_score,
                        "total_gained": total_gained,
                        "total_lost": total_lost,
                    }
                },
            )
            self.update_places()
        # clear storage
        storage.clear("exploit*")


def generate_flag(n=25):
    return "".join(random.choices(string.ascii_uppercase + string.ascii_lowercase, k=n))


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


class Round(Scenario):
    def __init__(self) -> None:
        super().__init__()
        self.round_status = RoundStatus()
        self.round = self.round_status.get_round()
        self.actions_modules = dict()
        self.load_actions()

    def load_actions(self):
        actions_dir = "actions"
        actions_path = Path(actions_dir)
        for filename in actions_path.glob("[!_]*"):
            print(filename)
            action_module = importlib.import_module(f"{actions_dir}.{filename.stem}")
            self.actions_modules[filename.stem] = action_module.action

    async def start(self):
        for action in self.actions:
            tasks = []
            for entity in self.entities:
                for service, service_info in self.services.items():
                    tasks.append(
                        asyncio.ensure_future(
                            self.actions_modules[action]()(
                                entity,
                                service,
                                service_info=service_info,
                                round=self.round,
                            )
                        )
                    )
            await asyncio.gather(*tasks)
        gloabal_tasks = []
        for action in self.global_actions:
            gloabal_tasks.append(
                asyncio.ensure_future(
                    self.actions_modules[action]()(
                        scenario=self.scenario,
                        round=self.round,
                    )
                )
            )
        await asyncio.gather(*gloabal_tasks)
        self.round_status.increment_round()


if __name__ == "__main__":
    import time

    start_time = time.time()
    asyncio.run(Round().start())
    print("--- %s seconds ---" % (time.time() - start_time))
