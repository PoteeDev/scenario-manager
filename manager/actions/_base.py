from dataclasses import dataclass
import string
from datetime import datetime
import inspect
import os


@dataclass
class Action:
    round: int
    entity: str
    action: str
    srv: str
    answer: str
    extra: str = None
    time: datetime = datetime.now()


@dataclass
class BaseAction:
    id: string
    script: string
    srv: string
    _domain: str = os.getenv("LOCAL_DOMAIN", "localhost")

    @classmethod
    def from_dict(cls, env):
        return cls(
            **{k: v for k, v in env.items() if k in inspect.signature(cls).parameters}
        )

    def send(self):
        pass

    def receive(self, response: Action):
        pass
