import json
import os
import uuid
import asyncio
from typing import MutableMapping
from aio_pika import Message, connect
from aio_pika.abc import (
    AbstractChannel,
    AbstractConnection,
    AbstractIncomingMessage,
    AbstractQueue,
)


class FibonacciRpcClient:
    connection: AbstractConnection
    channel: AbstractChannel
    callback_queue: AbstractQueue
    loop: asyncio.AbstractEventLoop

    def __init__(self) -> None:
        self.futures: MutableMapping[str, asyncio.Future] = {}
        self.loop = asyncio.get_running_loop()

    async def connect(self) -> "FibonacciRpcClient":
        host = os.getenv("RABBITMQ_HOST", "localhost")
        user = os.getenv("RABBITMQ_USER", "services")
        password = os.getenv("RABBITMQ_PASS", "longpassword")
        url = f"amqp://{user}:{password}@{host}/"
        self.connection = await connect(
            url,
            loop=self.loop,
        )
        self.channel = await self.connection.channel()
        self.callback_queue = await self.channel.declare_queue(exclusive=True)
        await self.callback_queue.consume(self.on_response)

        return self

    def on_response(self, message: AbstractIncomingMessage) -> None:
        if message.correlation_id is None:
            print(f"Bad message {message!r}")
            return

        future: asyncio.Future = self.futures.pop(message.correlation_id)
        future.set_result(message.body)

    async def rpc_send(self, channel, msg) -> int:
        correlation_id = str(uuid.uuid4())
        future = self.loop.create_future()

        self.futures[correlation_id] = future

        await self.channel.default_exchange.publish(
            Message(
                json.dumps(msg).encode(),
                content_type="text/plain",
                correlation_id=correlation_id,
                reply_to=self.callback_queue.name,
            ),
            routing_key=channel,
        )

        return json.loads(await future)


# class RunnerTask(object):
#     async def __init__(self):
#         self.connection = await pika.BlockingConnection(
#             pika.ConnectionParameters(
#                 host=os.getenv("RABBITMQ_HOST", "localhost"),
#                 credentials=pika.PlainCredentials(
#                     os.getenv("RABBITMQ_USER", "services"),
#                     os.getenv("RABBITMQ_PASS", "longpassword"),
#                 ),
#             )
#         )

#         self.channel = await self.connection.channel()
#         result = await self.channel.queue_declare(queue="", exclusive=True)
#         self.callback_queue = result.method.queue

#         self.channel.basic_consume(
#             queue=self.callback_queue,
#             on_message_callback=self.on_response,
#             auto_ack=True,
#         )

#         self.response = None
#         self.corr_id = None

#     async def on_response(self, ch, method, props, body):
#         if self.corr_id == props.correlation_id:
#             self.response = body

#     def send(self, channel, mes):
#         self.channel.basic_publish(exchange="", routing_key=channel, body=mes)

#     async def rpc_send(self, channel, mes):
#         self.response = None
#         self.corr_id = str(uuid.uuid4())
#         await self.channel.basic_publish(
#             exchange="",
#             routing_key=channel,
#             properties=pika.BasicProperties(
#                 reply_to=self.callback_queue,
#                 correlation_id=self.corr_id,
#             ),
#             body=json.dumps(mes),
#         )
#         self.connection.process_data_events(time_limit=None)
#         return json.loads(self.response)
