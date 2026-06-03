# 工具调用错误处理系统

本文档介绍如何使用项目中统一的工具调用错误处理系统，该系统实现了 [AI Agent 错误处理最佳实践](https://agentpatch.ai/blog/ai-agent-error-handling/)。

## 目录

- [核心概念](#核心概念)
- [快速开始](#快速开始)
- [错误分类](#错误分类)
- [重试策略](#重试策略)
- [备用工具链](#备用工具链)
- [成本追踪](#成本追踪)
- [配置说明](#配置说明)
- [最佳实践](#最佳实践)

## 核心概念

工具错误处理系统提供以下能力：

1. **自动错误分类**：将异常分类为可重试（5xx、超时、429）或致命错误（400、401/403）
2. **智能重试策略**：
   - 指数退避（5xx、超时）
   - 固定延迟（429 Retry-After）
   - 不重试（认证错误）
3. **熔断器保护**：短期内频繁失败时自动停止调用
4. **备用工具链**：主工具失败后自动切换到备用工具
5. **成本追踪**：记录调用成本、失败次数，实现渐进式退款

## 快速开始

### 1. 包装现有工具

```python
from doc_generation.resilience import ResilientTool, load_resilience_config

# 加载配置
config = load_resilience_config()

# 原始工具函数
def my_search_tool(query: str, max_results: int = 3) -> dict:
    # 调用外部 API
    return api.search(query, max_results=max_results)

# 包装为弹性工具
resilient_search = ResilientTool(
    tool_fn=my_search_tool,
    tool_name="my_search",
    config=config,
    timeout=30.0  # 30 秒超时
)

# 使用
try:
    result = resilient_search.invoke(query="AI agents", max_results=5)
except ToolError as e:
    logger.error(f"Search failed after retries: {e}")
```

### 2. 添加备用工具

```python
# 定义备用工具
def backup_search(query: str, max_results: int = 3) -> dict:
    return backup_api.search(query, max_results=max_results)

# 包装时指定备用链
resilient_search = ResilientTool(
    tool_fn=primary_search,
    tool_name="web_search",
    config=config,
    fallback_tools=[backup_search, another_backup],  # 按顺序尝试
    timeout=30.0
)

# 当主工具失败时，会自动尝试备用工具
result = resilient_search.invoke(query="AI agents")
```

### 3. 异步调用

```python
# 异步工具
async def async_search(query: str) -> dict:
    return await api.search_async(query)

resilient_search = ResilientTool(
    tool_fn=async_search,
    tool_name="async_search",
    config=config,
)

# 异步调用
result = await resilient_search.ainvoke(query="AI agents")
```

## 错误分类

系统会自动将异常分类为以下类型：

### 可重试错误 (ToolRetryableError)

- **ToolServerError (5xx)**: 服务器内部错误，使用指数退避重试
- **ToolTimeoutError**: 请求超时，重试 1 次
- **ToolRateLimitError (429)**: 速率限制，按 Retry-After 等待后重试
- **ToolConnectionError**: 网络连接失败，重试

### 致命错误 (ToolFatalError) - 不重试

- **ToolAuthError (401/403)**: 认证失败，需要人工修复
- **ToolConfigError**: 配置错误（如缺少 API key）
- **ToolNotFoundError (404)**: 资源不存在
- **ToolBadInputError (400)**: 错误输入，可交给 LLM 修正参数

### 错误分类示例

```python
from doc_generation.resilience import classify_tool_error

try:
    result = api.call()
except Exception as e:
    classified = classify_tool_error(e, tool_name="my_tool")
    
    if isinstance(classified, ToolRetryableError):
        print("可以重试")
    elif isinstance(classified, ToolBadInputError):
        print(f"输入错误: {classified.error_details}")
    elif isinstance(classified, ToolAuthError):
        print("认证失败，需要检查配置")
```

## 重试策略

### 配置重试参数

在 `config.yml` 中配置：

```yaml
stages:
  prod:
    resilience:
      retry:
        max_attempts: 3        # 最大重试次数
        base_delay: 1.0        # 基础延迟（秒）
        max_delay: 30.0        # 最大延迟（秒）
        jitter: true           # 启用抖动（随机化延迟）
```

### 重试行为

| 错误类型 | 重试策略 | 延迟计算 |
|---------|---------|---------|
| 5xx、超时 | 指数退避 | 1s → 2s → 4s → 8s (最大 30s) |
| 429 速率限制 | 固定延迟 | 按 Retry-After 头等待 |
| 400 错误输入 | 不重试 | 立即抛出，由 LLM 处理 |
| 401/403 认证 | 不重试 | 立即抛出 |

### 自定义重试逻辑

```python
from doc_generation.resilience import RetryConfig

custom_retry = RetryConfig(
    max_attempts=5,
    base_delay=2.0,
    max_delay=60.0,
    jitter=False  # 固定延迟
)

config = load_resilience_config()
config.retry = custom_retry

resilient_tool = ResilientTool(
    tool_fn=my_tool,
    tool_name="custom_tool",
    config=config,
)
```

## 备用工具链

### 按能力注册工具

```python
from doc_generation.resilience import register_tool_capability

# 注册多个搜索工具到 "web_search" 能力
register_tool_capability("web_search", "tavily_search")
register_tool_capability("web_search", "bing_search")
register_tool_capability("web_search", "duckduckgo_search")

# 获取备用工具列表（排除主工具）
fallbacks = get_fallback_tools("web_search", primary_tool="tavily_search")
# 返回: ["bing_search", "duckduckgo_search"]
```

### 手动指定备用链

```python
resilient_tool = ResilientTool(
    tool_fn=tavily_search,
    tool_name="tavily_search",
    config=config,
    fallback_tools=[bing_search, duckduckgo_search],
)

# 执行流程：
# 1. 尝试 tavily_search (最多重试 3 次)
# 2. 如果失败，尝试 bing_search (单次调用，不重试)
# 3. 如果失败，尝试 duckduckgo_search (单次调用，不重试)
# 4. 如果全部失败，抛出 FallbackToolExhaustedError
```

## 成本追踪

### 查看成本统计

```python
from doc_generation.resilience import get_cost_tracker

tracker = get_cost_tracker()

# 获取单个工具的统计
stats = tracker.get_stats("tavily_search")
if stats:
    print(f"总调用: {stats.total_calls}")
    print(f"成功: {stats.successful_calls}")
    print(f"失败: {stats.failed_calls}")
    print(f"连续失败: {stats.consecutive_failures}")
    print(f"总成本: {stats.total_cost}")
    print(f"总退款: {stats.total_refund}")
    print(f"错误分布: {stats.error_breakdown}")

# 获取所有工具的统计
all_stats = tracker.get_all_stats()
for tool_name, stats in all_stats.items():
    print(f"{tool_name}: {stats.successful_calls}/{stats.total_calls} 成功")
```

### 退款策略

系统实现渐进式退款：

| 错误类型 | 退款策略 |
|---------|---------|
| 5xx、超时 | **全额退款** (100%) |
| 首次 4xx | **全额退款** (100%) |
| 连续 4xx | 递减退款：90% → 80% → 60% → 20% → 0% |
| 401/403 认证 | **不退款** |
| 成功调用 | 不退款，重置连续失败计数 |

**退款重置条件**：
- 成功调用后立即重置
- 24 小时无活动后自动重置

```python
# 手动记录成本（通常由 ResilientTool 自动调用）
refund = tracker.record_call(
    tool_name="my_tool",
    success=False,
    error_type="4xx",
    cost=1.0
)
print(f"本次退款: {refund} 积分")
```

## 配置说明

### 完整配置示例

```yaml
stages:
  prod:
    resilience:
      # 重试配置
      retry:
        max_attempts: 3
        base_delay: 1.0
        max_delay: 30.0
        jitter: true
      
      # 熔断器配置
      circuit_breaker:
        failure_threshold: 5      # 失败 5 次后打开熔断器
        recovery_timeout: 60      # 60 秒后进入半开状态
        success_threshold: 2      # 半开状态下成功 2 次后关闭
      
      # 超时配置
      watchdog:
        default_timeout: 120      # 默认超时 120 秒
      
      # 静态兜底响应
      fallback:
        static_response: "系统暂时无法处理您的请求，请稍后重试。"
```

### 熔断器状态转换

```
CLOSED (正常) ─────失败 5 次────→ OPEN (拒绝请求)
      ↑                              │
      │                              │ 60 秒后
      │                              ↓
      └────成功 2 次────── HALF_OPEN (探测)
```

## 最佳实践

### 1. 设置合理的超时时间

```python
# 快速查询：30 秒
fast_tool = ResilientTool(tool_fn=quick_query, tool_name="quick", config=config, timeout=30)

# 复杂处理：5 分钟
slow_tool = ResilientTool(tool_fn=heavy_processing, tool_name="slow", config=config, timeout=300)
```

### 2. 为不同环境使用不同配置

```yaml
stages:
  dev:
    resilience:
      retry:
        max_attempts: 2  # 开发环境快速失败
  prod:
    resilience:
      retry:
        max_attempts: 5  # 生产环境更多重试
```

### 3. 监控成本和失败率

```python
import logging

tracker = get_cost_tracker()

def check_tool_health():
    stats = tracker.get_stats("critical_tool")
    if stats and stats.failed_calls > 0:
        failure_rate = stats.failed_calls / stats.total_calls
        if failure_rate > 0.5:
            logging.error(f"Tool failure rate too high: {failure_rate:.2%}")
        
        if stats.consecutive_failures > 10:
            logging.critical(f"Tool has {stats.consecutive_failures} consecutive failures!")
```

### 4. 优雅降级

```python
def search_with_fallback(query: str) -> dict:
    resilient_search = ResilientTool(
        tool_fn=primary_search,
        tool_name="search",
        config=config,
        fallback_tools=[backup_search],
    )
    
    try:
        return resilient_search.invoke(query=query)
    except FallbackToolExhaustedError:
        # 所有搜索工具都失败，返回缓存结果
        return get_cached_results(query)
```

### 5. 日志记录

系统自动记录详细日志：

```
[TOOL_RETRY] Retryable error on attempt 1/3 for tool='tavily_search', sleeping 1.00s: TimeoutError
[RESILIENT_TOOL] Retries exhausted for tool='tavily_search' (refund=1.00), entering fallback
[TOOL_FALLBACK] tool='tavily_search' trying fallback 'bing_search' (position 0)
[TOOL_COST] Full refund for tool='tavily_search' error_type='timeout': 1.00 credits
```

## 示例：完整的搜索工具

```python
from doc_generation.resilience import (
    ResilientTool,
    load_resilience_config,
    ToolError,
    get_cost_tracker,
)

# 加载配置
config = load_resilience_config()

# 定义搜索工具
def tavily_search(query: str, max_results: int = 3) -> dict:
    # 实际的 API 调用
    return tavily_client.search(query, max_results=max_results)

def bing_search(query: str, max_results: int = 3) -> dict:
    return bing_client.search(query, top=max_results)

# 创建弹性工具
resilient_search = ResilientTool(
    tool_fn=tavily_search,
    tool_name="web_search",
    config=config,
    fallback_tools=[bing_search],
    timeout=30.0,
)

# 使用
try:
    results = resilient_search.invoke(query="AI agents", max_results=5)
    print(f"找到 {len(results)} 条结果")
except ToolError as e:
    print(f"搜索失败: {e}")

# 检查成本
tracker = get_cost_tracker()
stats = tracker.get_stats("web_search")
print(f"搜索成本: {stats.total_cost} 积分，退款: {stats.total_refund} 积分")
```

## 常见问题

### Q1: 为什么 400 错误不会自动重试？

A: 400 错误通常表示输入参数有问题。盲目重试相同的错误参数不会成功。正确的做法是让 LLM 看到错误信息后修正参数，再重新调用。

### Q2: 熔断器打开后如何恢复？

A: 熔断器会在配置的 `recovery_timeout`（默认 60 秒）后自动进入半开状态，允许探测请求。如果探测成功，熔断器会关闭。

### Q3: 如何禁用某个工具的重试？

```python
from doc_generation.resilience import RetryConfig

no_retry_config = RetryConfig(max_attempts=1)  # 只尝试 1 次
config.retry = no_retry_config

tool = ResilientTool(tool_fn=my_tool, tool_name="no_retry", config=config)
```

### Q4: 成本追踪会影响性能吗？

A: 成本追踪使用线程锁保证线程安全，但开销很小（微秒级）。在高并发场景下影响可以忽略不计。

## 参考资料

- [AI Agent 错误处理最佳实践](https://agentpatch.ai/blog/ai-agent-error-handling/)
- [HTTP 状态码参考](https://developer.mozilla.org/en-US/docs/Web/HTTP/Status)
- [指数退避算法](https://en.wikipedia.org/wiki/Exponential_backoff)
