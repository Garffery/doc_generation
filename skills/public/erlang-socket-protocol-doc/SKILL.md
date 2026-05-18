---
name: erlang-socket-protocol-doc
description: >-
  Erlang game-server Socket protocol documentation. Use when drafting backend
  dev docs and explaining frontend-backend interaction over socket — locate
  pack/read handlers, map opcodes (e.g. segment 635, message 63500), and
  document binary field layout and C2S/S2C flow.
---

# Erlang Socket 前后端协议文档

撰写后端开发文档草稿、且功能涉及**客户端与服务端通过 Socket 通信**时，必须在「接口设计（草稿）」中补充协议说明。前后端不以 REST 为主交互时，以本 skill 为准。

## 协议编号约定

| 层级 | 示例 | 含义 |
|------|------|------|
| **协议段** | `635` | 功能域/模块分组（如某类活动、某系统） |
| **消息号** | `63500` | 具体一条 C2S 或 S2C 消息；通常对应 `pack/2`、`read/2` 的第一个参数 |
| **线上包号** | `pt:pack` 首参 | 实际发包用的数字，**以代码为准**（可能与消息号相同或不同，勿臆测） |

消息号与协议段的关系因项目而异（如 `635xx` 归属段 `635`）。文档中写清：**协议段**、**消息号**、**pt:pack 使用的包号**（若三者不全相同）。

## 从代码提取协议（必读）

在 Erlang 工程中查找 `pack(<MsgId>,` 与 `read(<MsgId>,`（或项目约定的 `encode`/`decode`）。

### pack — 服务端组包（多为 S2C）

```erlang
pack(63500, {ActivityId, PlayerLv}) ->
    Data = <<ActivityId:32, PlayerLv:32>>,
    {ok, pt:pack(635000, Data)}.
```

- 元组 `{ActivityId, PlayerLv}`：逻辑字段及顺序
- `<<...>>`：二进制布局（`:32` 等为位宽/类型）
- `pt:pack(635000, Data)`：线上包号与载荷

### read — 服务端解包（多为 C2S）

```erlang
read(63500, <<ActivityId:32>>) ->
    {ok, [ActivityId]}.
```

- `read` 与同名 `pack` 的**字段列表、位宽可以不同**（请求/响应不对称很常见）
- 必须分别文档化 C2S 的 `read` 与 S2C 的 `pack`（或项目中的反向命名）

### 位宽与类型（文档用语）

| 代码写法 | 文档类型 | 说明 |
|----------|----------|------|
| `Field:32` | int32 / uint32 | 32 位整数；有符号与否按项目约定标注 |
| `Field:16` | int16 | 16 位 |
| `Field:8` | byte | 8 位 |
| `Field/binary` | binary | 变长或固定长度需结合上下文说明 |
| 嵌套 `<<...>>` | 结构体 | 按顺序展开子字段 |

字符串、列表、map 等若经 `pt` 或自定义编码，在文档中写明**编码规则**或引用公共打包模块。

## 工作流

1. **划定范围**：按需求简报中的界面/操作，列出涉及的协议段与消息号（可从配置表、`*_pt.erl`、`*_proto.erl` 等模块名推断）。
2. **逐条对照代码**：每个消息号找到 `pack`/`read` 实现，记录方向（C2S / S2C）。
3. **画交互序**：谁在什么操作后发哪条消息、期望回哪条（可文字描述，复杂时用序号列表）。
4. **填表输出**：使用下方模板写入「接口设计（草稿）」。
5. **标待确认**：代码仓库不可见时，字段含义、错误码、未找到的 push 包标注 **待确认**。

## 「接口设计（草稿）」协议小节模板

每个涉及 Socket 的 F-xxx 功能点建议包含：

```markdown
#### 接口设计（草稿）— Socket

**通信方式**：WebSocket / TCP（按项目实际）

**协议段**：635（示例：活动相关）

##### 消息一览

| 方向 | 消息号 | 线上包号(pt) | 触发场景 | 处理模块（建议） |
|------|--------|--------------|----------|------------------|
| C2S | 63500 | （见代码） | 打开活动界面 | ... |
| S2C | 63501 | ... | 下发活动数据 | ... |

##### 63500 — 打开活动界面（示例）

| 字段 | 类型 | 说明 |
|------|------|------|
| ActivityId | int32 | 活动配置 id |
| PlayerLv | int32 | 玩家等级（仅 S2C 下发时存在则写在对应 pack 表） |

**C2S 载荷**（read）：`ActivityId`

**S2C 载荷**（pack）：`ActivityId`, `PlayerLv`

**业务说明**：客户端进入活动时发送…；服务端校验后返回…

**错误与边界**：（若无代码依据则写待确认）
```

- 一张表只描述**一个方向的一条消息**的载荷；C2S、S2C 分表或分小节。
- 协议段内其它消息（63501、63502…）按同样格式追加。

## 需求简报（research_brief）中的提示

若功能含 UI 或客户端操作，在功能点描述中**点名协议段或消息号**（已知时），并注明「需 Socket 协议说明」。未知时写「协议段待查（活动类界面）」。

## 与其它 skill 的配合

- 模块划分、gen_server、非 Socket 的 HTTP/RPC：遵循 `erlang-backend-doc`
- 活动持久化字段：遵循 `erlang-player-data-storage`
- 本 skill **只约束 Socket 协议与前后端交互**；不把协议字段与 `#role{}` / `#player_misc_extra{}` 混为同一表（逻辑字段可交叉引用）

## 禁止与注意

- 不要凭消息号规律**编造**未在 `pack`/`read` 中出现的字段或位宽。
- 不要默认 C2S、S2C 使用相同结构；必须分别对照 `read` 与 `pack`。
- `pt:pack` 的包号与 `pack/2` 的消息号不一致时，**两个数字都要写进文档**。
