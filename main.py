from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register


@register(
    "astrbot_plugin_tfgm",
    "TerraFirmaGreg-Translation-CN",
    "TerraFirmaGreg 中文社区 AstrBot 插件",
    "0.1.1",
)
class TFGMPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)

    @filter.command("tfgm")
    async def tfgm(self, event: AstrMessageEvent):
        """查看 TerraFirmaGreg 中文社区信息。"""
        yield event.plain_result(
            "TerraFirmaGreg 中文社区\nhttps://github.com/TerraFirmaGreg-Translation-CN"
        )

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def query_server(self, event: AstrMessageEvent):
        """收到“查服”时回复固定欢迎语，无需唤醒前缀。"""
        if event.message_str.strip() != "查服":
            return
        yield event.plain_result("群峦格雷欢迎你")
        event.stop_event()
