import importlib
import os
import time
import pika
import uuid
import json
import redis
import random
import string
from pathlib import Path
from pymongo import MongoClient
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime


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

    def calculate(self, _id, service_name, service: dict):
        
        if service.get("exploit"):
            exploits = service.pop("exploit")
            self.update_exploits(_id, service_name, exploits)
        service_results = list()
        for checkers in service.values():
            service_results.extend(checkers.values())
        if all(service_results):
            status = 1
        elif any(service_results):
            status = 0
        else:
            status = -1

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
            service["score"] = service["reputation"] * service["sla"]
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
                            f"srv.{service_name}.reputation": -exploit_cost,
                        }
                    },
                )

    def update_scoreboard(self, round_result):
        for entity_name, entity_result in round_result.items():
            for service_name, service in entity_result.items():
                self.calculate(entity_name, service_name, service)


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


@dataclass
class Action:
    round: int
    entity: str
    action: str
    srv: str
    answer: str
    extra: str
    time: datetime = datetime.now()


class ActionsLogs:
    def __init__(self) -> None:
        client = MongoClient(
            os.getenv("MONGO_HOST", "localhost"),
            username="admin",
            password=os.getenv("MONGO_PASS"),
        )
        self.collection = client["ad"]["actions_logs"]

    def add(self, action: Action):
        self.collection.insert_one(action)


class Round(Scenario):
    def __init__(self) -> None:
        super().__init__()
        self.round_status = RoundStatus()
        self.round = self.round_status.get_round()
        self.flags = FlagStorage()
        self.result = defaultdict(dict)
        self.actions_modules = dict()
        self.load_actions()

    # def generate_request(self, action):
    #     req = list()
    #     for name, service in self.services.items():
    #         for entity in self.entities:
    #             arguments = []
    #             if action == "ping":
    #                 arguments.append(
    #                     {
    #                         "extra": action,
    #                         "args": [action, f"{service['domain']}.{entity}"],
    #                     }
    #                 )

    #             elif action in ("get", "put"):
    #                 if self.result[entity][name]["ping"] == 0:
    #                     self.result[entity][name] |= {
    #                         "get": 0,
    #                         "put": 0,
    #                     }
    #                     continue

    #                 for checker in service["checkers"]:
    #                     if action == "put":
    #                         flag = generate_flag()
    #                         arguments.append(
    #                             {
    #                                 "extra": f"{checker}_{flag}",
    #                                 "args": [
    #                                     action,
    #                                     f"{service['domain']}.{entity}",
    #                                     checker,
    #                                     flag,
    #                                 ],
    #                             }
    #                         )
    #                     elif action == "get":
    #                         if self.round == 0:
    #                             continue
    #                         value = self.flags.get_uniq(entity, name, checker)
    #                         arguments.append(
    #                             {
    #                                 "extra": checker,
    #                                 "args": [
    #                                     action,
    #                                     f"{service['domain']}.{entity}",
    #                                     checker,
    #                                     value,
    #                                 ],
    #                             }
    #                         )
    #             elif action == "exploit":
    #                 for exploit_name, values in service["exploits"].items():
    #                     if self.round in values["rounds"]:
    #                         arguments.append(
    #                             {
    #                                 "extra": exploit_name,
    #                                 "args": [
    #                                     action,
    #                                     f"{service['domain']}.{entity}",
    #                                     exploit_name,
    #                                 ],
    #                             }
    #                         )
    #             for args in arguments:
    #                 req.append(
    #                     {
    #                         "id": entity,
    #                         "script": service["script"],
    #                         "srv": name,
    #                         **args,
    #                     }
    #                 )
    #     return req

    def load_actions(self):
        base_dir = "manager"
        actions_dir = "actions"
        actions_path = Path(actions_dir)

        for filename in actions_path.glob("[!_]*"):
            action_module = importlib.import_module(f"{actions_dir}.{filename.stem}")
            self.actions_modules[filename.stem] = action_module.action

    def run(self):
        runner = RunnerTask()
        logs = ActionsLogs()
        for action_name in self.actions:
            print(f"action {action_name}")
            request_list = list()
            for service_name, service in self.services.items():
                print(f"service {service_name}")
                for entity in self.entities:
                    match action_name:
                        case "exploit":
                            args = service.get("exploits"), self.round
                        case "ping":
                            args = None
                        case _:
                            args = service.get("checkers")
                    request_list.extend(
                        list(
                            self.actions_modules[action_name](
                                entity, service["script"], service_name
                            ).send(args)
                        )
                    )
            
            print(request_list)
            if not request_list:
                continue
            response = runner.send("runner", request_list)
            for result in response:
                r = Action(
                    self.round,
                    result["id"],
                    action_name,
                    result["srv"],
                    result["answer"],
                    result["extra"],
                )
                answer = self.actions_modules[action_name](
                    result["id"], None, result["srv"]
                ).receive(r)
                if not self.result[r.entity].get(r.srv):
                    self.result[r.entity] |= {r.srv: {action_name: {}}}
                elif not self.result[r.entity][r.srv].get(action_name):
                    self.result[r.entity][r.srv] |= {action_name: {}}
                self.result[r.entity][r.srv][action_name] |= answer
            print(self.result)
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
