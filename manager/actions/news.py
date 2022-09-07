import os
from actions._base import ActionBase


class NewsAction:
    def send(self, *args):
        request = {
            **self.__dict__,
            "args": ["ping", f"{self.srv}.{self._domain}"],
        }
        yield request


action = NewsAction
