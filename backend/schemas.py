from pydantic import BaseModel, Field


class GenerateRequest(BaseModel):
    """文档生成请求"""
    message: str = Field(..., description="用户需求描述", min_length=1)


class ResumeRequest(BaseModel):
    """用户回答澄清问题后恢复生成"""
    thread_id: str = Field(..., description="会话线程ID")
    answers: str = Field(..., description="用户对澄清问题的回答")
