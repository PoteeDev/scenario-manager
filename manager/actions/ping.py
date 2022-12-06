import os
from actions._base import ActionBase
import asyncio


class PingAction(ActionBase):
    async def __call__(self, *args, **kwargs):
        # await asyncio.sleep(0)
        rpc = await self.connect()
        request = {
            "id": args[0],
            "srv": args[1],
            "script": kwargs["service_info"]["script"],
            "args": ["ping", args[2]],
        }
        answer = await rpc.rpc_send("runner", request)
        result = 0
        if answer["answer"] == "pong":
            result = 1

        self.write("ping", args[0], args[1], result=result)


action = PingAction
