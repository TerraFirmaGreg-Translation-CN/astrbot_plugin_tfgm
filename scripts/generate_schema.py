"""Regenerate the committed AstrBot WebUI schema from runtime defaults."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from bridge.config import schema  # noqa: E402

(ROOT / "_conf_schema.json").write_text(
    json.dumps(schema(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
)

from bridge.config import AI, CONNECTION, DELIVERY, ROUTE, SERVER  # noqa: E402

lines = [
    "# 配置参考",
    "",
    "由 `scripts/generate_schema.py` 从运行默认值生成。所有修改保存后重载插件生效。",
    "",
    "总开关 `enabled` 默认 `false`；`servers`、`routes` 默认空列表。连接、投递、AI 为全局设置；每台服务器有 AI 子开关，每条路由有独立转发规则。",
    "",
]
for title, fields in [
    ("服务器 servers[]", SERVER),
    ("群服路由 routes[]", ROUTE),
    ("连接 connection", CONNECTION),
    ("投递 delivery", DELIVERY),
    ("游戏内 AI ai", AI),
]:
    lines += [
        "## " + title,
        "",
        "| 参数 | 含义 | 默认值 | 选项/范围 |",
        "| --- | --- | --- | --- |",
    ]
    for key, spec in fields.items():
        value = json.dumps(spec["default"], ensure_ascii=False)
        bounds = spec.get("slider")
        options = ", ".join(map(str, spec.get("options", [])))
        if bounds:
            options = f"{bounds['min']}～{bounds['max']}"
        if spec.get("secret"):
            options = "密码输入；与其他令牌分开"
        lines.append(f"| `{key}` | {spec['description']} | `{value}` | {options} |")
    lines.append("")
(ROOT / "docs").mkdir(exist_ok=True)
(ROOT / "docs" / "configuration.md").write_text("\n".join(lines), encoding="utf-8")
