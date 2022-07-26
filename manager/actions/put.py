from actions._base import ActionBase
from flags import FlagStorage
import random
import string


def generate_flag(n=25):
    return "".join(random.choices(string.ascii_uppercase + string.ascii_lowercase, k=n))


class PutAction(ActionBase):
    async def __call__(self, *args, **kwargs):
        rpc = await self.connect()
        for checker in kwargs["service_info"]["checkers"]:
            result = 0
            if self.read("ping", args[0], args[1]) == 1:
                flag = generate_flag()
                request = {
                    "id": args[0],
                    "srv": args[1],
                    "script": kwargs["service_info"]["script"],
                    "args": ["put", args[2], checker, flag],
                }
                answer = await rpc.rpc_send("runner", request)
                if answer:
                    FlagStorage().put(
                       args[0], 
                       args[1],
                        checker,
                        flag,
                        answer["answer"],
                    )
                    result = 1

            self.write("put", args[0], args[1], checker, result=result)


action = PutAction
