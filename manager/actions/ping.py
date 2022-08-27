import os
from actions._base import BaseAction, Action


class PingAction(BaseAction):
    def send(self, *args):
        request = {
            **self.__dict__,
            "extra": "ping",
            "args": ["ping", f"{self.srv}.{self._domain}"],
        }
        yield request

    def receive(self, response: Action):
        if response.answer == "pong":
            return {"ping": 1}
        return {"ping": 0}


action = PingAction
