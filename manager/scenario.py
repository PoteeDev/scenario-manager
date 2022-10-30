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
from storage import storage


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
    entities: list
    actions: list
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
        scenario = collection.find_one({"id": "scenario"})
        self.period = convert_time(scenario["period"])
        self.actions = scenario["actions"]
        self.services = scenario["services"]

    def get_entities(self):
        db_entities = self.client["ad"]["entities"]
        entities = db_entities.find(
            {"blocked": {"$ne": True}, "login": {"$ne": "admin"}}, {"name": 1}
        )
        if entities:
            self.entities = list(map(lambda x: x["name"], entities))
        else:
            self.entities = []


class Score(Scenario):
    def __init__(self) -> None:
        super().__init__()

        self.round = RoundStatus().get_round()
        self.scoreboard = self.client["ad"]["scoreboard"]
        for _id in self.entities:
            services = dict()
            for name, service in self.services.items():
                services[f"srv.{name}"] = {
                    "reputation": service["reputation"],
                    "gained": 0,
                    "lost": 0,
                    "score": 0,
                    "sla": 0,
                }
            self.scoreboard.update_one(
                {
                    "id": _id,
                },
                {"$setOnInsert": services},
                upsert=True,
            )

    def get_matching(self, event):
        for key in storage:
            if re.match(event, key):
                yield key.split("_")[3], storage[key]

    def get_status(self, entity):
        for service in self.services:
            ping_action = f"ping_{entity}_{service}"
            if not storage.get(ping_action):
                yield {service: -1}
            pattern = f"\w{{3}}_{entity}_{service}_.*"
            results = dict(self.get_matching(pattern)).values()
            if all(results):
                yield service, 1
            elif any(results):
                yield service, 0
            else:
                yield service, -1

    def get_exploits(self, entity):
        for service in self.services:
            pattern = f"exploit_{entity}_{service}_.*"
            yield service, dict(self.get_matching(pattern))

    def update_services(self, entity, services):
        for service_name, status in services.items():
            service = self.scoreboard.find_one(
                {"id": entity}, {f"srv.{service_name}": 1}
            )
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
        base_dir = "manager/actions"
        actions_dir = "actions"
        actions_path = Path(actions_dir)
        for filename in actions_path.glob("[!_]*"):
            print(filename)
            action_module = importlib.import_module(f"{actions_dir}.{filename.stem}")
            self.actions_modules[filename.stem] = action_module.action

    async def start(self):
        print(self.actions_modules)
        tasks_total = 0
        for action in self.actions:
            tasks = []
            for entity in self.entities:
                for service in self.services:
                    tasks.append(
                        asyncio.ensure_future(
                            self.actions_modules[action]()(
                                entity,
                                service,
                                service_info=self.services[service],
                                round=self.round,
                            )
                        )
                    )
            await asyncio.gather(*tasks)
            tasks_total += len(tasks)
        self.round_status.increment_round()

    # def run(self):
    #     runner = RunnerTask()
    #     logs = ActionsLogs()
    #     for action in self.actions:
    #         req = self.generate_request(action)
    #         if req:
    #             print("-->", req)
    #             response = runner.send("runner", req)
    #             print("<--", response)
    #             for result in response:
    #                 r = Action(
    #                     self.round,
    #                     result["id"],
    #                     action,
    #                     result["srv"],
    #                     result["answer"],
    #                     result["extra"],
    #                 )
    #                 if not self.result[r.entity].get(r.srv):
    #                     self.result[r.entity] |= {r.srv: {"exploit": {}}}
    #                 if r.extra == "error":
    #                     if action != "exploit":
    #                         self.result[r.entity][r.srv][action] = 0
    #                     print(result)
    #                     continue
    #                 match action:
    #                     case "ping":
    #                         answer = 0
    #                         if r.answer == "pong":
    #                             answer = 1
    #                         self.result[r.entity][r.srv][action] = answer
    #                     case "get":
    #                         answer = 0
    #                         if (
    #                             self.flags.validate(
    #                                 r.entity,
    #                                 r.srv,
    #                                 r.extra,
    #                                 r.answer,
    #                             )
    #                             or self.round == 0
    #                         ):
    #                             answer = 1
    #                         self.result[r.entity][r.srv][action] = answer
    #                     case "put":
    #                         self.flags.put(
    #                             r.entity,
    #                             r.srv,
    #                             *r.extra.split("_"),
    #                             r.answer,
    #                         )
    #                         self.result[r.entity][r.srv][action] = 1
    #                     case "exploit":
    #                         self.result[r.entity][r.srv][action] |= {
    #                             r.extra: int(r.answer)
    #                         }

    #                     case _:
    #                         self.result[r.entity][r.srv][action] = int(r.answer)
    #                 logs.add(result)
    #     self.round_status.increment_round()


if __name__ == "__main__":
    import time

    start_time = time.time()
    asyncio.run(Round().start())
    print("--- %s seconds ---" % (time.time() - start_time))
    # scenario = Scenario()
    # score = Score()

    # start_time = time.time()
    # for i in range(scenario.rounds):
    #     print("Round:", i)
    #     round = Round()
    #     round.run()
    #     score.update_scoreboard(round.result, i)
    #     time.sleep(scenario.period - ((time.time() - start_time) % scenario.period))
    # elapsed = time.time() - start_time
    # print(
    #     "Elapsed time:",
    #     time.strftime(
    #         "%H:%M:%S.{}".format(str(elapsed % 1)[2:])[:15], time.gmtime(elapsed)
    #     ),
    # )
