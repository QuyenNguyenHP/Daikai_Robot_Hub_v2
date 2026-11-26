import asyncio
import threading
import unittest
from types import SimpleNamespace

from fastapi import WebSocketDisconnect
from backend.main import robot_mode_websocket


class ModeWebsocketTests(unittest.IsolatedAsyncioTestCase):
    async def test_robot_timeout_does_not_block_network_event_loop(self):
        release = threading.Event()
        observations = []
        loop_thread = threading.get_ident()

        def mode():
            observations.append(threading.get_ident())
            observations.append(release.wait(1))
            return {"fsm_id": 811}

        class Socket:
            app = SimpleNamespace(state=SimpleNamespace(robot_control=SimpleNamespace(mode=mode)))

            async def accept(self):
                pass

            async def send_json(self, payload):
                self.payload = payload
                raise WebSocketDisconnect()

        socket = Socket()

        async def heartbeat():
            await asyncio.sleep(0.05)
            release.set()

        await asyncio.gather(robot_mode_websocket(socket), heartbeat())
        self.assertNotEqual(observations[0], loop_thread)
        self.assertTrue(observations[1])
        self.assertIsNone(socket.payload["error"])
