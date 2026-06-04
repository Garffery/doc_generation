#***********************************************
#      Filename: tool_cost.py
#   Description: 工具调用成本追踪和统计
#***********************************************

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from threading import Lock

logger = logging.getLogger(__name__)


@dataclass
class ToolCallRecord:
    """单次工具调用记录"""
    tool_name: str
    timestamp: float
    success: bool
    error_type: Optional[str] = None
    duration: float = 0.0
    cost: float = 0.0
    refund: float = 0.0

    def __post_init__(self):
        if self.timestamp == 0:
            self.timestamp = time.time()


@dataclass
class ToolCostStats:
    """工具成本统计信息"""
    tool_name: str
    total_calls: int = 0
    success_calls: int = 0
    failed_calls: int = 0
    total_cost: float = 0.0
    total_refund: float = 0.0
    net_cost: float = 0.0
    error_breakdown: Dict[str, int] = field(default_factory=dict)
    avg_duration: float = 0.0
    total_duration: float = 0.0

    @property
    def success_rate(self) -> float:
        """成功率（百分比）"""
        if self.total_calls == 0:
            return 0.0
        return (self.success_calls / self.total_calls) * 100.0

    @property
    def failure_rate(self) -> float:
        """失败率（百分比）"""
        return 100.0 - self.success_rate

    def to_dict(self) -> Dict:
        """转换为字典格式"""
        return {
            "tool_name": self.tool_name,
            "total_calls": self.total_calls,
            "success_calls": self.success_calls,
            "failed_calls": self.failed_calls,
            "success_rate": round(self.success_rate, 2),
            "failure_rate": round(self.failure_rate, 2),
            "total_cost": round(self.total_cost, 4),
            "total_refund": round(self.total_refund, 4),
            "net_cost": round(self.net_cost, 4),
            "avg_duration": round(self.avg_duration, 3),
            "total_duration": round(self.total_duration, 3),
            "error_breakdown": self.error_breakdown,
        }


class ToolCostTracker:
    """工具调用成本追踪器。

    追踪所有工具调用的成本、成功率、失败类型等统计信息。
    线程安全的单例实现。

    Example:
        ```python
        tracker = get_cost_tracker()

        # 记录成功调用
        tracker.record_call("tavily_search", success=True)

        # 记录失败调用（带退款）
        refund = tracker.record_call("tavily_search", success=False, error_type="timeout")

        # 获取统计信息
        stats = tracker.get_stats("tavily_search")
        print(f"成功率: {stats.success_rate:.2f}%")

        # 获取所有工具的统计
        all_stats = tracker.get_all_stats()

        # 重置统计
        tracker.reset()
        ```
    """

    def __init__(
        self,
        default_cost_per_call: float = 0.01,
        refund_on_failure: bool = True,
        refund_percentage: float = 1.0,
    ):
        """初始化成本追踪器。

        Args:
            default_cost_per_call: 每次调用的默认成本
            refund_on_failure: 失败时是否退款
            refund_percentage: 退款比例（0.0-1.0）
        """
        self._default_cost = default_cost_per_call
        self._refund_on_failure = refund_on_failure
        self._refund_percentage = max(0.0, min(1.0, refund_percentage))

        self._records: List[ToolCallRecord] = []
        self._stats_cache: Dict[str, ToolCostStats] = {}
        self._lock = Lock()
        self._start_time = time.time()

        logger.info(
            "[COST_TRACKER] Initialized with default_cost=%.4f, refund=%s (%.0f%%)",
            self._default_cost, self._refund_on_failure, self._refund_percentage * 100
        )

    def record_call(
        self,
        tool_name: str,
        success: bool,
        error_type: Optional[str] = None,
        duration: float = 0.0,
        cost: Optional[float] = None,
    ) -> float:
        """记录一次工具调用。

        Args:
            tool_name: 工具名称
            success: 是否成功
            error_type: 错误类型（失败时）
            duration: 调用耗时（秒）
            cost: 本次调用成本（如果为 None 则使用默认值）

        Returns:
            退款金额（如果有）
        """
        call_cost = cost if cost is not None else self._default_cost
        refund = 0.0

        # 计算退款
        if not success and self._refund_on_failure:
            refund = call_cost * self._refund_percentage

        with self._lock:
            # 记录调用
            record = ToolCallRecord(
                tool_name=tool_name,
                timestamp=time.time(),
                success=success,
                error_type=error_type,
                duration=duration,
                cost=call_cost,
                refund=refund,
            )
            self._records.append(record)

            # 更新缓存
            if tool_name not in self._stats_cache:
                self._stats_cache[tool_name] = ToolCostStats(tool_name=tool_name)

            stats = self._stats_cache[tool_name]
            stats.total_calls += 1
            stats.total_cost += call_cost
            stats.total_refund += refund
            stats.net_cost = stats.total_cost - stats.total_refund
            stats.total_duration += duration
            stats.avg_duration = stats.total_duration / stats.total_calls

            if success:
                stats.success_calls += 1
            else:
                stats.failed_calls += 1
                if error_type:
                    stats.error_breakdown[error_type] = stats.error_breakdown.get(error_type, 0) + 1

        if not success:
            logger.debug(
                "[COST_TRACKER] Recorded failed call: tool='%s', error='%s', cost=%.4f, refund=%.4f",
                tool_name, error_type or "unknown", call_cost, refund
            )

        return refund

    def get_stats(self, tool_name: str) -> Optional[ToolCostStats]:
        """获取指定工具的统计信息。

        Args:
            tool_name: 工具名称

        Returns:
            统计信息，如果工具从未被调用则返回 None
        """
        with self._lock:
            return self._stats_cache.get(tool_name)

    def get_all_stats(self) -> Dict[str, ToolCostStats]:
        """获取所有工具的统计信息。

        Returns:
            工具名称到统计信息的映射
        """
        with self._lock:
            return dict(self._stats_cache)

    def get_total_stats(self) -> Dict:
        """获取全局汇总统计。

        Returns:
            包含所有工具汇总数据的字典
        """
        with self._lock:
            total_calls = sum(s.total_calls for s in self._stats_cache.values())
            total_success = sum(s.success_calls for s in self._stats_cache.values())
            total_failed = sum(s.failed_calls for s in self._stats_cache.values())
            total_cost = sum(s.total_cost for s in self._stats_cache.values())
            total_refund = sum(s.total_refund for s in self._stats_cache.values())
            total_duration = sum(s.total_duration for s in self._stats_cache.values())

            success_rate = (total_success / total_calls * 100.0) if total_calls > 0 else 0.0

            return {
                "total_calls": total_calls,
                "success_calls": total_success,
                "failed_calls": total_failed,
                "success_rate": round(success_rate, 2),
                "total_cost": round(total_cost, 4),
                "total_refund": round(total_refund, 4),
                "net_cost": round(total_cost - total_refund, 4),
                "total_duration": round(total_duration, 3),
                "uptime": round(time.time() - self._start_time, 3),
                "tools_count": len(self._stats_cache),
            }

    def get_records(
        self,
        tool_name: Optional[str] = None,
        success: Optional[bool] = None,
        limit: Optional[int] = None,
    ) -> List[ToolCallRecord]:
        """获取调用记录。

        Args:
            tool_name: 过滤指定工具（None 表示所有工具）
            success: 过滤成功/失败（None 表示所有）
            limit: 限制返回数量（None 表示全部）

        Returns:
            符合条件的调用记录列表（按时间倒序）
        """
        with self._lock:
            records = list(self._records)

        # 过滤
        if tool_name is not None:
            records = [r for r in records if r.tool_name == tool_name]
        if success is not None:
            records = [r for r in records if r.success == success]

        # 按时间倒序排列
        records.sort(key=lambda r: r.timestamp, reverse=True)

        # 限制数量
        if limit is not None and limit > 0:
            records = records[:limit]

        return records

    def reset(self, tool_name: Optional[str] = None):
        """重置统计信息。

        Args:
            tool_name: 重置指定工具（None 表示重置所有）
        """
        with self._lock:
            if tool_name is None:
                self._records.clear()
                self._stats_cache.clear()
                self._start_time = time.time()
                logger.info("[COST_TRACKER] Reset all statistics")
            else:
                self._records = [r for r in self._records if r.tool_name != tool_name]
                if tool_name in self._stats_cache:
                    del self._stats_cache[tool_name]
                logger.info("[COST_TRACKER] Reset statistics for tool='%s'", tool_name)

    def export_summary(self) -> str:
        """导出可读的统计摘要。

        Returns:
            格式化的统计摘要字符串
        """
        total = self.get_total_stats()
        all_stats = self.get_all_stats()

        lines = [
            "=" * 60,
            "Tool Cost Tracker Summary",
            "=" * 60,
            f"Total Calls: {total['total_calls']}",
            f"Success Rate: {total['success_rate']:.2f}%",
            f"Total Cost: ${total['total_cost']:.4f}",
            f"Total Refund: ${total['total_refund']:.4f}",
            f"Net Cost: ${total['net_cost']:.4f}",
            f"Total Duration: {total['total_duration']:.2f}s",
            f"Uptime: {total['uptime']:.2f}s",
            f"Tools Tracked: {total['tools_count']}",
            "",
            "Per-Tool Statistics:",
            "-" * 60,
        ]

        # 按调用次数排序
        sorted_tools = sorted(
            all_stats.items(),
            key=lambda x: x[1].total_calls,
            reverse=True
        )

        for tool_name, stats in sorted_tools:
            lines.append(f"\n[{tool_name}]")
            lines.append(f"  Calls: {stats.total_calls} (Success: {stats.success_calls}, Failed: {stats.failed_calls})")
            lines.append(f"  Success Rate: {stats.success_rate:.2f}%")
            lines.append(f"  Cost: ${stats.net_cost:.4f} (Refund: ${stats.total_refund:.4f})")
            lines.append(f"  Avg Duration: {stats.avg_duration:.3f}s")

            if stats.error_breakdown:
                lines.append("  Error Breakdown:")
                for error_type, count in sorted(stats.error_breakdown.items(), key=lambda x: x[1], reverse=True):
                    lines.append(f"    - {error_type}: {count}")

        lines.append("=" * 60)
        return "\n".join(lines)


# --- 全局单例 ---

_global_tracker: Optional[ToolCostTracker] = None
_tracker_lock = Lock()


def get_cost_tracker(
    default_cost_per_call: float = 0.01,
    refund_on_failure: bool = True,
    refund_percentage: float = 1.0,
    reset: bool = False,
) -> ToolCostTracker:
    """获取全局成本追踪器实例（单例模式）。

    Args:
        default_cost_per_call: 每次调用的默认成本
        refund_on_failure: 失败时是否退款
        refund_percentage: 退款比例（0.0-1.0）
        reset: 是否重置现有追踪器

    Returns:
        全局 ToolCostTracker 实例
    """
    global _global_tracker

    with _tracker_lock:
        if _global_tracker is None or reset:
            _global_tracker = ToolCostTracker(
                default_cost_per_call=default_cost_per_call,
                refund_on_failure=refund_on_failure,
                refund_percentage=refund_percentage,
            )
        return _global_tracker
