# Euxrvsh PVP AstrBot Plugin

一个面向 AstrBot 的本地 PvP 游戏插件。

当前版本已经重构为：

- SQLite 本地存储
- AI Tool 优先调用
- 少量 `/pvp` 兜底命令
- 按会话隔离对局

项目仓库：
[https://github.com/yarizm/EuxrvshPVPBOTv0.01](https://github.com/yarizm/EuxrvshPVPBOTv0.01)

## 功能特性

- 使用 AstrBot 的 `llm_tool` 能力，让 AI 在合适时机自动调用 PvP 工具
- 提供统一的 `/pvp` 兜底命令，便于手动测试和调试
- 使用 SQLite 单文件存储，不依赖 MySQL
- 每个会话独立保存一局对战，互不干扰
- 插件内置角色定义、战斗状态、效果、冷却和战斗日志
- 对模糊自然语言增加了二次确认提示，降低误触发概率

## 当前角色

- `output_king` / `输出大王`

当前已实现技能：

- `focus_shift` / `聚势`
- `sidestep` / `侧闪`
- `chain_burst` / `链爆`

## 目录结构

```text
astrbot_plugin_euxrvsh_pvp/
  main.py
  metadata.yaml
  _conf_schema.json
  requirements.txt
  plugin/
  euxrvsh_core/
```

核心代码说明：

- `astrbot_plugin_euxrvsh_pvp/main.py`
  AstrBot 插件入口、LLM Tool 定义、`/pvp` 命令入口
- `astrbot_plugin_euxrvsh_pvp/plugin/controller.py`
  插件展示层和文本渲染
- `astrbot_plugin_euxrvsh_pvp/euxrvsh_core/services/battle_service.py`
  战斗主逻辑
- `astrbot_plugin_euxrvsh_pvp/euxrvsh_core/repositories/sqlite_repository.py`
  SQLite 存储实现

## 安装方式

### 1. 本地 AstrBot

把整个插件目录 `astrbot_plugin_euxrvsh_pvp` 复制到 AstrBot 的插件目录：

```text
<AstrBot data 目录>/plugins/astrbot_plugin_euxrvsh_pvp
```

例如 Windows 默认可能是：

```text
C:\Users\<用户名>\.astrbot\data\plugins\astrbot_plugin_euxrvsh_pvp
```

复制后重载插件或重启 AstrBot。

### 2. Docker 中的 AstrBot

推荐把插件放到宿主机挂载出来的 `data/plugins/` 目录，而不是只放进容器内部。

如果你的容器把宿主机目录挂载到了 `/AstrBot/data`，那么目标路径通常是：

```text
<宿主机 data 目录>/plugins/astrbot_plugin_euxrvsh_pvp
```

然后重启容器：

```bash
docker restart <astrbot_container>
```

如果只是临时测试，也可以直接拷贝进容器：

```bash
docker cp ./astrbot_plugin_euxrvsh_pvp <astrbot_container>:/AstrBot/data/plugins/
docker restart <astrbot_container>
```

## 插件配置

当前插件配置项非常少：

- `sqlite_path`
  可选。自定义 SQLite 数据文件路径。留空时自动使用 AstrBot 插件数据目录
- `enable_fallback_commands`
  是否开启 `/pvp` 兜底命令
- `enable_debug_tools`
  是否开启调试工具

默认情况下，SQLite 数据会写入：

```text
/AstrBot/data/plugin_data/astrbot_plugin_euxrvsh_pvp/battle.sqlite
```

如果是宿主机挂载目录，对应的就是宿主机 `data/plugin_data/astrbot_plugin_euxrvsh_pvp/battle.sqlite`。

## 使用方式

### 自然语言触发

推荐直接和 AstrBot 对话，例如：

- `开一把 2 人局`
- `我选输出大王`
- `我打 2 号`
- `我用链爆打 2 号`
- `看看战况`
- `结束回合`
- `重开这局`

当意图不明确时，插件会引导 AI 优先先确认，例如：

- `你是想继续进行 PvP 对局，还是只是普通聊天？`
- `你要对几号位执行这个操作？`
- `你想用哪个技能？当前可用技能是：聚势、侧闪、链爆。`

### `/pvp` 兜底命令

也可以手动使用：

```text
/pvp help
/pvp start <人数>
/pvp roles
/pvp pick <角色名或ID>
/pvp state [summary|full]
/pvp endturn
/pvp reset
```

## 已注册的 AI Tools

- `pvp_create_battle`
- `pvp_list_roles`
- `pvp_pick_role`
- `pvp_attack`
- `pvp_use_skill`
- `pvp_end_turn`
- `pvp_view_state`
- `pvp_reset_battle`

## 开发与验证

本项目当前主要交付物是插件目录 `astrbot_plugin_euxrvsh_pvp/`。

如果需要本地检查代码，可以运行：

```bash
python -m py_compile astrbot_plugin_euxrvsh_pvp/main.py
pytest tests -q -p no:cacheprovider
```

