import json
from channels.generic.websocket import AsyncWebsocketConsumer


class KeepAliveConsumer(AsyncWebsocketConsumer):

    async def connect(self):
        await self.accept()
        await self.send(text_data=json.dumps({
            "message": "WebSocket connected"
        }))

    async def receive(self, text_data=None, bytes_data=None):
        await self.send(text_data=json.dumps({
            "message": "Connection is active"
        }))
