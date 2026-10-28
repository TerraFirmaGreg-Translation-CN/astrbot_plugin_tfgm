import asyncio
import json
import logging
import tempfile
import time
import unittest
from pathlib import Path

import aiohttp
from aiohttp import web
from aiohttp.test_utils import TestServer

from bridge.config import Settings, schema
from bridge.engine import Engine
from bridge.messages import chunks, flatten
from bridge.sidecar import Sidecar, SidecarError
from bridge.store import Store

PLAYER = "00000000-0000-0000-0000-000000000001"
OTHER = "00000000-0000-0000-0000-000000000002"
ORIGIN = "qq-main:GroupMessage:12345"


def config(**overrides):
    raw = {
        "enabled": True,
        "servers": [
            {"id": "survival", "message_token": "send-secret", "read_token": "read-secret"}
        ],
        "routes": [{"id": "main", "server_id": "survival", "qq_origin": ORIGIN}],
        "delivery": {"interval_seconds": 0},
    }
    raw.update(overrides)
    return Settings(raw)


def event(seq=1, text="大家好", player=PLAYER):
    return {
        "seq": seq,
        "type": "player_chat",
        "timestampMs": int(time.time() * 1000),
        "uuid": player,
        "name": "Steve",
        "data": {"message": text},
    }


class FakeSidecar:
    def __init__(self):
        self.instance = "boot-a"
        self.records = []
        self.sent = []
        self.processing = False
        self.delivered = 1
        self.fail = None
        self.enabled = True
        self.calls = []

    async def health(self):
        return {
            "api_version": 1,
            "mod_version": "0.13.15.2",
            "instance_id": self.instance,
            "last_event_seq": self.records[-1]["seq"] if self.records else 0,
            "messages": {"enabled": self.enabled},
        }

    async def events(self, since, limit):
        self.calls.append(since)
        data = [e for e in self.records if e["seq"] > since]
        return {
            "instance_id": self.instance,
            "events": data[:limit],
            "truncated": len(data) > limit,
            "last_seq": self.records[-1]["seq"] if self.records else 0,
        }

    async def send(self, body):
        self.sent.append(body)
        if self.fail:
            raise self.fail
        return {
            "request_id": body["request_id"],
            "instance_id": self.instance,
            "status": "processing" if self.processing else "completed",
            "delivered_count": self.delivered,
        }


class ConfigTests(unittest.TestCase):
    def test_defaults_and_committed_schema_match(self):
        self.assertFalse(Settings({}).enabled)
        self.assertEqual(schema(), json.loads(Path("_conf_schema.json").read_text()))

    def test_reject_unsafe_or_duplicate_configuration(self):
        variants = [
            {
                "servers": [
                    {"id": "s", "url": "http://user:secret@example.com", "message_token": "secret"}
                ]
            },
            {"servers": [{"id": "s", "read_token": "same", "message_token": "same"}]},
            {"routes": [{"id": "r", "server_id": "missing", "qq_origin": ORIGIN}]},
            {"routes": [{"id": "r", "server_id": "survival", "qq_origin": "123"}]},
            {
                "routes": [
                    {
                        "id": "r",
                        "server_id": "survival",
                        "qq_origin": ORIGIN,
                        "mc_template": "{message.__class__}",
                    }
                ]
            },
            {"ai": {"prefix": " "}},
            {"connection": {"poll_seconds": 0}},
        ]
        for variant in variants:
            with self.subTest(variant=variant), self.assertRaises(ValueError):
                config(**variant)

    def test_literal_cq_and_component_downgrade(self):
        def component(kind, **kw):
            return type(kind, (), kw)()

        text = flatten(
            [
                component("Plain", text="[CQ:at,qq=all] §c你好"),
                component("At", name="小明", qq="1"),
                component("Image", url="file:///secret"),
                component("Reply", message_str="abcdef"),
            ],
            "link",
            3,
        )
        self.assertEqual(text, "[CQ:at,qq=all] 你好@小明[图片][引用：abc] ")
        parts = chunks("字" * 700, 100, 2)
        self.assertEqual(len(parts), 2)
        self.assertTrue(parts[-1].endswith("…[截断]"))
        self.assertLessEqual(len(parts[-1]), 100)


class EngineTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.sent = []
        self.generations = []
        self.settings = config(
            connection={"initial_history": True, "batch_size": 1},
            ai={"enabled": True, "cooldown_seconds": 0, "show_thinking": False},
        )
        self.engine = Engine(
            self.settings,
            Path(self.temp.name) / "state.db",
            self.send,
            self.generate,
            logging.getLogger("test"),
        )
        self.fake = FakeSidecar()
        self.engine.clients["survival"] = self.fake

    async def send(self, origin, text):
        self.sent.append((origin, text))
        return True

    async def generate(self, prompt, history, ai):
        self.generations.append((prompt, list(history)))
        return "回答：" + prompt

    async def asyncTearDown(self):
        await self.engine.stop()
        self.temp.cleanup()

    def jobs(self, kind=None):
        sql = "SELECT * FROM jobs" + (" WHERE kind=?" if kind else "")
        return [dict(r) for r in self.engine.store.db.execute(sql, (kind,) if kind else ())]

    async def drain(self, target):
        while job := self.engine.store.claim(target):
            await self.engine.process(job)

    async def test_cursor_paging_dedup_and_restart_instance(self):
        self.fake.records = [event(1), event(2)]
        self.assertTrue(await self.engine.poll_once("survival"))
        self.assertEqual(self.engine.store.cursor("survival", "http://127.0.0.1:8765")["seq"], 1)
        await self.engine.poll_once("survival")
        await self.engine.poll_once("survival")
        self.assertEqual(len(self.jobs("qq")), 2)
        self.fake.instance = "boot-b"
        self.fake.records = [event(1, "重启后")]
        await self.engine.poll_once("survival")
        self.assertEqual(len(self.jobs("qq")), 3)
        await self.drain("qq:" + ORIGIN)
        self.assertEqual(len(self.sent), 3)

    async def test_initial_tail_skips_old_chat(self):
        self.settings.connection["initial_history"] = False
        self.fake.records = [event(1)]
        await self.engine.poll_once("survival")
        self.assertEqual(len(self.jobs()), 0)
        self.fake.records.append(event(2))
        await self.engine.poll_once("survival")
        self.assertEqual(len(self.jobs("qq")), 1)

    async def test_cursor_and_outbox_rollback_together(self):
        self.fake.records = [event(1), event(1)]
        self.settings.connection["batch_size"] = 200
        with self.assertRaises(SidecarError):
            await self.engine.poll_once("survival")
        self.assertEqual(len(self.jobs()), 0)
        self.assertEqual(self.engine.store.cursor("survival", "http://127.0.0.1:8765")["seq"], 0)

    async def test_qq_route_isolation_and_duplicate_input(self):
        for origin in ("other:GroupMessage:12345", ORIGIN, ORIGIN):
            self.engine.on_qq(origin, "1", "user", "Nick", lambda r: "你好")
        self.assertEqual(len(self.jobs("mc")), 1)
        await self.drain("mc:survival")
        self.assertEqual(
            self.fake.sent[0]["message"], {"text": "[QQ群] Nick：你好", "color": "white"}
        )
        self.assertEqual(self.fake.sent[0]["target"], {"type": "all"})

    async def test_prefix_filters_and_permissions(self):
        route = self.settings.routes[0]
        route.update(qq_mode="prefix", allowed_qq=["yes"])
        for sender, text in [("no", "#mc hi"), ("yes", "hi"), ("yes", "#mc hi")]:
            self.engine.on_qq(ORIGIN, text + sender, sender, sender, lambda r: text)
        self.assertEqual(len(self.jobs()), 1)
        await self.drain("mc:survival")
        self.assertTrue(self.fake.sent[0]["message"]["text"].endswith("hi"))
        self.assertNotIn("#mc", self.fake.sent[0]["message"]["text"])

    async def test_processing_reuses_id_and_payload(self):
        self.engine.on_qq(ORIGIN, "1", "u", "n", lambda r: "hi")
        job = self.engine.store.claim("mc:survival")
        self.fake.processing = True
        await self.engine.process(job)
        self.assertEqual(self.jobs()[0]["status"], "pending")
        self.engine.store.db.execute("UPDATE jobs SET next_at=0")
        self.engine.store.db.commit()
        self.fake.processing = False
        await self.drain("mc:survival")
        self.assertEqual(self.fake.sent[0], self.fake.sent[1])
        self.assertEqual(self.jobs()[0]["status"], "done")

    async def test_ambiguous_send_not_replayed_after_server_restart(self):
        self.engine.on_qq(ORIGIN, "1", "u", "n", lambda r: "hi")
        self.fake.fail = SidecarError("network_error", retry=True, ambiguous=True)
        await self.engine.process(self.engine.store.claim("mc:survival"))
        self.fake.instance = "boot-new"
        self.engine.store.db.execute("UPDATE jobs SET next_at=0")
        self.engine.store.db.commit()
        self.fake.fail = None
        await self.drain("mc:survival")
        self.assertEqual(len(self.fake.sent), 1)
        self.assertEqual(self.jobs()[0]["error"], "instance_changed_ambiguous")

    async def test_zero_recipients_not_success(self):
        self.engine.on_qq(ORIGIN, "1", "u", "n", lambda r: "hi")
        self.fake.delivered = 0
        await self.drain("mc:survival")
        self.assertEqual(self.jobs()[0]["error"], "no_online_recipients")

    async def test_changed_route_drops_queued_message(self):
        self.engine.on_qq(ORIGIN, "1", "u", "n", lambda r: "hi")
        self.settings.routes[0]["qq_origin"] = "qq:GroupMessage:99"
        await self.drain("mc:survival")
        self.assertEqual(self.fake.sent, [])
        self.assertEqual(self.jobs()[0]["error"], "configuration_changed")

    async def test_qq_failure_not_retried_ambiguously(self):
        async def fail(origin, text):
            raise TimeoutError("secret must not be logged")

        self.engine.send_qq = fail
        self.fake.records = [event()]
        await self.engine.poll_once("survival")
        await self.drain("qq:" + ORIGIN)
        self.assertEqual(self.jobs()[0]["status"], "failed")
        self.assertNotIn("secret", self.engine.status())

    async def test_ai_private_reply_and_player_history_isolation(self):
        for seq, player in [(1, PLAYER), (2, OTHER), (3, PLAYER)]:
            self.fake.records.append(event(seq, "@小助手 问题", player))
            await self.engine.poll_once("survival")
            await self.drain("ai:survival")
            await self.drain("mc:survival")
        self.assertEqual(len(self.generations[0][1]), 0)
        self.assertEqual(len(self.generations[1][1]), 0)
        self.assertEqual(len(self.generations[2][1]), 2)
        self.assertEqual(self.fake.sent[1]["target"], {"type": "players", "uuids": [OTHER]})
        self.assertEqual(self.sent, [])
        self.assertEqual(len(self.jobs("qq")), 0)

    async def test_ai_reset_and_busy_player(self):
        self.fake.records = [event(1, "@小助手 第一个"), event(2, "@小助手 第二个")]
        await self.engine.poll_once("survival")
        await self.engine.poll_once("survival")
        self.assertEqual(len(self.jobs("ai")), 1)
        await self.drain("ai:survival")
        self.fake.records.append(event(3, "@小助手 重置对话"))
        await self.engine.poll_once("survival")
        await self.drain("ai:survival")
        self.assertEqual(len(self.generations), 1)
        self.assertEqual(self.engine.store.history("survival:" + PLAYER, 24), [])

    async def test_ai_error_is_private_and_redacted(self):
        async def fail(*args):
            raise RuntimeError("API token secret")

        self.engine.generate = fail
        self.fake.records = [event(1, "@小助手 问题")]
        await self.engine.poll_once("survival")
        await self.drain("ai:survival")
        await self.drain("mc:survival")
        self.assertNotIn("secret", str(self.fake.sent))
        self.assertEqual(self.fake.sent[0]["target"]["uuids"], [PLAYER])
        self.assertEqual(self.engine.store.history("survival:" + PLAYER, 24), [])

    async def test_queue_bound_expiry_and_gap(self):
        self.settings.delivery["queue_capacity"] = 1
        self.fake.records = [event(5), event(6)]
        await self.engine.poll_once("survival")
        await self.engine.poll_once("survival")
        self.assertEqual(len(self.jobs("qq")), 1)
        self.assertEqual(self.engine.store.summary()["counters"]["event_gap"], 4)
        self.assertEqual(self.engine.store.summary()["counters"]["queue_full"], 1)
        self.engine.store.db.execute("UPDATE jobs SET expires=0")
        self.engine.store.db.commit()
        await self.drain("qq:" + ORIGIN)
        self.assertEqual(self.sent, [])


class StoreTests(unittest.TestCase):
    def test_restart_recovers_only_idempotent_mc_requests(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.db"
            store = Store(path)
            with store.db:
                for kind in ("qq", "mc", "ai"):
                    store.enqueue(kind, kind, kind, {}, 120, 10)
            for kind in ("qq", "mc", "ai"):
                store.claim(kind)
            store.close()
            store = Store(path)
            statuses = dict(store.db.execute("SELECT kind,status FROM jobs"))
            self.assertEqual(statuses, {"qq": "failed", "mc": "pending", "ai": "failed"})
            store.close()


class HttpTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.received = []
        self.status = 200
        self.redirect = False
        self.stream = False

        async def handler(request):
            self.received.append(
                (request.method, request.path, request.headers.get("Authorization"))
            )
            if self.redirect:
                raise web.HTTPFound("/other")
            if request.method == "POST":
                body = await request.json()
                return web.json_response(
                    {
                        "request_id": body["request_id"],
                        "instance_id": "boot",
                        "status": "processing" if self.status == 202 else "completed",
                        "delivered_count": 1,
                    },
                    status=self.status,
                )
            data = {
                "api_version": 1,
                "mod_version": "0.13.15.2",
                "instance_id": "boot",
                "messages": {"enabled": True},
                "last_event_seq": 0,
            }
            if self.stream:
                response = web.StreamResponse(headers={"Content-Type": "application/json"})
                await response.prepare(request)
                encoded = json.dumps(data).encode()
                await response.write(encoded[:10])
                await asyncio.sleep(0.01)
                await response.write(encoded[10:])
                await response.write_eof()
                return response
            return web.json_response(data)

        app = web.Application()
        app.router.add_route("*", "/api/v1/{path}", handler)
        self.server = TestServer(app)
        await self.server.start_server()
        self.session = aiohttp.ClientSession()
        self.client = Sidecar(
            self.session,
            {"url": str(self.server.make_url("")), "read_token": "read", "message_token": "write"},
            5,
        )

    async def asyncTearDown(self):
        await self.session.close()
        await self.server.close()

    async def test_separate_tokens_and_processing(self):
        await self.client.health()
        self.status = 202
        response = await self.client.send({"request_id": "id", "message": "hi"})
        self.assertEqual(response["status"], "processing")
        self.assertEqual([r[2] for r in self.received], ["Bearer read", "Bearer write"])

    async def test_redirect_is_rejected(self):
        self.redirect = True
        with self.assertRaisesRegex(SidecarError, "http_302"):
            await self.client.health()
        self.assertEqual(len(self.received), 1)

    async def test_streamed_json_is_read_completely(self):
        self.stream = True
        self.assertEqual((await self.client.health())["instance_id"], "boot")


class RuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_http_poll_workers_ai_and_shutdown(self):
        records, received, qq_sent, model_calls = [], [], [], []

        async def health(request):
            self.assertEqual(request.headers.get("Authorization"), "Bearer read-secret")
            return web.json_response(
                {
                    "api_version": 1,
                    "mod_version": "0.13.15.2",
                    "instance_id": "boot",
                    "last_event_seq": records[-1]["seq"] if records else 0,
                    "messages": {"enabled": True},
                }
            )

        async def events(request):
            since = int(request.query["since_seq"])
            return web.json_response(
                {
                    "instance_id": "boot",
                    "truncated": False,
                    "events": [r for r in records if r["seq"] > since],
                }
            )

        async def messages(request):
            self.assertEqual(request.headers.get("Authorization"), "Bearer send-secret")
            body = await request.json()
            received.append(body)
            return web.json_response(
                {
                    "request_id": body["request_id"],
                    "instance_id": "boot",
                    "status": "completed",
                    "delivered_count": 1,
                }
            )

        async def send(origin, text):
            qq_sent.append((origin, text))
            return True

        async def generate(prompt, history, ai):
            model_calls.append(prompt)
            await asyncio.sleep(0.05)
            return "测试回答"

        app = web.Application()
        app.router.add_get("/api/v1/health", health)
        app.router.add_get("/api/v1/events", events)
        app.router.add_post("/api/v1/messages", messages)
        async with TestServer(app) as server:
            with tempfile.TemporaryDirectory() as tmp:
                settings = config(
                    connection={"poll_seconds": 0.2, "initial_history": True},
                    ai={"enabled": True, "show_thinking": False},
                )
                settings.servers["survival"]["url"] = str(server.make_url(""))
                engine = Engine(
                    settings, Path(tmp) / "state.db", send, generate, logging.getLogger("runtime")
                )
                try:
                    records.extend([event(1), event(2, "@小助手 你好")])
                    await engine.start()
                    engine.on_qq(ORIGIN, "q1", "123", "Nick", lambda r: "QQ问候")

                    async def completed():
                        while len(received) < 2 or not qq_sent:
                            await asyncio.sleep(0.02)

                    await asyncio.wait_for(completed(), 5)
                    self.assertEqual(len(qq_sent), 1)
                    self.assertEqual(model_calls, ["你好"])
                    self.assertEqual(len(received), 2)
                    self.assertTrue(any(r["target"].get("uuids") == [PLAYER] for r in received))
                finally:
                    await engine.stop()
                self.assertTrue(all(task.done() for task in engine.tasks))
                self.assertTrue(engine.session.closed)
