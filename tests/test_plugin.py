"""Plugin boundary tests with explicit SDK doubles; not an AstrBot deployment test."""

import importlib.util
import logging
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from test_bridge import ORIGIN, config


def load_plugin(data_dir):
    class Star:
        def __init__(self, context):
            self.context = context

    class Chain:
        def message(self, text):
            self.text = text
            return self

    class Message:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    class Filters:
        PermissionType = types.SimpleNamespace(ADMIN="admin")
        EventMessageType = types.SimpleNamespace(ALL="all")

        @staticmethod
        def command(name):
            return lambda fn: fn

        event_message_type = command

        @staticmethod
        def permission_type(permission):
            def decorate(fn):
                fn.permission = permission
                return fn

            return decorate

    def module(name, **kwargs):
        m = types.ModuleType(name)
        m.__dict__.update(kwargs)
        return m

    root = Path(__file__).resolve().parents[1]
    package = module("tfgm_test_plugin")
    package.__path__ = [str(root)]
    modules = {
        "astrbot": module("astrbot"),
        "astrbot.api": module(
            "astrbot.api", AstrBotConfig=dict, logger=logging.getLogger("plugin-test")
        ),
        "astrbot.api.event": module(
            "astrbot.api.event", AstrMessageEvent=object, MessageChain=Chain, filter=Filters
        ),
        "astrbot.api.star": module(
            "astrbot.api.star",
            Context=object,
            Star=Star,
            StarTools=types.SimpleNamespace(get_data_dir=lambda _: data_dir),
            register=lambda *a: lambda cls: cls,
        ),
        "astrbot.core": module("astrbot.core"),
        "astrbot.core.agent": module("astrbot.core.agent"),
        "astrbot.core.agent.message": module("astrbot.core.agent.message", Message=Message),
        "tfgm_test_plugin": package,
    }
    with patch.dict(sys.modules, modules):
        spec = importlib.util.spec_from_file_location("tfgm_test_plugin.main", root / "main.py")
        loaded = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(loaded)
    return loaded.TFGMPlugin


class Event:
    def __init__(self, text="你好", sender="111", platform="aiocqhttp", group="12345"):
        self.message_str, self.sender, self.platform, self.group = text, sender, platform, group
        self.message_obj = types.SimpleNamespace(
            message_id="42", raw_message={"post_type": "message", "sender": {"card": "群名片"}}
        )
        self.stopped = False

    def get_platform_name(self):
        return self.platform

    def get_platform_id(self):
        return "qq-main"

    def get_group_id(self):
        return self.group

    def get_sender_id(self):
        return self.sender

    def get_self_id(self):
        return "999"

    def get_sender_name(self):
        return "昵称"

    def get_messages(self):
        return [type("Plain", (), {"text": self.message_str})()]

    def plain_result(self, text):
        return text

    def stop_event(self):
        self.stopped = True


class PluginTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.cls = load_plugin(Path(self.temp.name))
        self.context = types.SimpleNamespace(
            send_message=AsyncMock(return_value=True),
            get_current_chat_provider_id=AsyncMock(return_value="default-model"),
            llm_generate=AsyncMock(return_value=types.SimpleNamespace(completion_text="回答")),
            persona_manager=types.SimpleNamespace(
                get_persona=AsyncMock(return_value=types.SimpleNamespace(system_prompt="人格"))
            ),
        )
        self.plugin = self.cls(self.context, {})
        await self.plugin.initialize()

    async def asyncTearDown(self):
        await self.plugin.terminate()
        self.temp.cleanup()

    async def test_legacy_command_and_admin_diagnostics(self):
        e = Event("查服")
        result = [r async for r in self.plugin.query_server(e)]
        self.assertEqual(result, ["群峦格雷欢迎你"])
        self.assertTrue(e.stopped)
        self.assertEqual(self.cls.status.permission, "admin")
        self.assertEqual(self.cls.origin.permission, "admin")
        self.assertEqual([r async for r in self.plugin.origin(Event())], [ORIGIN])

    async def test_qq_input_uses_group_identity_and_ignores_self_private_and_other_platforms(self):
        settings = config()
        self.plugin.engine.settings = settings
        self.plugin.engine.route_map = {r["id"]: r for r in settings.routes}
        for e in (Event(sender="999"), Event(group=""), Event(platform="telegram"), Event()):
            self.assertEqual([r async for r in self.plugin.query_server(e)], [])
        rows = list(self.plugin.engine.store.db.execute("SELECT payload FROM jobs"))
        self.assertEqual(len(rows), 1)
        self.assertIn("群名片", rows[0][0])

    async def test_generate_provider_persona_and_context_types(self):
        ai = config().ai
        ai["persona_id"] = "persona"
        answer = await self.plugin.generate("问题", [{"role": "user", "content": "之前"}], ai)
        self.assertEqual(answer, "回答")
        kwargs = self.context.llm_generate.call_args.kwargs
        self.assertEqual(kwargs["chat_provider_id"], "default-model")
        self.assertTrue(kwargs["system_prompt"].startswith("人格\n\n"))
        self.assertEqual(kwargs["contexts"][0].content, "之前")
        self.assertNotIn("tools", kwargs)

    async def test_plain_qq_output_and_lifecycle_reload(self):
        self.assertTrue(await self.plugin.send_qq(ORIGIN, "[CQ:at,qq=all]"))
        self.assertEqual(self.context.send_message.call_args.args[1].text, "[CQ:at,qq=all]")
        old = self.plugin.engine
        await self.plugin.initialize()
        self.assertTrue(old.stopping)
        self.assertIsNot(old, self.plugin.engine)
        await self.plugin.terminate()
        self.assertIsNone(self.plugin.engine)

    async def test_configuration_error_does_not_break_existing_commands(self):
        self.plugin.config = {"ai": {"prefix": ""}}
        await self.plugin.initialize()
        self.assertIsNone(self.plugin.engine)
        self.assertIn("不能为空", self.plugin.start_error)
        self.assertIn("TerraFirmaGreg", [r async for r in self.plugin.tfgm(Event())][0])
