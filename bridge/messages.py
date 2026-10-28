"""Text-only transport: never interpret user-authored CQ or Minecraft components."""

import re
from datetime import datetime
from urllib.parse import urlsplit


def clean(text):
    text = re.sub(r"§.", "", str(text))
    return "".join(c for c in text if c in "\n\t" or (ord(c) >= 32 and ord(c) != 127))


def allowed(identity, allow, deny):
    return identity not in deny and (not allow or identity in allow)


def select_text(text, route, direction):
    if any(text.startswith(p) for p in route["ignored_prefixes"] if p):
        return None
    if route[f"{direction}_mode"] == "prefix":
        prefix = route[f"{direction}_prefix"]
        if not text.startswith(prefix):
            return None
        if route["strip_prefix"]:
            text = text[len(prefix) :]
    return text if text.strip() else None


def format_text(template, server, name, message):
    return template.format(
        server=clean(server),
        player=clean(name),
        nickname=clean(name),
        message=clean(message),
        time=datetime.now().astimezone().strftime("%H:%M"),
    )


def chunks(text, size, limit):
    text = clean(text)
    if len(text) > size * limit:
        text = text[: size * limit - 5] + "…[截断]"
    return [text[i : i + size] for i in range(0, len(text), size) if text[i : i + size].strip()]


def flatten(components, image_mode="placeholder", quote_chars=80):
    out = []
    for c in components:
        kind = type(c).__name__
        if kind == "Plain":
            out.append(str(c.text))
        elif kind == "At":
            out.append("@" + str(getattr(c, "name", None) or c.qq))
        elif kind == "AtAll":
            out.append("@全体成员")
        elif kind == "Image":
            if image_mode != "ignore":
                url = str(getattr(c, "url", "") or "")
                out.append(
                    "[图片]"
                    + (
                        url
                        if image_mode == "link" and urlsplit(url).scheme in {"http", "https"}
                        else ""
                    )
                )
        elif kind == "Reply":
            if quote_chars:
                # No extra network lookups for missing quote content.
                text = str(getattr(c, "message_str", "") or "")
                out.append("[引用" + ("：" + text[:quote_chars] if text else "") + "] ")
        else:
            label = {
                "File": "文件",
                "Record": "语音",
                "Video": "视频",
                "Face": "表情",
                "Forward": "合并转发",
            }.get(kind, "消息")
            name = getattr(c, "name", "") if kind == "File" else ""
            out.append(f"[{label}{'：' + str(name) if name else ''}]")
    return clean("".join(out))
