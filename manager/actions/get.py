from dataclasses import dataclass
from actions._base import BaseAction, Action
from flags import FlagStorage
import os


@dataclass
class GetAction(BaseAction):
    def send(self, checkers):
        for checker in checkers:
            uniq_value = FlagStorage().get_uniq(self.id, self.srv, checker)
            request = {
                **self.__dict__,
                "extra": checker,
                "args": ["get", f"{self.srv}.{self._domain}", checker, uniq_value],
            }
            yield request

    def receive(self, response: Action):
        if (
            FlagStorage().validate(
                response.entity,
                response.srv,
                response.extra,
                response.answer,
            )
            or response.round == 0
        ):
            return {response.extra: 1}
        return {response.extra: 0}


action = GetAction
