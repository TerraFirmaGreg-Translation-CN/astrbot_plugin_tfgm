# TFGM 中文社区 AstrBot 插件

基于 **TFGM Sidecar 0.13.15.2** 实现 Minecraft 游戏聊天与 QQ 群双向互通，以及游戏内 AI 对话。所有功能都在本插件内；不注册 Minecraft 平台，不实现 OneBot 协议，不需要额外桥接进程。

QQ 使用 AstrBot 已有的 OneBot v11（`aiocqhttp`）连接。游戏侧使用 Sidecar HTTP API。

## 环境

- AstrBot **4.10.4+**（多服务器配置使用该版本引入的 `template_list`）。
- Sidecar **0.13.15.2**：MC 1.20.1 / Forge 47.x。插件检查 API v1 和最低版本；更高版本仍需实际验证接口兼容性。
- Python 3.10+；依赖见 `requirements.txt`。
- AstrBot 能访问 Sidecar HTTP 地址。Docker 中的 `127.0.0.1` 指向当前容器，不一定是游戏服务器。

## 安装与最小配置

1. 在 AstrBot 插件管理中从本仓库安装，或上传 `astrbot_plugin_tfgm.zip`。
2. 游戏服务器安装 Sidecar 0.13.15.2，在 `config/tfgm_sidecar.toml` 配置如下分组。已有分组请修改，不要重复添加 TOML 表头：

   ```toml
   [general]
   enabled = true

   [http]
   enabled = true
   bind_address = "127.0.0.1"
   port = 8765
   token = "替换为读取令牌"

   [messages]
   enabled = true
   token = "替换为另一个独立的消息令牌"
   dynamic_components = false
   ```

   根据部署网络调整监听地址；非回环监听必须设置读取令牌。确认 `sampling.events` 包含 `player_chat`。修改 Sidecar 配置后重启游戏服务器。插件只发送静态文本组件，不依赖动态组件功能。此链路不需要开启 Sidecar push。

3. AstrBot 已连接 QQ 后，由 **AstrBot 管理员**在目标 QQ 群发送 `/tfgm_origin`，复制结果，例如 `qq-main:GroupMessage:123456789`。它包含平台实例 ID，不能只填群号，也不要使用按群成员隔离的会话 ID。
4. 打开插件配置：添加服务器，填写唯一 ID、地址、读取令牌、消息令牌；添加路由，填写对应服务器 ID 和上一步的群 UMO；打开总开关。
5. 保存配置并**重载插件**，发送 `/tfgm_status` 查看状态。默认两个方向均全量转发，不同步进出/死亡通知。先在测试群验证。

核心配置示例（其他选项自动使用默认值）：

```json
{
  "enabled": true,
  "servers": [
    {
      "__template_key": "default",
      "id": "survival",
      "name": "生存服",
      "url": "http://127.0.0.1:8765",
      "read_token": "替换为读取令牌",
      "message_token": "替换为独立消息令牌"
    }
  ],
  "routes": [
    {
      "__template_key": "default",
      "id": "survival-qq",
      "server_id": "survival",
      "qq_origin": "qq-main:GroupMessage:123456789"
    }
  ]
}
```

同服可以绑定多个群，同群可以绑定多个服。路由只连接指定群与指定服，不将某群的消息再转发到另一个群。相同群服组合不能重复添加。

## 游戏内 AI

群服互通验证后，打开插件配置的「游戏内 AI → 启用」，选择 AstrBot 已配置的聊天模型和可选人格，保存并重载。全局 AI 开关和服务器自己的 AI 开关都需要开启。

```text
@小助手 高炉应该如何搭建？
@小助手 重置对话
```

- 默认仅提问玩家收到回答，按 **服务器 ID + UUID** 隔离历史，默认保存 10 轮、闲置 24 小时过期。
- 输入来自公共游戏聊天，即使回答仅自己可见，问题仍可能被其他玩家看到。本版本没有私密输入命令。
- 模型留空使用 AstrBot 当前默认模型；人格留空仅使用插件提示词，不自动继承 QQ 群人格或会话。
- 默认 AI 问题与回答不转发到 QQ，可分别开启。普通聊天不加入 AI 上下文。
- 默认每人冷却 10 秒、每服并发 2、请求超时 90 秒。同一玩家已有排队/执行中的问题时不会再创建第二个 AI 请求。重置口令也遵守并发和冷却限制。
- 通过 `Context.llm_generate` 直接生成文本；**不自动执行其他插件命令、MCP、工具调用、知识库检索或完整 Agent 流程**。本版没有开放无实际功能的工具配置开关。

## 消息与配置

WebUI 提供服务器、路由、连接、投递、AI 五组配置，所有实际支持的参数都有默认值及说明。完整字段表见 [配置参考](docs/configuration.md)。

- 两个方向可分别关闭、分别选择全量或前缀模式；默认前缀为 `#qq ` / `#mc `，仅在前缀模式生效。
- 可配置模板、游戏文本颜色、UUID/QQ 允许及拒绝列表、忽略命令前缀、其他机器人 QQ 号。
- 模板仅接受 `{server}`、`{player}`、`{nickname}`、`{message}`、`{time}`；时间使用 AstrBot 运行环境的本地时区。
- 优先展示 QQ 群名片。@ 转成普通文本；引用显示已有摘要，不额外查询历史。图片默认显示占位，可改为 HTTP(S) 链接或忽略；不在游戏里直接渲染图片。文件、语音、视频降级为文字占位。
- 默认每段 300 字、最多 4 段，超出标注截断。QQ→MC 颜色作用于整条消息。玩家文本中的 `§` 格式码会被移除，CQ 码以普通文本发送。
- 默认忽略机器人自己发出的消息；其他机器人需要填写忽略列表。Sidecar 发出的系统消息本身不会再次成为 `player_chat`。
- `查服` 保留固定回复「群峦格雷欢迎你」，不转发进游戏；`/tfgm` 保留社区链接。

更改配置统一在保存后重载插件。旧后台任务会取消并关闭 HTTP 会话；不会同时保留两套轮询。不要同时启动两个共享同一插件数据目录的 AstrBot 实例。

## 可靠性与数据

插件数据位于 AstrBot 的 `data/plugin_data/astrbot_plugin_tfgm/bridge.sqlite3`（由 `StarTools.get_data_dir` 定位），包含事件游标、待投递消息、结果记录和 AI 历史。与插件代码分开，升级不会主动删除它。

- 游标与事件产生的发送任务在同一事务提交。按服务器、启动实例及事件序号去重；QQ群输入按平台群会话和消息 ID 去重。
- 默认首次连接从当前事件末尾开始；可开启最近历史读取。重连只补发有效期内消息，默认 120 秒。缓冲缺口计入 `event_gap`；Sidecar 环形缓冲区不能保证长时间离线无丢失。
- 每目标队列默认上限 200 条，满时拒绝新任务并计入 `queue_full`；每目标默认间隔 1 秒。队列过期消息不再发送。
- Sidecar POST 使用稳定请求 ID；202 会以相同请求、相同 ID 重查。网络/部分服务错误也只重试原请求，默认最多 3 次。检测到启动实例变化后停止重放已经尝试的请求。
- 发送成功只代表 Sidecar 发生服务端发送调用，不保证玩家已阅读。零在线接收者标记 `no_online_recipients`，不建立离线信箱。
- QQ 主动发送异常可能意味着消息已经发出，因此不自动重试；插件中断时执行中的 QQ/AI 任务记为结果不确定，不自动重放。不是跨平台严格 exactly-once。
- 已完成/失败任务默认保留 24 小时，AI 历史默认闲置 24 小时过期，每分钟清理。SQLite 文件含聊天内容，请按游戏服务数据管理；日志不输出令牌、聊天正文或上游异常正文。
- `/tfgm_status` 展示连接、发送能力、队列和错误码。`messages_disabled` 检查 Sidecar 消息开关；`http_401` 检查对应读/写令牌；`qq_platform_not_found` 检查群 UMO 的平台 ID；`generation_failed` 检查 AstrBot 模型配置。

## 开发与验证

```sh
python -m pip install -r requirements.txt ruff
python scripts/generate_schema.py
ruff format .
ruff check .
python -m unittest discover -s tests -v
python scripts/package.py
```

`bridge/config.py` 是 WebUI Schema 和运行默认值的共同来源；修改后重新生成 `_conf_schema.json` 与配置参考。

自动测试覆盖配置校验、游标分页/重启/事务回滚、双向路由/过滤/去重、发送重试/零接收者、AI 身份隔离/重置/失败、真实本机 HTTP 分块响应与后台任务生命周期。AstrBot 入口测试使用 SDK 测试替身；核对的官方接口包括 4.10.4 的模型、人格、数据目录及 QQ 发送 API。

这些测试**不等于在真实 AstrBot + NapCat + TFGM 整合包上的部署验证**。正式启用前请在测试群完成：双向中文/换行/图片占位、两个群路由隔离、机器人回环、插件重载、游戏重启、两个玩家 AI 历史隔离与定向回复。

CI 在检查通过后生成 ZIP。`scripts/package.py` 也可直接从当前工作目录打包，无需先提交 Git；安装包只包含运行文件、Schema、文档、元数据和许可证。

## GitHub Release 发布

推送 `v*` 标签后，Actions 自动校验标签与 `metadata.yaml`、`main.py` 中的版本一致，执行 Python 3.10 / 3.12 检查，再创建 GitHub Release 并上传可直接安装的 `astrbot_plugin_tfgm.zip`。Release 说明自动生成，带 `-rc.1` 等后缀的标签标记为预发布。

发布前先提交并推送代码和工作流，再推送对应标签，例如当前版本：

```sh
git tag v0.3.0
git push origin v0.3.0
```

也可在 Actions → **Check, package and release plugin** → **Run workflow** 填写 `release_tag`，发布已经存在的远程标签；留空只检查和打包，不创建 Release。不会自动创建 Git 标签。重复运行遇到已有 Release 会保留其附件，不覆盖已发布内容。

检查和打包使用同一个已解析的提交；只有发布 job 获得 `contents: write`。使用内置 `GITHUB_TOKEN`，无需额外配置 PAT。普通 main 推送和 PR 继续仅检查并生成 Actions 安装包。

## 许可

AGPL-3.0，保留原插件许可证，见 [LICENSE](LICENSE)。
