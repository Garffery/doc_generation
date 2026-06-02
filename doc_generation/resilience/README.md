# Resilience 模块说明文档

## 概述

`resilience` 模块是系统调用 LLM 模型的统一异常处理框架。它为所有模型调用提供了完整的弹性保护机制，确保单个 LLM 服务的不可用不会导致整个系统崩溃。

## 核心功能

| 功能 | 说明 |
|------|------|
| 错误分类 | 将各种原始异常统一归类为可重试/不可重试两大类 |
| 指数退避重试 | 对瞬态错误自动重试，支持 Full Jitter 避免惊群效应 |
| 熔断器 | 按 backend 粒度熔断，防止持续向已故障的服务发送请求 |
| 超时看门狗 | 为每次调用设置硬超时，避免请求无限等待 |
| 降级链 | 主模型失败后按顺序切换到备用模型，最终兜底为静态响应 |

## 整体架构

```
请求进入
    │
    ▼
┌─────────────────┐
│  ResilientModel │  (invoker.py - 核心编排器)
└────────┬────────┘
         │
         ▼
┌─────────────────┐    ┌──────────────────┐
│  熔断器检查      │───▶│ 直接走降级链      │ (circuit OPEN 时)
│ (circuit_breaker)│    └──────────────────┘
└────────┬────────┘
         │ (circuit CLOSED/HALF_OPEN)
         ▼
┌─────────────────┐
│  Watchdog 超时   │  (watchdog.py)
│  保护包装        │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  指数退避重试    │  (retry.py)
│  循环调用        │
└────────┬────────┘
         │
    成功 ─┤── 失败(可重试)：继续重试
         │      │
         │      └── 重试耗尽
         │              │
         ▼              ▼
    返回结果     ┌─────────────────┐
                 │   降级链         │  (fallback.py)
                 │  备用模型→静态   │
                 └─────────────────┘
```

## 模块详细说明

### 1. errors.py — 错误分类体系

定义了统一的 LLM 错误层次结构：

```
LLMError (基类)
├── LLMRetryableError (可重试 - 瞬态错误)
│   ├── LLMRateLimitError      — 429 速率限制
│   ├── LLMTimeoutError        — 408/504/连接超时
│   ├── LLMModelOverloadedError — 500/502/503 模型过载
│   └── LLMConnectionError     — 网络连接失败
├── LLMFatalError (不可重试 - 致命错误)
│   ├── LLMAuthError           — 401/403 认证失败
│   ├── LLMContentFilterError  — 内容安全过滤
│   ├── LLMContextLengthError  — 上下文超限
│   ├── LLMInvalidRequestError — 400 无效请求
│   └── LLMOutputParseError    — 结构化输出解析失败
└── CircuitOpenError           — 熔断器开路拒绝
```

**`classify_error()` 函数**是错误分类的核心入口，按以下优先级进行匹配：
1. 异常类型名中的超时/连接关键词
2. HTTP 状态码（429/408/504/500/502/503/401/403/400）
3. 异常类型名模式匹配（兼容 OpenAI SDK 异常类）
4. 错误消息内容匹配
5. 默认归为可重试错误（保守策略）

### 2. retry.py — 指数退避重试

提供 `retry_sync()` 和 `retry_async()` 两个执行器。

**重试策略：**
- 仅对 `LLMRetryableError` 进行重试
- 遇到 `LLMFatalError` 立即停止重试，直接抛出
- 未被识别的异常先经过 `classify_error()` 分类

**退避算法：**
```
delay = min(base_delay × 2^attempt, max_delay)
如果启用 jitter: delay = random(0, delay)    # Full Jitter
如果有 Retry-After: delay = min(retry_after, max_delay)
```

**默认配置：**
- `max_attempts`: 3
- `base_delay`: 1.0s
- `max_delay`: 30.0s
- `jitter`: true

### 3. circuit_breaker.py — Per-Backend 熔断器

按 backend（如 openai、deepseek）维度创建独立的熔断器实例，线程安全。

**三态转换模型：**

```
         连续失败达到阈值
CLOSED ──────────────────▶ OPEN
  ▲                          │
  │ 探测成功达到阈值          │ 冷却期结束
  │                          ▼
  └─────────────────── HALF_OPEN
         探测失败 ──────▶ OPEN
```

- **CLOSED（关闭）：** 正常放行所有请求，记录失败次数
- **OPEN（打开）：** 拒绝所有请求，等待冷却期结束
- **HALF_OPEN（半开）：** 允许一个探测请求通过，成功则关闭，失败则重新打开

**默认配置：**
- `failure_threshold`: 5（连续 5 次失败触发熔断）
- `recovery_timeout`: 60s（冷却期）
- `success_threshold`: 2（半开状态需 2 次成功才关闭）

### 4. watchdog.py — 超时看门狗

为每次 LLM 调用提供硬超时保护，兼容 Windows 平台。

**实现方式：**
- **同步调用**：使用 `ThreadPoolExecutor` + `future.result(timeout)` 实现超时
- **异步调用**：使用 `asyncio.wait_for()` 实现超时

超时后抛出 `WatchdogTimeoutError`（继承自 `LLMTimeoutError`，属于可重试错误）。

**默认超时：** 120 秒

### 5. fallback.py — 降级链

主模型重试失败或熔断后的降级处理。

**降级流程：**
1. 按配置顺序逐个尝试备用模型（每个备用模型只尝试一次，不重试）
2. 如果某个备用节点配置为 `static`，直接返回静态文本
3. 所有备用模型失败后，返回全局静态兜底响应
4. 如果没有配置任何降级选项，抛出 `FallbackExhaustedError`

**配置示例：**
```yaml
roles:
  supervisor:
    backend: openai
    handle: gpt-5.4-mini
    fallback_chain:
      - backend: deepseek        # 第一降级：切换到 deepseek
        handle: deepseek-v4-flash
      - static: "Supervisor暂时不可用，流程终止。"  # 最终静态兜底
```

### 6. invoker.py — ResilientModel 编排器

**核心组件**，包装 LangChain 模型实例，将上述所有机制串联为统一的调用流程。

**调用链路（invoke/ainvoke）：**
1. 检查熔断器状态 → 如果 OPEN，跳过主模型直接走降级链
2. Watchdog 超时保护 → 包装实际模型调用
3. 指数退避重试 → 对超时包装后的调用进行重试
4. 成功 → 记录成功，返回结果
5. 失败 → 记录失败（影响熔断器计数），进入降级链

**透明代理：**
- `bind_tools()` 和 `with_structured_output()` 返回新的 `ResilientModel` 包装
- `__getattr__` 代理所有其他属性到底层模型
- 对上层代码完全透明，无需修改调用方式

### 7. config.py — 配置解析

从 `config.yml` 解析所有弹性配置，包括：
- 重试配置（`RetryConfig`）
- 熔断器配置（`CircuitBreakerConfig`）
- 看门狗配置（`WatchdogConfig`）
- 各角色的降级链（`FallbackEntry`）
- 各角色对应的 backend 映射

## 配置参考

```yaml
resilience:
  retry:
    max_attempts: 3        # 最大重试次数
    base_delay: 1.0        # 基础延迟（秒）
    max_delay: 30.0        # 最大延迟（秒）
    jitter: true           # 是否启用随机抖动
  circuit_breaker:
    failure_threshold: 5   # 触发熔断的连续失败次数
    recovery_timeout: 60   # 熔断后冷却期（秒）
    success_threshold: 2   # 半开状态恢复所需成功次数
  watchdog:
    default_timeout: 120   # 单次调用超时（秒）
  fallback:
    static_response: "系统暂时无法处理您的请求，请稍后重试。"
```

## 使用方式

上层代码通过 `ResilientModel` 包装原始模型即可获得完整的弹性保护，无需关心内部实现细节：

```python
from doc_generation.resilience import ResilientModel, load_resilience_config

config = load_resilience_config(stage="prod")
resilient_llm = ResilientModel(model=raw_model, role="supervisor", config=config)

# 使用方式与原始模型完全一致
result = await resilient_llm.ainvoke(messages)
```
