"""Gmail API routes - Full featured."""

from fastapi import APIRouter, HTTPException, Query, Response
from pydantic import BaseModel, EmailStr

from gsuite_api.dependencies import GmailDep

router = APIRouter()


# ========== Response Models ==========

class AttachmentResponse(BaseModel):
    id: str
    filename: str
    mime_type: str
    size: int


class MessageResponse(BaseModel):
    id: str
    thread_id: str
    subject: str
    sender: str
    recipient: str
    cc: list[str]
    date: str | None
    snippet: str
    is_unread: bool
    is_starred: bool
    is_important: bool
    labels: list[str]
    has_attachments: bool


class MessageDetailResponse(MessageResponse):
    body_plain: str | None
    body_html: str | None
    attachments: list[AttachmentResponse]


class ThreadMessageResponse(BaseModel):
    id: str
    subject: str
    sender: str
    date: str | None
    snippet: str
    is_unread: bool
    body_plain: str | None
    body_html: str | None


class ThreadResponse(BaseModel):
    id: str
    subject: str
    snippet: str
    message_count: int
    participants: list[str]
    has_unread: bool
    messages: list[ThreadMessageResponse]


class LabelResponse(BaseModel):
    id: str
    name: str
    type: str
    messages_total: int
    messages_unread: int
    threads_total: int
    threads_unread: int


# ========== Request Models ==========

class SendRequest(BaseModel):
    to: list[EmailStr]
    subject: str
    body: str
    cc: list[EmailStr] | None = None
    bcc: list[EmailStr] | None = None
    html: bool = False
    signature: bool = False
    reply_to: str | None = None
    thread_id: str | None = None


class ModifyLabelsRequest(BaseModel):
    add_labels: list[str] | None = None
    remove_labels: list[str] | None = None


class BatchModifyRequest(BaseModel):
    message_ids: list[str]
    add_labels: list[str] | None = None
    remove_labels: list[str] | None = None


class ReplyRequest(BaseModel):
    body: str
    html: bool = False
    signature: bool = False


# ========== Helper Functions ==========

def _message_to_response(m) -> MessageResponse:
    return MessageResponse(
        id=m.id,
        thread_id=m.thread_id,
        subject=m.subject,
        sender=m.sender,
        recipient=m.recipient,
        cc=m.cc,
        date=m.date.isoformat() if m.date else None,
        snippet=m.snippet,
        is_unread=m.is_unread,
        is_starred=m.is_starred,
        is_important=m.is_important,
        labels=m.labels,
        has_attachments=len(m.attachments) > 0,
    )


def _message_to_detail(m) -> MessageDetailResponse:
    return MessageDetailResponse(
        id=m.id,
        thread_id=m.thread_id,
        subject=m.subject,
        sender=m.sender,
        recipient=m.recipient,
        cc=m.cc,
        date=m.date.isoformat() if m.date else None,
        snippet=m.snippet,
        is_unread=m.is_unread,
        is_starred=m.is_starred,
        is_important=m.is_important,
        labels=m.labels,
        has_attachments=len(m.attachments) > 0,
        body_plain=m.plain,
        body_html=m.html,
        attachments=[
            AttachmentResponse(
                id=a.id,
                filename=a.filename,
                mime_type=a.mime_type,
                size=a.size,
            )
            for a in m.attachments
        ],
    )


# ========== Messages Routes ==========

@router.get("/messages")
async def list_messages(
    gmail: GmailDep,
    query: str | None = Query(None, description="Gmail search query"),
    labels: list[str] | None = Query(None, description="Filter by label IDs"),
    limit: int = Query(25, ge=1, le=100),
):
    """
    List messages with optional filters.
    
    Uses Gmail search query syntax:
    - `is:unread` - unread messages
    - `from:someone@example.com` - from specific sender
    - `has:attachment` - messages with attachments
    - `newer_than:7d` - from last 7 days
    """
    messages = gmail.get_messages(query=query, labels=labels, max_results=limit)
    return {
        "messages": [_message_to_response(m) for m in messages],
        "count": len(messages),
    }


@router.get("/messages/unread")
async def list_unread(gmail: GmailDep, limit: int = Query(25, le=100)):
    """Get unread messages."""
    messages = gmail.get_unread(max_results=limit)
    return {
        "messages": [_message_to_response(m) for m in messages],
        "count": len(messages),
    }


@router.get("/messages/starred")
async def list_starred(gmail: GmailDep, limit: int = Query(25, le=100)):
    """Get starred messages."""
    messages = gmail.get_starred(max_results=limit)
    return {
        "messages": [_message_to_response(m) for m in messages],
        "count": len(messages),
    }


@router.get("/messages/important")
async def list_important(gmail: GmailDep, limit: int = Query(25, le=100)):
    """Get important messages."""
    messages = gmail.get_important(max_results=limit)
    return {
        "messages": [_message_to_response(m) for m in messages],
        "count": len(messages),
    }


@router.get("/messages/sent")
async def list_sent(gmail: GmailDep, limit: int = Query(25, le=100)):
    """Get sent messages."""
    messages = gmail.get_sent(max_results=limit)
    return {
        "messages": [_message_to_response(m) for m in messages],
        "count": len(messages),
    }


@router.get("/messages/{message_id}")
async def get_message(message_id: str, gmail: GmailDep):
    """Get a specific message with full body and attachments."""
    message = gmail.get_message(message_id)
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")
    return _message_to_detail(message)


@router.post("/messages/send")
async def send_message(request: SendRequest, gmail: GmailDep):
    """
    Send an email.
    
    Set `reply_to` to a message ID to reply to an existing message.
    Set `thread_id` to keep the reply in the same thread.
    """
    message = gmail.send(
        to=[str(e) for e in request.to],
        subject=request.subject,
        body=request.body,
        cc=[str(e) for e in request.cc] if request.cc else None,
        bcc=[str(e) for e in request.bcc] if request.bcc else None,
        html=request.html,
        signature=request.signature,
        reply_to=request.reply_to,
        thread_id=request.thread_id,
    )
    return {"id": message.id, "thread_id": message.thread_id, "status": "sent"}


# ========== Message Actions ==========

@router.post("/messages/{message_id}/read")
async def mark_as_read(message_id: str, gmail: GmailDep):
    """Mark message as read."""
    message = gmail.get_message(message_id)
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")
    message.mark_as_read()
    return {"status": "success", "is_unread": message.is_unread}


@router.post("/messages/{message_id}/unread")
async def mark_as_unread(message_id: str, gmail: GmailDep):
    """Mark message as unread."""
    message = gmail.get_message(message_id)
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")
    message.mark_as_unread()
    return {"status": "success", "is_unread": message.is_unread}


@router.post("/messages/{message_id}/star")
async def star_message(message_id: str, gmail: GmailDep):
    """Star a message."""
    message = gmail.get_message(message_id)
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")
    message.star()
    return {"status": "success", "is_starred": message.is_starred}


@router.delete("/messages/{message_id}/star")
async def unstar_message(message_id: str, gmail: GmailDep):
    """Remove star from message."""
    message = gmail.get_message(message_id)
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")
    message.unstar()
    return {"status": "success", "is_starred": message.is_starred}


@router.post("/messages/{message_id}/important")
async def mark_important(message_id: str, gmail: GmailDep):
    """Mark message as important."""
    message = gmail.get_message(message_id)
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")
    message.mark_important()
    return {"status": "success", "is_important": message.is_important}


@router.delete("/messages/{message_id}/important")
async def mark_not_important(message_id: str, gmail: GmailDep):
    """Remove important mark from message."""
    message = gmail.get_message(message_id)
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")
    message.mark_not_important()
    return {"status": "success", "is_important": message.is_important}


@router.delete("/messages/{message_id}")
async def trash_message(message_id: str, gmail: GmailDep):
    """Move message to trash."""
    message = gmail.get_message(message_id)
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")
    message.trash()
    return {"status": "success", "message": f"Message {message_id} moved to trash"}


@router.post("/messages/{message_id}/untrash")
async def untrash_message(message_id: str, gmail: GmailDep):
    """Remove message from trash."""
    message = gmail.get_message(message_id)
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")
    message.untrash()
    return {"status": "success", "message": f"Message {message_id} removed from trash"}


@router.post("/messages/{message_id}/archive")
async def archive_message(message_id: str, gmail: GmailDep):
    """Archive message (remove from inbox)."""
    message = gmail.get_message(message_id)
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")
    message.archive()
    return {"status": "success", "message": f"Message {message_id} archived"}


@router.post("/messages/{message_id}/inbox")
async def move_to_inbox(message_id: str, gmail: GmailDep):
    """Move message to inbox."""
    message = gmail.get_message(message_id)
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")
    message.move_to_inbox()
    return {"status": "success", "message": f"Message {message_id} moved to inbox"}


# ========== Labels on Messages ==========

@router.post("/messages/{message_id}/labels")
async def modify_labels(message_id: str, request: ModifyLabelsRequest, gmail: GmailDep):
    """Add or remove labels from a message."""
    message = gmail.get_message(message_id)
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")
    
    if request.add_labels:
        for label in request.add_labels:
            message.add_label(label)
    
    if request.remove_labels:
        for label in request.remove_labels:
            message.remove_label(label)
    
    return {
        "status": "success",
        "labels": message.labels,
        "added": request.add_labels or [],
        "removed": request.remove_labels or [],
    }


# ========== Batch Operations ==========

@router.post("/messages/batch/read")
async def batch_mark_as_read(request: BatchModifyRequest, gmail: GmailDep):
    """Mark multiple messages as read."""
    if not request.message_ids:
        raise HTTPException(status_code=400, detail="message_ids cannot be empty")
    
    for msg_id in request.message_ids:
        msg = gmail.get_message(msg_id)
        if msg:
            msg.mark_as_read()
    
    return {
        "status": "success",
        "count": len(request.message_ids),
    }


@router.post("/messages/batch/labels")
async def batch_modify_labels(request: BatchModifyRequest, gmail: GmailDep):
    """Modify labels on multiple messages."""
    if not request.message_ids:
        raise HTTPException(status_code=400, detail="message_ids cannot be empty")
    
    for msg_id in request.message_ids:
        msg = gmail.get_message(msg_id)
        if msg:
            if request.add_labels:
                for label in request.add_labels:
                    msg.add_label(label)
            if request.remove_labels:
                for label in request.remove_labels:
                    msg.remove_label(label)
    
    return {
        "status": "success",
        "count": len(request.message_ids),
        "added": request.add_labels or [],
        "removed": request.remove_labels or [],
    }


# ========== Reply ==========

@router.post("/messages/{message_id}/reply")
async def reply_to_message(message_id: str, request: ReplyRequest, gmail: GmailDep):
    """Reply to a message (keeps thread)."""
    message = gmail.get_message(message_id)
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")
    
    reply = message.reply(
        body=request.body,
        html=request.html,
        signature=request.signature,
    )
    
    return {"id": reply.id, "thread_id": reply.thread_id, "status": "sent"}


# ========== Attachments ==========

@router.get("/messages/{message_id}/attachments/{attachment_id}")
async def download_attachment(message_id: str, attachment_id: str, gmail: GmailDep):
    """Download an attachment."""
    message = gmail.get_message(message_id)
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")
    
    attachment = next((a for a in message.attachments if a.id == attachment_id), None)
    if not attachment:
        raise HTTPException(status_code=404, detail="Attachment not found")
    
    content = attachment.download()
    
    return Response(
        content=content,
        media_type=attachment.mime_type,
        headers={
            "Content-Disposition": f'attachment; filename="{attachment.filename}"'
        },
    )


# ========== Threads ==========

@router.get("/threads/{thread_id}")
async def get_thread(thread_id: str, gmail: GmailDep):
    """Get a full email thread with all messages."""
    thread = gmail.get_thread(thread_id)
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    
    # Build participants list from all messages
    participants = set()
    has_unread = False
    for m in thread.messages:
        participants.add(m.sender)
        if m.recipient:
            participants.add(m.recipient)
        if m.is_unread:
            has_unread = True
    
    return ThreadResponse(
        id=thread.id,
        subject=thread.messages[0].subject if thread.messages else "",
        snippet=thread.snippet,
        message_count=len(thread.messages),
        participants=list(participants),
        has_unread=has_unread,
        messages=[
            ThreadMessageResponse(
                id=m.id,
                subject=m.subject,
                sender=m.sender,
                date=m.date.isoformat() if m.date else None,
                snippet=m.snippet,
                is_unread=m.is_unread,
                body_plain=m.plain,
                body_html=m.html,
            )
            for m in thread.messages
        ],
    )


# ========== Labels ==========

@router.get("/labels")
async def list_labels(gmail: GmailDep):
    """List all labels with stats."""
    labels = gmail.get_labels()
    return {
        "labels": [
            LabelResponse(
                id=l.id,
                name=l.name,
                type=l.type.value,
                messages_total=l.messages_total,
                messages_unread=l.messages_unread,
                threads_total=l.threads_total,
                threads_unread=l.threads_unread,
            )
            for l in labels
        ],
        "count": len(labels),
    }


# ========== Profile ==========

@router.get("/profile")
async def get_profile(gmail: GmailDep):
    """Get authenticated user's profile."""
    return gmail.get_profile()
