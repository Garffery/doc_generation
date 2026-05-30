import uuid
from datetime import datetime, timezone

import os

from motor.motor_asyncio import AsyncIOMotorClient

_client = AsyncIOMotorClient(os.environ.get("MONGODB_URI", "mongodb://localhost:27017"))
_db = _client["doc_generation"]
_tickets = _db["tickets"]
_reports = _db["reports"]


async def create_ticket(message: str, thread_id: str) -> str:
    ticket_id = str(uuid.uuid4())
    doc = {
        "id": ticket_id,
        "thread_id": thread_id,
        "message": message,
        "status": "pending",
        "created_at": datetime.now(timezone.utc),
    }
    await _tickets.insert_one(doc)
    return ticket_id


async def update_ticket_status(ticket_id: str, status: str) -> None:
    await _tickets.update_one({"id": ticket_id}, {"$set": {"status": status}})


async def get_ticket_id_by_thread(thread_id: str) -> str | None:
    doc = await _tickets.find_one({"thread_id": thread_id}, {"id": 1})
    return doc["id"] if doc else None


async def init_report(ticket_id: str, message: str) -> None:
    doc = {
        "ticket_id": ticket_id,
        "message": message,
        "research_brief": "",
        "draft_report": "",
        "final_report": "",
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    await _reports.insert_one(doc)


async def update_report_stage(ticket_id: str, stage: str, content: str) -> None:
    await _reports.update_one(
        {"ticket_id": ticket_id},
        {"$set": {stage: content, "updated_at": datetime.now(timezone.utc)}},
    )


async def list_tickets(skip: int = 0, limit: int = 20) -> list[dict]:
    cursor = _tickets.find(
        {}, {"_id": 0, "id": 1, "message": 1, "status": 1, "created_at": 1}
    ).sort("created_at", -1).skip(skip).limit(limit)
    return await cursor.to_list(length=limit)


async def get_ticket(ticket_id: str) -> dict | None:
    return await _tickets.find_one({"id": ticket_id}, {"_id": 0})


async def get_ticket_with_report(ticket_id: str) -> dict | None:
    ticket = await _tickets.find_one({"id": ticket_id}, {"_id": 0})
    if not ticket:
        return None
    report = await _reports.find_one({"ticket_id": ticket_id}, {"_id": 0})
    ticket["report"] = report or {}
    return ticket
