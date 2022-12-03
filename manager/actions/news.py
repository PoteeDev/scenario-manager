from actions._base import ActionBase
from dataclasses import dataclass


@dataclass
class News:
    round: int
    text: str


class NewsAction(ActionBase):
    async def __call__(self, scenario: dict, round: int):
        # await asyncio.sleep(0)
        rpc = await self.connect()
        for news in scenario["news"]:
            print("news round", news.get("round"), round)
            if news.get("round") == round:
                request = {
                    "recipient": str(scenario.get("news_chat_id")),
                    "message": news.get("text"),
                    "mode": news.get("mode"),
                }
                await rpc.send("sender", request)

action = NewsAction
