from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, MessageChain, filter
from astrbot.api.star import Context, Star, StarTools, register
from astrbot.core.agent.message import Message

from .bridge.config import Settings
from .bridge.engine import Engine
from .bridge.messages import flatten


@register(
    "astrbot_plugin_tfgm",
    "TerraFirmaGreg-Translation-CN",
    "TFGM Sidecar 群服互通与游戏内 AI 对话",
    "0.3.0",
)
class TFGMPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self.engine = None
        self.start_error = ""

    async def initialize(self):
        if self.engine:
            await self.engine.stop()
            self.engine = None
        self.start_error = ""
        try:
            settings = Settings(dict(self.config))
        except ValueError as e:
            self.start_error = str(e)
            logger.error("TFGM 配置无效：%s", self.start_error)
            return
        self.engine = Engine(
            settings,
            StarTools.get_data_dir("astrbot_plugin_tfgm") / "bridge.sqlite3",
            self.send_qq,
            self.generate,
            logger,
        )
        await self.engine.start()

    async def terminate(self):
        if self.engine:
            await self.engine.stop()
            self.engine = None

    async def send_qq(self, origin, text):
        # MessageChain Plain preserves literal [CQ:...] as text.
        return await self.context.send_message(origin, MessageChain().message(text))

    async def generate(self, prompt, history, ai):
        provider = ai["provider_id"] or await self.context.get_current_chat_provider_id(
            umo="tfgm:FriendMessage:default"
        )
        system = ai["system_prompt"]
        if ai["persona_id"]:
            persona = await self.context.persona_manager.get_persona(ai["persona_id"])
            system = (persona.system_prompt or "") + "\n\n" + system
        contexts = [Message(**entry) for entry in history]
        response = await self.context.llm_generate(
            chat_provider_id=provider, prompt=prompt, contexts=contexts, system_prompt=system
        )
        return response.completion_text

    @filter.command("tfgm")
    async def tfgm(self, event: AstrMessageEvent):
        """查看社区地址与插件使用说明。"""
        yield event.plain_result(
            "TerraFirmaGreg 中文社区\nhttps://github.com/TerraFirmaGreg-Translation-CN\n"
            "管理员：/tfgm_origin 获取群会话标识；/tfgm_status 查看互通状态。"
        )

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("tfgm_origin")
    async def origin(self, event: AstrMessageEvent):
        """获取当前 QQ 群会话标识，用于 WebUI 路由配置。"""
        if event.get_platform_name() != "aiocqhttp" or not event.get_group_id():
            yield event.plain_result("请在已连接 OneBot 的 QQ 群内执行。")
            return
        # AstrBot may isolate member sessions. Routing always identifies the whole group.
        yield event.plain_result(f"{event.get_platform_id()}:GroupMessage:{event.get_group_id()}")

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("tfgm_status")
    async def status(self, event: AstrMessageEvent):
        """查看连接、队列及错误代码，不显示令牌或聊天正文。"""
        yield event.plain_result(
            self.engine.status()
            if self.engine
            else "TFGM 未启动：" + (self.start_error or "正在初始化")
        )

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def query_server(self, event: AstrMessageEvent):
        """保留查服指令，同时监听已配置 QQ 群的玩家消息。"""
        if event.message_str.strip() == "查服":
            yield event.plain_result("群峦格雷欢迎你")
            event.stop_event()
            return
        if not self.engine or event.get_platform_name() != "aiocqhttp" or not event.get_group_id():
            return
        sender = event.get_sender_id()
        if not sender or sender == event.get_self_id():
            return
        raw = getattr(event.message_obj, "raw_message", None)
        if isinstance(raw, dict) and raw.get("post_type") != "message":
            return
        message_id = str(getattr(event.message_obj, "message_id", "") or "")
        if not message_id:
            return
        nickname = event.get_sender_name() or sender
        if raw and hasattr(raw, "get"):
            nickname = (raw.get("sender", {}) or {}).get("card") or nickname
        origin = f"{event.get_platform_id()}:GroupMessage:{event.get_group_id()}"
        self.engine.on_qq(
            origin,
            message_id,
            sender,
            nickname,
            lambda route: flatten(event.get_messages(), route["image_mode"], route["quote_chars"]),
        )
