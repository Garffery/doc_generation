import logging

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from backend.schemas import GenerateRequest, ResumeRequest
from backend.service import run_agent_stream, resume_agent_stream, retry_agent_stream
from backend.db import list_tickets, get_ticket_with_report, get_ticket

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/generate")
async def generate(request: GenerateRequest):
    """提交文档生成请求，返回 SSE 流"""
    return StreamingResponse(
        run_agent_stream(request.message),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/resume")
async def resume(request: ResumeRequest):
    """用户回答澄清问题后恢复文档生成"""
    return StreamingResponse(
        resume_agent_stream(request.thread_id, request.answers),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/tickets")
async def tickets(skip: int = 0, limit: int = 20):
    """获取工单列表"""
    items = await list_tickets(skip, limit)
    return {"items": items}


@router.get("/tickets/{ticket_id}")
async def ticket_detail(ticket_id: str):
    """获取工单详情（含报告内容）"""
    result = await get_ticket_with_report(ticket_id)
    if result is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Ticket not found")
    return result


@router.post("/retry/{ticket_id}")
async def retry(ticket_id: str):
    """进程崩溃后从 checkpoint 恢复执行"""
    from fastapi import HTTPException

    ticket = await get_ticket(ticket_id)
    if ticket is None:
        raise HTTPException(status_code=404, detail="Ticket not found")
    if ticket["status"] not in ("error", "running"):
        raise HTTPException(status_code=400, detail="Only error/running tickets can be retried")

    return StreamingResponse(
        retry_agent_stream(ticket_id, ticket["thread_id"]),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
