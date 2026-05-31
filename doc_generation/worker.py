#***********************************************
#      Filename: worker.py
#   Description: ARQ Worker - 执行 claude_code_tool 异步任务
#***********************************************

"""ARQ Worker 定义
独立进程，监听 Redis 队列，执行 _claude_code_tool 并将结果存入 Redis。

启动方式:
    arq doc_generation.worker.WorkerSettings
"""

import os
import logging

from doc_generation.utils import load_dotenv_if_present

load_dotenv_if_present()

import redis.asyncio as aioredis
from arq.connections import RedisSettings

logger = logging.getLogger(__name__)


REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379")


async def run_claude_code_tool(ctx: dict, job_id: str, thread_id: str, tool_args: dict) -> None:
    """执行 claude_code_tool 并将结果/错误存入 Redis。

    Args:
        ctx: ARQ worker context (contains redis pool)
        job_id: 唯一任务 ID
        thread_id: LangGraph thread_id，用于回调恢复
        tool_args: 传递给 claude_code 的参数
    """
    r: aioredis.Redis = ctx.get("redis")
    result_key = f"claude_code_job:{job_id}"
    error_key = f"claude_code_job:{job_id}:error"

    logger.info("[WORKER] Starting claude_code_tool job_id=%s thread_id=%s", job_id, thread_id)

    try:
        from doc_generation.tools.claude_code_tool import _run_claude_code

        prompt = tool_args.get("prompt", "")
        result = await _run_claude_code(
            prompt,
            system_prompt=tool_args.get("system_prompt"),
            model=tool_args.get("model"),
            cwd=tool_args.get("cwd"),
            max_turns=tool_args.get("max_turns"),
            allowed_tools=tool_args.get("allowed_tools"),
        )

        await r.set(result_key, result, ex=3600)
        logger.info("[WORKER] claude_code_tool completed job_id=%s, result_length=%d", job_id, len(result))

    except Exception as e:
        error_msg = f"{type(e).__name__}: {e}"
        await r.set(error_key, error_msg, ex=3600)
        logger.exception("[WORKER] claude_code_tool failed job_id=%s: %s", job_id, error_msg)

    # 触发回调恢复子图
    try:
        await _trigger_resume_callback(thread_id, job_id)
    except Exception as cb_err:
        logger.warning("[WORKER] Failed to trigger resume callback: %s", cb_err)


async def _trigger_resume_callback(thread_id: str, job_id: str) -> None:
    """通知 FastAPI 后端恢复子图执行"""
    import httpx

    callback_url = os.environ.get(
        "RESUME_CALLBACK_URL",
        "http://localhost:8000/api/internal/resume/researcher"
    )
    url = f"{callback_url}/{thread_id}"

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(url, json={"job_id": job_id})
        resp.raise_for_status()
        logger.info("[WORKER] Resume callback sent for thread_id=%s, status=%d", thread_id, resp.status_code)


async def startup(ctx: dict) -> None:
    """Worker 启动时初始化 Redis 连接"""
    ctx["redis"] = aioredis.from_url(REDIS_URL, decode_responses=True)
    logger.info("[WORKER] Started, connected to Redis at %s", REDIS_URL)


async def shutdown(ctx: dict) -> None:
    """Worker 关闭时清理 Redis 连接"""
    r: aioredis.Redis = ctx.get("redis")
    if r:
        await r.aclose()
    logger.info("[WORKER] Shutdown complete")


class WorkerSettings:
    """ARQ Worker 配置"""

    functions = [run_claude_code_tool]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(REDIS_URL)
    max_jobs = 3
    job_timeout = 600  # 10 分钟超时
