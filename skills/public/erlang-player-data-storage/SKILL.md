---
name: erlang-player-data-storage
description: >-
  Erlang game-server player data storage conventions. Use when drafting backend
  dev docs and deciding where activity or feature state is persisted — choose
  #player_misc_extra{} for operational events vs #role{} fields for permanent
  features; map fields to value/value_text/time slots.
---

# Erlang 玩家数据存储选型

撰写后端开发文档草稿时，在「数据设计（草稿）」中**必须先判定存储载体**，再给出字段映射。不要混用两种模式。

## 选型决策

| 场景 | 存储位置 | 判定依据 |
|------|----------|----------|
| **运营活动** | `#player_misc_extra{}` | 限时活动、赛季战令、节日玩法等；活动结束后数据可清理或归档；同一玩家可有多条记录（按 `key` 区分活动） |
| **功能 / 系统能力** | `#role{}` 中的字段 | 常驻功能（背包扩展、成就、VIP 等级等）；数据随角色长期存在；支持 Erlang 任意数据类型 |

**不确定时**：在文档中写明两种方案的取舍理由，并标注 **待确认**。

---

## 运营活动：`#player_misc_extra{}`

活动数据按 `(player_id, key)` 定位；`key` 一般为活动 id。

```erlang
#player_misc_extra{
    player_id,    # 玩家id
    key,          # key，一般是活动id，用来区分不同活动的数据
    value = 0,    # 只支持数,默认值为0
    value1 = 0,   # 只支持数字,默认值为0
    value2 = 0,   # 只支持数字,默认值为0
    value3 = 0,   # 只支持数字,默认值为0
    value_text = [], # 默认值是一个list，list内部能够支持erlang中所有的数据类型
    value_text_1 = [], # 默认值是一个list，list内部能够支持erlang中所有的数据类型
    value_text_2 = [], # 默认值是一个list，list内部能够支持erlang中所有的数据类型
    value_text_3 = [], # 默认值是一个list，list内部能够支持erlang中所有的数据类型
    time = 0,          # 时间戳
    time1 = 0,         # 时间戳
    time2 = 0,         # 时间戳
    server_id = 0,     # 时间戳
}
```

### 字段分配原则

- **数字类**（等级、积分、计数、位图掩码等）→ `value` / `value1` / `value2` / `value3`
- **复杂结构**（奖励列表、任务进度 map、已领取档位列表等）→ `value_text` / `value_text_1` / `value_text_2` / `value_text_3`（list 内可放任意 Erlang 项）
- **时间类**（活动开始/结束、上次刷新、结算时间等）→ `time` / `time1` / `time2`
- 同一活动内**固定语义**的槽位须在文档中列表说明，避免不同模块复用同一槽位

### 文档中须写清

- `key` 取值规则（活动 id 或配置表 id）
- 各 `value*` / `value_text_*` / `time*` 的业务含义（表格）
- 活动结束后的数据策略（保留 / 删除 / 邮件补发后清理）

---

## 功能：`#role{}` 字段

常驻功能数据挂在玩家 `#role{}` record 的**具名字段**上（非 `player_misc_extra`）。

- 数据类型：支持 Erlang 中所有数据类型（整数、元组、列表、map、嵌套 record 等）
- 文档中须写清：**字段名**、**类型/结构示例**、**默认值**、**读写模块**
- 若与活动共用逻辑，说明活动期内是否镜像到 `player_misc_extra`（一般不建议双写，除非有明确迁移需求）

---

## 「数据设计（草稿）」输出模板

每个 F-xxx 功能点的小节建议按以下结构填写：

```markdown
#### 数据设计（草稿）

**存储选型**：运营活动 → `#player_misc_extra{}` | 功能 → `#role{}.<字段名>`

| 逻辑字段 | 物理位置 | 类型 | 说明 |
|----------|----------|------|------|
| ... | value / value_text / time / role.xxx | ... | ... |

**key**（仅活动）：`<活动id 或规则>`

**生命周期**：...
```

活动类示例（战令）：

| 逻辑字段 | 物理位置 | 说明 |
|----------|----------|------|
| 战令等级 | value | 当前等级 1–15 |
| 累计积分 | value1 | 距下一级进度 |
| 已购档位 | value2 | 位图或枚举 |
| 已领取奖励 | value_text | 列表，元素为 `{Level, Tier}` 等 |
| 活动结束时间 | time | Unix 时间戳 |

---

## 与 erlang-backend-doc 的配合

- 模块划分、gen_server、接口设计仍遵循 `erlang-backend-doc`
- 本 skill **只约束玩家侧持久化形态**；ETS/Mnesia/配置表等另行说明，勿与 `player_misc_extra` / `role` 字段混淆
