import logging

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from backend.schemas import GenerateRequest, ResumeRequest
from backend.service import run_agent_stream, resume_agent_stream
from backend.db import list_tickets, get_ticket_with_report

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
