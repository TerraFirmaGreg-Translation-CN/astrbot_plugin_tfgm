# astrbot_plugin_tfgm

TerraFirmaGreg 中文社区的 AstrBot 插件，目前为初始骨架。

## 使用

在 AstrBot WebUI 的插件管理中，通过仓库地址安装：

```text
https://github.com/TerraFirmaGreg-Translation-CN/astrbot_plugin_tfgm
```

发送 `/tfgm` 查看社区 GitHub 地址。当前没有额外配置或第三方依赖。

## 开发

将本仓库放入 AstrBot 的 `data/plugins/astrbot_plugin_tfgm` 目录，启动 AstrBot 后通过插件管理页面重载插件。

- `main.py`：插件入口和指令。
- `metadata.yaml`：插件名称、版本、作者及仓库信息。

提交前运行 `ruff format .` 和 `ruff check .`，并在 AstrBot 中验证指令。

## 来源与许可

根据 [AstrBot 插件开发指南](https://docs.astrbot.app/dev/star/plugin-new.html)及其推荐的 [Soulter/helloworld 模板](https://github.com/Soulter/helloworld)初始化，保留模板的 AGPL-3.0 许可证，详见 [LICENSE](LICENSE)。
