from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register


@register(
    "astrbot_plugin_tfgm",
    "TerraFirmaGreg-Translation-CN",
    "TerraFirmaGreg 中文社区 AstrBot 插件",
    "0.1.0",
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
