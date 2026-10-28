# 配置参考

由 `scripts/generate_schema.py` 从运行默认值生成。所有修改保存后重载插件生效。

总开关 `enabled` 默认 `false`；`servers`、`routes` 默认空列表。连接、投递、AI 为全局设置；每台服务器有 AI 子开关，每条路由有独立转发规则。

## 服务器 servers[]

| 参数 | 含义 | 默认值 | 选项/范围 |
| --- | --- | --- | --- |
| `enabled` | 启用服务器 | `true` |  |
| `id` | 服务器唯一 ID | `""` |  |
| `name` | 服务器显示名称 | `"生存服"` |  |
| `url` | Sidecar 基础地址 | `"http://127.0.0.1:8765"` |  |
| `read_token` | Sidecar 读取令牌 http.token | `""` | 密码输入；与其他令牌分开 |
| `message_token` | Sidecar 消息令牌 messages.token | `""` | 密码输入；与其他令牌分开 |
| `ai_enabled` | 此服务器 AI 开关 | `true` |  |

## 群服路由 routes[]

| 参数 | 含义 | 默认值 | 选项/范围 |
| --- | --- | --- | --- |
| `enabled` | 启用路由 | `true` |  |
| `id` | 路由唯一 ID | `""` |  |
| `server_id` | 对应服务器 ID | `""` |  |
| `qq_origin` | QQ 群会话标识 UMO | `""` |  |
| `mc_to_qq` | 游戏 → QQ | `true` |  |
| `qq_to_mc` | QQ → 游戏 | `true` |  |
| `mc_mode` | 游戏转发模式 | `"all"` | all, prefix |
| `qq_mode` | QQ 转发模式 | `"all"` | all, prefix |
| `mc_prefix` | 游戏转发前缀 | `"#qq "` |  |
| `qq_prefix` | QQ 转发前缀 | `"#mc "` |  |
| `strip_prefix` | 移除匹配的转发前缀 | `true` |  |
| `mc_template` | 游戏 → QQ 格式 | `"[{server}] {player}：{message}"` |  |
| `qq_template` | QQ → 游戏格式 | `"[QQ群] {nickname}：{message}"` |  |
| `mc_color` | 游戏中显示颜色 | `"white"` | white, gray, aqua, green, yellow, gold |
| `image_mode` | 图片处理 | `"placeholder"` | placeholder, link, ignore |
| `quote_chars` | 引用摘要最大字数 | `80` | 0～300 |
| `ignored_prefixes` | 不转发的命令前缀 | `["/tfgm", "tfgm_status", "tfgm_origin"]` |  |
| `ignored_qq` | 忽略的 QQ 号（含其他机器人） | `[]` |  |
| `allowed_qq` | 允许的 QQ 号（空为全部） | `[]` |  |
| `denied_players` | 忽略的玩家 UUID | `[]` |  |
| `allowed_players` | 允许的玩家 UUID（空为全部） | `[]` |  |
| `join_leave` | 转发玩家加入/退出 | `false` |  |
| `death` | 转发玩家死亡 | `false` |  |

## 连接 connection

| 参数 | 含义 | 默认值 | 选项/范围 |
| --- | --- | --- | --- |
| `poll_seconds` | 聊天轮询间隔（秒） | `1.0` | 0.2～60 |
| `batch_size` | 每页事件数量 | `200` | 1～1000 |
| `timeout_seconds` | HTTP 超时（秒） | `5.0` | 4～60 |
| `health_seconds` | 健康检查间隔（秒） | `30` | 5～300 |
| `retry_seconds` | 最大重连退避（秒） | `30` | 1～300 |
| `initial_history` | 首次连接读取历史 | `false` |  |

## 投递 delivery

| 参数 | 含义 | 默认值 | 选项/范围 |
| --- | --- | --- | --- |
| `queue_capacity` | 每目标待投递上限 | `200` | 1～2000 |
| `ttl_seconds` | 转发有效期（秒） | `120` | 10～300 |
| `interval_seconds` | 同一目标发送间隔（秒） | `1.0` | 0～30 |
| `chunk_chars` | 单段最大字数 | `300` | 50～1000 |
| `max_chunks` | 最多分段数 | `4` | 1～10 |
| `attempts` | Sidecar 最大发送尝试次数 | `3` | 1～10 |
| `retention_hours` | 已完成记录保留小时数 | `24` | 1～168 |

## 游戏内 AI ai

| 参数 | 含义 | 默认值 | 选项/范围 |
| --- | --- | --- | --- |
| `enabled` | 启用游戏内 AI | `false` |  |
| `prefix` | 唤醒前缀 | `"@小助手 "` |  |
| `provider_id` | 聊天模型（留空使用 AstrBot 当前默认模型） | `""` |  |
| `persona_id` | 人格（留空只使用下方提示词） | `""` |  |
| `system_prompt` | 游戏助手提示词 | `"你是 TerraFirmaGreg 游戏助手。用简洁中文回答；不确定的配方和机制请明确说明，不要编造。"` |  |
| `reply_scope` | 回复范围 | `"player"` | player, all |
| `cooldown_seconds` | 同一玩家请求冷却（秒） | `10` | 0～600 |
| `concurrency` | 每服 AI 并发数 | `2` | 1～8 |
| `timeout_seconds` | AI 请求超时（秒） | `90` | 5～300 |
| `history_turns` | 每位玩家保留对话轮数 | `10` | 0～50 |
| `history_hours` | 对话闲置过期小时数 | `24` | 1～168 |
| `max_input_chars` | 问题最大字数 | `2000` | 100～10000 |
| `max_reply_chars` | 回答最大字数 | `1200` | 100～10000 |
| `show_thinking` | 显示思考中提示 | `true` |  |
| `thinking_text` | 思考中提示 | `"[小助手] 思考中……"` |  |
| `reply_prefix` | 回答前缀 | `"[小助手] "` |  |
| `reset_word` | 重置会话口令（接在唤醒前缀之后） | `"重置对话"` |  |
| `forward_questions` | 将 AI 提问同时转发到绑定 QQ 群 | `false` |  |
| `forward_replies` | 将 AI 回答同时转发到绑定 QQ 群 | `false` |  |
| `allowed_players` | 允许使用 AI 的 UUID（空为全部） | `[]` |  |
| `denied_players` | 禁止使用 AI 的 UUID | `[]` |  |
