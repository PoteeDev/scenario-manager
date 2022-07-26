from actions._base import ActionBase
from flags import FlagStorage


flags = FlagStorage()

class GetAction(ActionBase):
    async def __call__(self, *args, **kwargs):
        rpc = await self.connect()
        for checker in kwargs["service_info"]["checkers"]:
            result = 0
            if self.read("ping", args[0], args[1]) == 1:
                # for first round
                if kwargs["round"] == 0:
                    self.write("get", args[0], args[1], checker, result=1)
                    continue

                value = flags.get_uniq(args[0], args[1], checker)
                request = {
                    "id": args[0],
                    "srv": args[1],
                    "script": kwargs["service_info"]["script"],
                    "args": ["get", args[2], checker, value],
                }
                answer = await rpc.rpc_send("runner", request)
                if flags.validate(
                    args[0], 
                    args[1],
                    checker,
                    answer['answer'],
                ):
                    result = 1

            self.write("get", args[0], args[1], checker, result=result)


action = GetAction
