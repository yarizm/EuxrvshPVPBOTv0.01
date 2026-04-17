# Euxrvsh PvP AstrBot Plugin

一个面向 AstrBot 的本地 PvP 游戏插件。

当前版本重点是：

- 运行态使用 SQLite
- 角色定义改为 JSON 文件加载
- 插件数据目录清晰可见
- 支持用户通过 `roles/custom/*.json` 扩展角色
- AI Tool 优先，`/pvp` 作为兜底命令

项目仓库：[https://github.com/yarizm/EuxrvshPVPBOTv0.01](https://github.com/yarizm/EuxrvshPVPBOTv0.01)

## 目录结构

```text
astrbot_plugin_euxrvsh_pvp/
  main.py
  metadata.yaml
  _conf_schema.json
  requirements.txt
  plugin/
  euxrvsh_core/

插件运行后会自动初始化：

<AstrBot data>/plugin_data/astrbot_plugin_euxrvsh_pvp/
  runtime.db
  storage.json
  roles/
    builtin/
      output_king.json
    custom/
```

## 存储设计

插件现在不再把角色定义写进数据库。

- `runtime.db`
  只保存对局运行态：
  - `battles`
  - `battle_players`
  - `battle_effects`
  - `battle_cooldowns`
  - `battle_log`
- `storage.json`
  保存当前存储结构的元信息和目录位置
- `roles/builtin/*.json`
  官方内置角色文件
- `roles/custom/*.json`
  用户自定义角色文件

## 安装方式

把整个 `astrbot_plugin_euxrvsh_pvp` 目录复制到 AstrBot 的插件目录：

```text
<AstrBot data>/plugins/astrbot_plugin_euxrvsh_pvp
```

例如 Windows 本地常见路径：

```text
C:\Users\<用户名>\.astrbot\data\plugins\astrbot_plugin_euxrvsh_pvp
```

如果你用 Docker 部署 AstrBot，推荐把插件放到宿主机挂载出来的 `data/plugins/` 目录，再重启容器。

## 插件配置

当前配置项：

- `storage_root`
  插件存储根目录。留空时默认写到：
  `plugin_data/astrbot_plugin_euxrvsh_pvp/`
- `sqlite_path`
  兼容字段。仅用于旧版本迁移；如果填写，会把它的父目录视为 `storage_root`
- `enable_fallback_commands`
  是否开启 `/pvp` 命令组
- `enable_debug_tools`
  是否开启调试工具

## 使用方式

### 自然语言

可以直接对 AstrBot 说：

- `开一把 2 人局`
- `我选输出大王`
- `我打 2 号`
- `我用链爆打 2 号`
- `看看战况`
- `结束回合`

### `/pvp` 兜底命令

```text
/pvp help
/pvp start <人数>
/pvp roles
/pvp pick <角色名或ID>
/pvp state [summary|full]
/pvp endturn
/pvp reset
```

## 已注册 AI Tools

- `pvp_create_battle`
- `pvp_list_roles`
- `pvp_pick_role`
- `pvp_attack`
- `pvp_use_skill`
- `pvp_end_turn`
- `pvp_view_state`
- `pvp_reset_battle`

## 角色扩展

### 扩展方式

1. 把角色 JSON 文件放进：

```text
<storage_root>/roles/custom/
```

2. 重载插件或重启 AstrBot

3. 用 `/pvp roles` 或自然语言确认角色是否加载成功

### 角色 JSON 结构

```json
{
  "role_id": "custom_role",
  "name": "自定义角色",
  "summary": "一句话介绍",
  "stats": {
    "hp": 24,
    "atk": 6,
    "defense": 2,
    "max_ap": 2
  },
  "skills": [
    {
      "key": "sample_skill",
      "name": "示例技能",
      "description": "技能描述",
      "ap_cost": 1,
      "cooldown": 2,
      "target_type": "self",
      "branches": [
        {
          "when": "always",
          "actions": [
            {
              "type": "append_detail",
              "text": "这里是技能效果描述。"
            }
          ]
        }
      ]
    }
  ]
}
```

### 当前支持的条件

- `always`
- `focus_lt`
- `focus_gte`

### 当前支持的动作

- `set_focus`
- `add_focus`
- `set_effect`
- `clear_effect`
- `attack`
- `append_detail`

`attack` 动作当前支持这些参数：

- `base_damage`
- `allow_multiplier`
- `grant_focus`
- `apply_burn`

## 当前内置角色

- `output_king` / `输出大王`

内置技能：

- `focus_shift` / `聚势`
- `sidestep` / `侧闪`
- `chain_burst` / `链爆`

## 开发与验证

本地检查：

```bash
python -m compileall astrbot_plugin_euxrvsh_pvp tests
python -m pytest tests -q -p no:cacheprovider
```

当前这轮重构对应的验证结果：

- `5 passed`
- `compileall` 通过
