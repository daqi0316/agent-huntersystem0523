"""MCP 工具 API — 邮件发送、日历查询/预约。

当前为仿真模式：验证输入格式 + 模拟外部服务调用。
生产环境接入真实 SMTP / CalDAV 或第三方 API。
"""

import asyncio
import re
from datetime import datetime, timezone

from fastapi import APIRouter
from pydantic import BaseModel, EmailStr, Field

router = APIRouter()

# --- 邮件 ---

EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")


class EmailSendRequest(BaseModel):
    to: EmailStr
    subject: str = Field(..., min_length=1, max_length=256)
    body: str = Field(..., min_length=1, max_length=10000)
    cc: list[EmailStr] = Field(default_factory=list)
    bcc: list[EmailStr] = Field(default_factory=list)


class EmailSendResponse(BaseModel):
    success: bool = True
    message_id: str = ""
    status: str = "sent"
    detail: str = ""


@router.post("/email/send", response_model=EmailSendResponse)
async def send_email(req: EmailSendRequest):
    """仿真发送邮件。验证收件人/主题/正文，模拟 SMTP 发送延迟。"""
    # 模拟发送延迟
    await asyncio.sleep(0.3)

    message_id = f"msg_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}_{hash(req.to + req.subject) & 0xFFFF}"

    return EmailSendResponse(
        success=True,
        message_id=message_id,
        status="sent",
        detail=f"邮件已发送至 {req.to} (主题: {req.subject[:40]})",
    )


# --- 日历 ---


class CalendarEvent(BaseModel):
    id: str = ""
    title: str = ""
    start_time: str = ""
    end_time: str = ""
    location: str = ""
    description: str = ""
    status: str = "scheduled"


class CalendarQueryRequest(BaseModel):
    date_from: str = Field(default="", description="开始日期 ISO，如 2025-06-01")
    date_to: str = Field(default="", description="结束日期 ISO，如 2025-06-30")
    limit: int = Field(20, ge=1, le=100)


class CalendarQueryResponse(BaseModel):
    success: bool = True
    events: list[CalendarEvent] = []
    total: int = 0


class CalendarBookRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=256)
    start_time: str = Field(..., description="ISO 格式开始时间")
    end_time: str = Field(..., description="ISO 格式结束时间")
    attendee_email: EmailStr
    location: str = Field(default="", max_length=256)
    description: str = Field(default="", max_length=2000)


class CalendarBookResponse(BaseModel):
    success: bool = True
    event_id: str = ""
    status: str = "scheduled"
    detail: str = ""


@router.get("/calendar/query", response_model=CalendarQueryResponse)
async def query_calendar(
    date_from: str = "",
    date_to: str = "",
    limit: int = 20,
):
    """仿真查询日历。返回模拟事件数据。"""
    events = []
    if date_from and date_to:
        # 生成几条模拟事件
        for i in range(min(limit, 3)):
            events.append(
                CalendarEvent(
                    id=f"evt_sim_{i}",
                    title=f"[模拟] 面试 #{i + 1}",
                    start_time=f"{date_from}T10:00:00",
                    end_time=f"{date_from}T11:00:00",
                    location="视频面试",
                    status="scheduled",
                )
            )

    return CalendarQueryResponse(success=True, events=events, total=len(events))


@router.post("/calendar/book", response_model=CalendarBookResponse)
async def book_calendar(req: CalendarBookRequest):
    """仿真预约日历事件。验证时间格式并模拟创建。"""
    event_id = f"evt_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}_{hash(req.title + req.attendee_email) & 0xFFFF}"

    return CalendarBookResponse(
        success=True,
        event_id=event_id,
        status="scheduled",
        detail=f"已预约「{req.title}」({req.start_time} - {req.end_time})，参与者: {req.attendee_email}",
    )
