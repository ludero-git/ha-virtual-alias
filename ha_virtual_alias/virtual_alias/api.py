import asyncio
import json
import os

import aiohttp
import websockets

from .const import REST_API_URL, WS_API_URL

SUPERVISOR_TOKEN = os.environ["SUPERVISOR_TOKEN"]


class RestAPI:
    def __init__(self):
        self.session = None

    def _get_session(self):
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(
                headers={
                    "Authorization": f"Bearer {SUPERVISOR_TOKEN}",
                }
            )

        return self.session

    async def request(self, method, path, **kwargs):
        session = self._get_session()

        url = f"{REST_API_URL}/{path.lstrip('/')}"

        async with session.request(method, url, **kwargs) as response:
            response.raise_for_status()

            data = await response.json()
            return data.get("data", data)

    async def get(self, path, **kwargs):
        return await self.request("GET", path, **kwargs)

    async def post(self, path, **kwargs):
        return await self.request("POST", path, **kwargs)

    async def close(self):
        if self.session is not None:
            await self.session.close()
            self.session = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.close()


class WebsocketAPI:
    def __init__(self):
        self.ws = None
        self.id = 0
        self.subscriptions = {}
        self.listener_task = None

    async def connect(self):
        self.ws = await websockets.connect(WS_API_URL)

        message = json.loads(await self.ws.recv())

        if message.get("type") != "auth_required":
            raise RuntimeError(f"Expected auth_required, got {message.get('type')!r}")

        await self.ws.send(
            json.dumps(
                {
                    "type": "auth",
                    "access_token": SUPERVISOR_TOKEN,
                }
            )
        )

        auth = json.loads(await self.ws.recv())

        if auth.get("type") != "auth_ok":
            await self.ws.close()
            self.ws = None
            raise RuntimeError(f"Authentication failed: {auth}")

        self.listener_task = asyncio.create_task(self._listen())

    async def _listen(self):
        try:
            async for raw_message in self.ws:
                msg = json.loads(raw_message)

                if msg.get("type") != "event":
                    continue

                callback = self.subscriptions.get(msg.get("id"))
                if not callback:
                    continue

                result = callback(msg["event"])

                # Support both async and regular callbacks.
                if asyncio.iscoroutine(result):
                    await result

        except asyncio.CancelledError:
            raise

        except websockets.ConnectionClosed:
            pass

    async def subscribe(self, payload, callback):
        if self.ws is None:
            raise RuntimeError("Websocket API is not connected")

        self.id += 1
        subscription_id = self.id

        self.subscriptions[subscription_id] = callback

        await self.ws.send(
            json.dumps(
                {
                    "id": subscription_id,
                    **payload,
                }
            )
        )

        return subscription_id

    async def unsubscribe(self, subscription_id):
        if self.ws is None:
            raise RuntimeError("Websocket API is not connected")

        await self.ws.send(
            json.dumps(
                {
                    "id": self._next_id(),
                    "type": "unsubscribe_events",
                    "subscription": subscription_id,
                }
            )
        )

        self.subscriptions.pop(subscription_id, None)

    def _next_id(self):
        self.id += 1
        return self.id

    async def close(self):
        if self.listener_task:
            self.listener_task.cancel()

            try:
                await self.listener_task
            except asyncio.CancelledError:
                pass

            self.listener_task = None

        if self.ws:
            await self.ws.close()
            self.ws = None

        self.subscriptions.clear()

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.close()
