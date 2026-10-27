# astrbot_plugin_tfgm

TerraFirmaGreg 中文社区的 AstrBot 插件，提供社区信息和查服指令。

## 使用

在 AstrBot WebUI 的插件管理中，通过仓库地址安装：

```text
https://github.com/TerraFirmaGreg-Translation-CN/astrbot_plugin_tfgm
```

- 通过 NapCat（OneBot v11）发送 `查服`，固定回复：`群峦格雷欢迎你`。无需 @ 机器人，只匹配完整指令（忽略首尾空白）。
- 发送 `/tfgm` 查看社区 GitHub 地址。

当前没有额外配置或第三方依赖。

## ZIP 安装包

推送到 `main`、推送 `v*` 标签或手动运行工作流时，GitHub Actions 会自动打包。

1. 打开仓库 [Actions](https://github.com/TerraFirmaGreg-Translation-CN/astrbot_plugin_tfgm/actions/workflows/package.yml)，选择成功的 `Package plugin` 运行。
2. 在 Artifacts 中下载 `astrbot_plugin_tfgm.zip`（需要登录 GitHub，保留 90 天）。
3. 在 AstrBot 插件管理中选择本地 ZIP 安装，直接上传下载的文件，无需解压。

ZIP 内含插件目录、入口、元数据、说明和许可证，不包含 GitHub 工作流。也可以在 Actions 页面点击 `Run workflow` 手动生成。

## 开发

将本仓库放入 AstrBot 的 `data/plugins/astrbot_plugin_tfgm` 目录，启动 AstrBot 后通过插件管理页面重载插件。

- `main.py`：插件入口和指令。
- `metadata.yaml`：插件名称、版本、作者及仓库信息。

提交前运行 `ruff format .` 和 `ruff check .`，并在 AstrBot 中验证指令。

## 来源与许可

根据 [AstrBot 插件开发指南](https://docs.astrbot.app/dev/star/plugin-new.html)及其推荐的 [Soulter/helloworld 模板](https://github.com/Soulter/helloworld)初始化，保留模板的 AGPL-3.0 许可证，详见 [LICENSE](LICENSE)。
