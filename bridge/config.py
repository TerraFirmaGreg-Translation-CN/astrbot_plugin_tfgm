"""Single source of defaults, WebUI schema and runtime validation."""

import copy
import re
from string import Formatter
from urllib.parse import urlsplit


def field(description, default, **kwargs):
    kind = {bool: "bool", int: "int", float: "float", str: "string", list: "list"}[type(default)]
    return {"description": description, "type": kind, "default": default, **kwargs}


def number(description, default, low, high):
    return field(
        description,
        default,
        slider={"min": low, "max": high, "step": 1 if type(default) is int else 0.1},
    )


CONNECTION = {
    "poll_seconds": number("聊天轮询间隔（秒）", 1.0, 0.2, 60),
    "batch_size": number("每页事件数量", 200, 1, 1000),
    "timeout_seconds": number("HTTP 超时（秒）", 5.0, 4, 60),
    "health_seconds": number("健康检查间隔（秒）", 30, 5, 300),
    "retry_seconds": number("最大重连退避（秒）", 30, 1, 300),
    "initial_history": field(
        "首次连接读取历史", False, hint="关闭时从当前游标开始；开启也仅补发有效期内消息。"
    ),
}
DELIVERY = {
    "queue_capacity": number("每目标待投递上限", 200, 1, 2000),
    "ttl_seconds": number("转发有效期（秒）", 120, 10, 300),
    "interval_seconds": number("同一目标发送间隔（秒）", 1.0, 0, 30),
    "chunk_chars": number("单段最大字数", 300, 50, 1000),
    "max_chunks": number("最多分段数", 4, 1, 10),
    "attempts": number("Sidecar 最大发送尝试次数", 3, 1, 10),
    "retention_hours": number("已完成记录保留小时数", 24, 1, 168),
}
AI = {
    "enabled": field("启用游戏内 AI", False),
    "prefix": field("唤醒前缀", "@小助手 "),
    "provider_id": field(
        "聊天模型（留空使用 AstrBot 当前默认模型）", "", _special="select_provider"
    ),
    "persona_id": field("人格（留空只使用下方提示词）", "", _special="select_persona"),
    "system_prompt": field(
        "游戏助手提示词",
        "你是 TerraFirmaGreg 游戏助手。用简洁中文回答；不确定的配方和机制请明确说明，不要编造。",
        type="text",
    ),
    "reply_scope": field(
        "回复范围",
        "player",
        options=["player", "all"],
        hint="仅回复提问者不代表问题私密：输入仍是公共聊天。",
    ),
    "cooldown_seconds": number("同一玩家请求冷却（秒）", 10, 0, 600),
    "concurrency": number("每服 AI 并发数", 2, 1, 8),
    "timeout_seconds": number("AI 请求超时（秒）", 90, 5, 300),
    "history_turns": number("每位玩家保留对话轮数", 10, 0, 50),
    "history_hours": number("对话闲置过期小时数", 24, 1, 168),
    "max_input_chars": number("问题最大字数", 2000, 100, 10000),
    "max_reply_chars": number("回答最大字数", 1200, 100, 10000),
    "show_thinking": field("显示思考中提示", True),
    "thinking_text": field("思考中提示", "[小助手] 思考中……"),
    "reply_prefix": field("回答前缀", "[小助手] "),
    "reset_word": field("重置会话口令（接在唤醒前缀之后）", "重置对话"),
    "forward_questions": field("将 AI 提问同时转发到绑定 QQ 群", False),
    "forward_replies": field("将 AI 回答同时转发到绑定 QQ 群", False),
    "allowed_players": field("允许使用 AI 的 UUID（空为全部）", []),
    "denied_players": field("禁止使用 AI 的 UUID", []),
}
SERVER = {
    "enabled": field("启用服务器", True),
    "id": field(
        "服务器唯一 ID", "", hint="使用字母、数字、下划线或短横线；修改会产生新的游标和会话。"
    ),
    "name": field("服务器显示名称", "生存服"),
    "url": field(
        "Sidecar 基础地址",
        "http://127.0.0.1:8765",
        hint="容器内 localhost 指向容器自身。不要填写 /api/v1。",
    ),
    "read_token": field("Sidecar 读取令牌 http.token", "", secret=True),
    "message_token": field("Sidecar 消息令牌 messages.token", "", secret=True),
    "ai_enabled": field("此服务器 AI 开关", True, hint="还需开启全局 AI 开关。"),
}
ROUTE = {
    "enabled": field("启用路由", True),
    "id": field("路由唯一 ID", ""),
    "server_id": field("对应服务器 ID", ""),
    "qq_origin": field(
        "QQ 群会话标识 UMO",
        "",
        hint="在目标 QQ 群执行 /tfgm_origin 获取；包含平台实例 ID，不能只填群号。",
    ),
    "mc_to_qq": field("游戏 → QQ", True),
    "qq_to_mc": field("QQ → 游戏", True),
    "mc_mode": field("游戏转发模式", "all", options=["all", "prefix"]),
    "qq_mode": field("QQ 转发模式", "all", options=["all", "prefix"]),
    "mc_prefix": field("游戏转发前缀", "#qq "),
    "qq_prefix": field("QQ 转发前缀", "#mc "),
    "strip_prefix": field("移除匹配的转发前缀", True),
    "mc_template": field("游戏 → QQ 格式", "[{server}] {player}：{message}"),
    "qq_template": field("QQ → 游戏格式", "[QQ群] {nickname}：{message}"),
    "mc_color": field(
        "游戏中显示颜色", "white", options=["white", "gray", "aqua", "green", "yellow", "gold"]
    ),
    "image_mode": field("图片处理", "placeholder", options=["placeholder", "link", "ignore"]),
    "quote_chars": number("引用摘要最大字数", 80, 0, 300),
    "ignored_prefixes": field("不转发的命令前缀", ["/tfgm", "tfgm_status", "tfgm_origin"]),
    "ignored_qq": field("忽略的 QQ 号（含其他机器人）", []),
    "allowed_qq": field("允许的 QQ 号（空为全部）", []),
    "denied_players": field("忽略的玩家 UUID", []),
    "allowed_players": field("允许的玩家 UUID（空为全部）", []),
    "join_leave": field("转发玩家加入/退出", False),
    "death": field("转发玩家死亡", False),
}


def group(description, items):
    return {"type": "object", "description": description, "items": items}


def schema():
    def repeated(description, items):
        return {
            "type": "template_list",
            "description": description,
            "default": [],
            "templates": {"default": {"name": description, "items": items}},
        }

    return {
        "enabled": field("启用群服互通与游戏 AI", False),
        "servers": repeated("服务器", SERVER),
        "routes": repeated("群服路由", ROUTE),
        "connection": group("连接与事件读取", CONNECTION),
        "delivery": group("队列与消息投递", DELIVERY),
        "ai": group("游戏内 AI", AI),
    }


def defaults(fields, supplied):
    if not isinstance(supplied, dict):
        raise ValueError("配置分组必须是对象")
    result = {}
    for key, spec in fields.items():
        value = copy.deepcopy(supplied.get(key, spec["default"]))
        kind = spec["type"]
        valid = {
            "bool": type(value) is bool,
            "int": type(value) is int,
            "float": type(value) in (float, int),
            "string": isinstance(value, str),
            "text": isinstance(value, str),
            "list": isinstance(value, list),
        }[kind]
        if not valid:
            raise ValueError(f"{key}: 配置类型错误")
        if "slider" in spec and not spec["slider"]["min"] <= value <= spec["slider"]["max"]:
            raise ValueError(f"{key}: 超出允许范围")
        if "options" in spec and value not in spec["options"]:
            raise ValueError(f"{key}: 无效选项")
        if kind == "list" and any(not isinstance(x, str) for x in value):
            raise ValueError(f"{key}: 列表元素必须是字符串")
        result[key] = value
    return result


def validate_template(template):
    for _, name, fmt, conversion in Formatter().parse(template):
        if name is not None and (
            name not in {"server", "player", "nickname", "message", "time"} or fmt or conversion
        ):
            raise ValueError("模板仅支持 server/player/nickname/message/time 简单占位符")
    if len(template) > 2000:
        raise ValueError("模板过长")


class Settings:
    def __init__(self, raw):
        self.enabled = raw.get("enabled", False)
        if type(self.enabled) is not bool:
            raise ValueError("enabled 必须是布尔值")
        self.connection = defaults(CONNECTION, raw.get("connection", {}))
        self.delivery = defaults(DELIVERY, raw.get("delivery", {}))
        self.ai = defaults(AI, raw.get("ai", {}))
        if not self.ai["prefix"].strip() or not self.ai["reset_word"].strip():
            raise ValueError("AI 唤醒前缀和重置口令不能为空")
        self.servers = {}
        self.routes = []
        ids, bindings = set(), set()
        for entry in raw.get("servers", []):
            s = defaults(SERVER, entry)
            if not s["enabled"]:
                continue
            if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", s["id"]) or s["id"] in self.servers:
                raise ValueError("服务器 ID 无效或重复")
            u = urlsplit(s["url"])
            if (
                u.scheme not in {"http", "https"}
                or not u.hostname
                or u.username
                or u.password
                or u.query
                or u.fragment
                or u.path.rstrip("/")
            ):
                raise ValueError("Sidecar 地址必须是无凭据、无路径的 HTTP(S) 基础地址")
            s["url"] = s["url"].rstrip("/")
            if not s["message_token"] or s["message_token"] == s["read_token"]:
                raise ValueError("消息令牌必须非空且与读取令牌不同")
            self.servers[s["id"]] = s
        for entry in raw.get("routes", []):
            r = defaults(ROUTE, entry)
            if not r["enabled"]:
                continue
            if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", r["id"]) or r["id"] in ids:
                raise ValueError("路由 ID 无效或重复")
            if r["server_id"] not in self.servers:
                raise ValueError("路由引用了未启用的服务器")
            if not re.fullmatch(r"[^:]+:GroupMessage:[0-9]+", r["qq_origin"]):
                raise ValueError("请填写 /tfgm_origin 返回的 QQ 群 UMO")
            binding = (r["server_id"], r["qq_origin"])
            if binding in bindings:
                raise ValueError("同一服务器与群不能重复绑定")
            for direction in ("mc", "qq"):
                validate_template(r[f"{direction}_template"])
                if r[f"{direction}_mode"] == "prefix" and not r[f"{direction}_prefix"].strip():
                    raise ValueError("前缀模式必须填写非空前缀")
            ids.add(r["id"])
            bindings.add(binding)
            self.routes.append(r)
