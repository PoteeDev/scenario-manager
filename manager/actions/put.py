from dataclasses import dataclass
from actions._base import BaseAction, Action
from flags import FlagStorage
import os
import random
import string


def generate_flag(n=25):
    return "".join(random.choices(string.ascii_uppercase + string.ascii_lowercase, k=n))


@dataclass
class PutAction(BaseAction):
    def send(self, checkers):
        for checker in checkers:
            flag = generate_flag()
            # flag = "321"
            request = {
                **self.__dict__,
                "extra": f"{checker}_{flag}",
                "args": ["put", f"{self.srv}.{self._domain}", checker, flag],
            }
            yield request

    def receive(self, response: Action):
        # TODO: fix bad condition
        if response.extra != "error":
            FlagStorage().put(
                response.entity,
                response.srv,
                *response.extra.split("_"),
                response.answer,
            )
            return {response.extra.split("_")[0]: 1}
        return {response.extra.split("_")[0]: 0}


action = PutAction
