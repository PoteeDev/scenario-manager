import os
import time
import yaml
import pika
import uuid
import json
import redis
import random
import string
from pathlib import Path
from pymongo import MongoClient
from collections import defaultdict


class Settings:
    def __init__(self) -> None:
        self.client = MongoClient(
            os.getenv("MONGO_HOST", "localhost"),
            username="admin",
            password=os.getenv("MONGO_PASS"),
        )
        self.settings = self.client["ad"]["settings"]
        self.upload_settings()

    def upload_settings(self):
        file = Path("scenario.yml")
        if file.exists():
            with Path("scenario.yml").open() as s:
                scenario = yaml.safe_load(s.read())
                self.rounds = scenario["rounds"]
                self.period = convert_time(scenario["period"])
                self.actions = scenario["actions"]
                self.services = scenario["services"]
                self.settings.update_one(
                    {"_id": "settings"},
                    {
                        "$set": {
                            "rounds": self.rounds,
                            "period": self.period,
                            "actions": self.actions,
                            "services": self.services,
                        }
                    },
                    upsert=True,
                )
        else:
            settings = self.settings.find_one({"_id": "settings"})
            if settings:
                self.rounds = settings.get("rounds")
                self.period = settings.get("period")
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


class RunnerTask(object):
    def __init__(self):
        self.connection = pika.BlockingConnection(
            pika.ConnectionParameters(
                host=os.getenv("RABBITMQ_HOST", "localhost"),
                credentials=pika.PlainCredentials(
                    os.getenv("RABBITMQ_USER", "admin"),
                    os.getenv("RABBITMQ_PASS", "admin"),
                ),
            )
        )

        self.channel = self.connection.channel()

        result = self.channel.queue_declare(queue="", exclusive=True)
        self.callback_queue = result.method.queue

        self.channel.basic_consume(
            queue=self.callback_queue,
            on_message_callback=self.on_response,
            auto_ack=True,
        )

        self.response = None
        self.corr_id = None

    def on_response(self, ch, method, props, body):
        if self.corr_id == props.correlation_id:
            self.response = body

    def send(self, channel, mes):
        self.response = None
        self.corr_id = str(uuid.uuid4())
        self.channel.basic_publish(
            exchange="",
            routing_key=channel,
            properties=pika.BasicProperties(
                reply_to=self.callback_queue,
                correlation_id=self.corr_id,
            ),
            body=json.dumps(mes),
        )
        self.connection.process_data_events(time_limit=None)
        return json.loads(self.response)


def convert_time(value):
    amount, suffix = value[:-1], value[-1]
    if suffix == "s":
        return float(amount)
    elif suffix == "m":
        return float(amount) * 60.0


class Scenario:
    rounds: int
    period: int
    teams: list
    actions: list
    services: dict

    def __init__(self) -> None:
        self.client = MongoClient(
            os.getenv("MONGO_HOST", "localhost"),
            username="admin",
            password=os.getenv("MONGO_PASS"),
        )
        self.get_teams()
        self.load_scenario()

    def load_scenario(self):
        with Path("scenario.yml").open() as s:
            scenario = yaml.safe_load(s.read())
            self.rounds = scenario["rounds"]
            self.period = convert_time(scenario["period"])
            self.actions = scenario["actions"]
            self.services = scenario["services"]

    def get_teams(self):
        db_teams = self.client["ad"]["teams"]
        teams = db_teams.find({}, {"name": 1})
        if teams:
            self.teams = list(map(lambda x: x["name"], teams))
        else:
            self.teams = []


class Score(Scenario):
    def __init__(self) -> None:
        super().__init__()

        self.round = RoundStatus().get_round()
        self.scoreboard = self.client["ad"]["scoreboard"]
        for _id in self.teams:
            services = dict()
            for name, service in self.services.items():
                services[f"srv.{name}"] = {
                    "hp": service["hp"],
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

    def calculate(self, _id, service_name, service: dict):
        exploits = service.pop("exploit")
        if all(service.values()):
            status = 1
        elif any(service.values()):
            status = 0
        else:
            status = -1

        self.update_exploits(_id, service_name, exploits)
        self.update_service(_id, service_name, status)
        score = self.scoreboard.find_one({"id": _id})
        total_score = sum(map(lambda x: x["score"], score["srv"].values()))
        self.scoreboard.update_one({"id": _id}, {"$set": {"total_score": total_score}})

    def update_service(self, _id, service_name, status):
        service = self.scoreboard.find_one({"id": _id}, {f"srv.{service_name}": 1})
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
            service["score"] = service["hp"] * service["sla"]
            self.scoreboard.update_one(
                {"id": _id}, {"$set": {f"srv.{service_name}": service}}
            )

    def update_exploits(self, _id, service_name, exploits):
        for name, result in exploits.items():
            exploit_cost = self.services[service_name]["exploits"][name]["cost"]
            if result == 0:
                self.scoreboard.update_one(
                    {"id": _id}, {"$inc": {f"srv.{service_name}.gained": 1}}
                )
            else:
                self.scoreboard.update_one(
                    {"id": _id},
                    {
                        "$inc": {
                            f"srv.{service_name}.lost": 1,
                            f"srv.{service_name}.hp": -exploit_cost,
                        }
                    },
                )

    def update_scoreboard(self, round_result):
        for team_name, team_result in round_result.items():
            for service_name, service in team_result.items():
                self.calculate(team_name, service_name, service)


def generate_flag(n=25):
    return "".join(random.choices(string.ascii_uppercase + string.ascii_lowercase, k=n))


class FlagStorage:
    def __init__(self) -> None:
        self.conn = redis.Redis(
            os.getenv("REDIS_HOST", "localhost"), password=os.getenv("REDIS_PASSWORD")
        )

    def put(self, _id, service_name, flag, uniq):
        pair = {"flag": flag, "id": uniq}
        self.conn.hset(f"{_id}_{service_name}", mapping=pair)

    def get_uniq(self, _id, service_name):
        pair = self.conn.hgetall(f"{_id}_{service_name}")
        if pair:
            return pair.get(b"id").decode()

    def validate(self, _id, service_name, flag):
        pair = self.conn.hgetall(f"{_id}_{service_name}")
        if pair:
            if pair.get(b"flag").decode() == flag:
                return True


class Round(Scenario):
    def __init__(self) -> None:
        super().__init__()
        self.round_status = RoundStatus()
        self.round = self.round_status.get_round()
        self.flags = FlagStorage()
        self.result = defaultdict(dict)

    def generate_request(self, action):
        req = list()
        for name, service in self.services.items():
            for team in self.teams:
                arguments = [
                    {
                        "extra": action,
                        "args": [action, f"{service['domain']}.{team}"],
                    }
                ]
                if action != "ping":
                    if self.result[team][name]["ping"] == 0:
                        self.result[team][name] |= {
                            "get": 0,
                            "put": 0,
                        }
                        continue
                if action == "put":
                    flag = generate_flag()
                    arguments = [
                        {
                            "extra": flag,
                            "args": [action, f"{service['domain']}.{team}", flag],
                        }
                    ]
                elif action == "get":
                    if self.round == 0:
                        continue
                    value = self.flags.get_uniq(team, name)
                    arguments = [
                        {
                            "extra": action,
                            "args": [action, f"{service['domain']}.{team}", value],
                        }
                    ]
                elif action == "exploit":
                    arguments = []
                    for exploit_name, values in service["exploits"].items():
                        if values["round"] <= self.round:
                            arguments.append(
                                {
                                    "extra": exploit_name,
                                    "args": [
                                        action,
                                        exploit_name,
                                        f"{service['domain']}.{team}",
                                    ],
                                }
                            )
                for args in arguments:
                    req.append(
                        {
                            "id": team,
                            "script": service["script"],
                            "srv": name,
                            **args,
                        }
                    )
        return req

    def run(self):
        runner = RunnerTask()
        for action in self.actions:
            req = self.generate_request(action)
            if req:
                print("-->", req)
                response = runner.send("runner", req)
                print("<--", response)
                for result in response:
                    if not self.result[result["id"]].get(result["srv"]):
                        self.result[result["id"]] |= {result["srv"]: {"exploit": {}}}
                    if result["extra"] == "error":
                        if action != "exploit":
                            self.result[result["id"]][result["srv"]][action] = 0
                        print(result)
                        continue

                    if action == "get":
                        answer = 0
                        if (
                            self.flags.validate(
                                result["id"], result["srv"], result["answer"]
                            )
                            or self.round == 0
                        ):
                            answer = 1
                        self.result[result["id"]][result["srv"]][action] = answer
                    elif action == "put":
                        self.flags.put(
                            result["id"],
                            result["srv"],
                            result["extra"],
                            result["answer"],
                        )
                        self.result[result["id"]][result["srv"]][action] = 1
                    elif action == "exploit":
                        self.result[result["id"]][result["srv"]][action] |= {
                            result["extra"]: int(result["answer"])
                        }

                    else:
                        self.result[result["id"]][result["srv"]][action] = int(
                            result["answer"]
                        )
        self.round_status.increment_round()


if __name__ == "__main__":
    scenario = Scenario()
    score = Score()

    start_time = time.time()
    for i in range(scenario.rounds):
        print("Round:", i)
        round = Round()
        round.run()
        score.update_scoreboard(round.result, i)
        time.sleep(scenario.period - ((time.time() - start_time) % scenario.period))
    elapsed = time.time() - start_time
    print(
        "Elapsed time:",
        time.strftime(
            "%H:%M:%S.{}".format(str(elapsed % 1)[2:])[:15], time.gmtime(elapsed)
        ),
    )
