"""Gmail API routes."""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, EmailStr

from gsuite_api.dependencies import GmailDep

router = APIRouter()


class MessageResponse(BaseModel):
    id: str
    thread_id: str
    subject: str
    sender: str
    recipient: str
    date: str | None
    snippet: str
    is_unread: bool
    is_starred: bool
    labels: list[str]


class SendRequest(BaseModel):
    to: list[EmailStr]
    subject: str
    body: str
    cc: list[EmailStr] | None = None
    html: bool = False


@router.get("/messages")
async def list_messages(
    gmail: GmailDep,
    query: str | None = Query(None),
    limit: int = Query(25, le=100),
):
    """List messages with optional search."""
    messages = gmail.get_messages(query=query, max_results=limit)
    return {
        "messages": [
            MessageResponse(
                id=m.id,
                thread_id=m.thread_id,
                subject=m.subject,
                sender=m.sender,
                recipient=m.recipient,
                date=m.date.isoformat() if m.date else None,
                snippet=m.snippet,
                is_unread=m.is_unread,
                is_starred=m.is_starred,
                labels=m.labels,
            )
            for m in messages
        ],
        "count": len(messages),
    }


@router.get("/messages/unread")
async def list_unread(gmail: GmailDep, limit: int = Query(25, le=100)):
    """Get unread messages."""
    messages = gmail.get_unread(max_results=limit)
    return {
        "messages": [
            MessageResponse(
                id=m.id,
                thread_id=m.thread_id,
                subject=m.subject,
                sender=m.sender,
                recipient=m.recipient,
                date=m.date.isoformat() if m.date else None,
                snippet=m.snippet,
                is_unread=m.is_unread,
                is_starred=m.is_starred,
                labels=m.labels,
            )
            for m in messages
        ],
        "count": len(messages),
    }


@router.get("/messages/{message_id}")
async def get_message(message_id: str, gmail: GmailDep):
    """Get a specific message."""
    message = gmail.get_message(message_id)
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")

    return {
        "id": message.id,
        "thread_id": message.thread_id,
        "subject": message.subject,
        "sender": message.sender,
        "recipient": message.recipient,
        "date": message.date.isoformat() if message.date else None,
        "snippet": message.snippet,
        "body": message.body,
        "labels": message.labels,
    }


@router.post("/messages/send")
async def send_message(request: SendRequest, gmail: GmailDep):
    """Send an email."""
    message = gmail.send(
        to=[str(e) for e in request.to],
        subject=request.subject,
        body=request.body,
        cc=[str(e) for e in request.cc] if request.cc else None,
        html=request.html,
    )
    return {"id": message.id, "status": "sent"}


@router.post("/messages/{message_id}/read")
async def mark_as_read(message_id: str, gmail: GmailDep):
    """Mark message as read."""
    message = gmail.get_message(message_id)
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")
    message.mark_as_read()
    return {"status": "success"}


@router.get("/labels")
async def list_labels(gmail: GmailDep):
    """List all labels."""
    labels = gmail.get_labels()
    return {
        "labels": [
            {
                "id": l.id,
                "name": l.name,
                "type": l.type.value,
                "messages_unread": l.messages_unread,
            }
            for l in labels
        ],
        "count": len(labels),
    }


@router.get("/profile")
async def get_profile(gmail: GmailDep):
    """Get user profile."""
    return gmail.get_profile()
