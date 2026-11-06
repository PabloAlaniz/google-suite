"""Gmail API routes - Full featured."""

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Response
from pydantic import BaseModel, EmailStr, Field

from gsuite_api.dependencies import GmailDep
from gsuite_api.responses import download_response
from gsuite_gmail import Message

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
    message_ids: list[str] = Field(..., min_length=1)
    add_labels: list[str] | None = None
    remove_labels: list[str] | None = None


class ReplyRequest(BaseModel):
    body: str
    html: bool = False
    signature: bool = False
    reply_all: bool = False


class ForwardRequest(BaseModel):
    to: list[EmailStr] = Field(..., min_length=1)
    body: str = ""
    include_attachments: bool = True


class DraftRequest(BaseModel):
    to: list[EmailStr]
    subject: str
    body: str
    cc: list[EmailStr] | None = None
    bcc: list[EmailStr] | None = None
    html: bool = False
    reply_to: str | None = None


class LabelRequest(BaseModel):
    name: str = Field(..., min_length=1)


class FilterRequest(BaseModel):
    criteria: dict[str, Any] = Field(..., description='e.g. {"from": "alerts@example.com"}')
    action: dict[str, Any] = Field(
        ..., description='e.g. {"addLabelIds": ["Alerts"], "removeLabelIds": ["INBOX"]}'
    )


# ========== Helper Functions ==========


def _message_to_response(m: Message) -> MessageResponse:
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


def _message_to_detail(m: Message) -> MessageDetailResponse:
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
) -> dict[str, Any]:
    """List messages with optional filters.

    Uses Gmail search query syntax:
    - `is:unread` - unread messages
    - `from:someone@example.com` - from specific sender
    - `has:attachment` - messages with attachments
    - `newer_than:7d` - from last 7 days
    """
    messages = await gmail.get_messages(query=query, labels=labels, max_results=limit)
    return {
        "messages": [_message_to_response(m) for m in messages],
        "count": len(messages),
    }


@router.get("/messages/unread")
async def list_unread(gmail: GmailDep, limit: int = Query(25, le=100)) -> dict[str, Any]:
    """Get unread messages."""
    messages = await gmail.get_unread(max_results=limit)
    return {
        "messages": [_message_to_response(m) for m in messages],
        "count": len(messages),
    }


@router.get("/messages/starred")
async def list_starred(gmail: GmailDep, limit: int = Query(25, le=100)) -> dict[str, Any]:
    """Get starred messages."""
    messages = await gmail.get_starred(max_results=limit)
    return {
        "messages": [_message_to_response(m) for m in messages],
        "count": len(messages),
    }


@router.get("/messages/important")
async def list_important(gmail: GmailDep, limit: int = Query(25, le=100)) -> dict[str, Any]:
    """Get important messages."""
    messages = await gmail.get_important(max_results=limit)
    return {
        "messages": [_message_to_response(m) for m in messages],
        "count": len(messages),
    }


@router.get("/messages/sent")
async def list_sent(gmail: GmailDep, limit: int = Query(25, le=100)) -> dict[str, Any]:
    """Get sent messages."""
    messages = await gmail.get_sent(max_results=limit)
    return {
        "messages": [_message_to_response(m) for m in messages],
        "count": len(messages),
    }


@router.get("/messages/{message_id}")
async def get_message(message_id: str, gmail: GmailDep) -> MessageDetailResponse:
    """Get a specific message with full body and attachments."""
    message = await gmail.get_message(message_id)
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")
    return _message_to_detail(message)


@router.post("/messages/send")
async def send_message(request: SendRequest, gmail: GmailDep) -> dict[str, Any]:
    """Send an email.

    Set `reply_to` to a message ID to reply to an existing message.
    Set `thread_id` to keep the reply in the same thread.
    """
    message = await gmail.send(
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


# ========== Batch Operations ==========
# Declared before the /messages/{message_id}/... routes: FastAPI matches in
# order, and /messages/{message_id}/read would otherwise capture
# /messages/batch/read with message_id="batch".


@router.post("/messages/batch/read")
async def batch_mark_as_read(request: BatchModifyRequest, gmail: GmailDep) -> dict[str, Any]:
    """Mark multiple messages as read (one batchModify call per 1000 IDs)."""
    count = await gmail.batch_modify(request.message_ids, remove_labels=["UNREAD"])
    return {"status": "success", "count": count}


@router.post("/messages/batch/labels")
async def batch_modify_labels(request: BatchModifyRequest, gmail: GmailDep) -> dict[str, Any]:
    """Add/remove labels (names or IDs) on multiple messages. Unknown labels are a 422."""
    count = await gmail.batch_modify(request.message_ids, request.add_labels, request.remove_labels)
    return {
        "status": "success",
        "count": count,
        "added": request.add_labels or [],
        "removed": request.remove_labels or [],
    }


# ========== Message Actions ==========


@router.post("/messages/{message_id}/read")
async def mark_as_read(message_id: str, gmail: GmailDep) -> dict[str, Any]:
    """Mark message as read."""
    message = await gmail.get_message(message_id)
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")
    await gmail.modify_message(message, remove_labels=["UNREAD"])
    return {"status": "success", "is_unread": message.is_unread}


@router.post("/messages/{message_id}/unread")
async def mark_as_unread(message_id: str, gmail: GmailDep) -> dict[str, Any]:
    """Mark message as unread."""
    message = await gmail.get_message(message_id)
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")
    await gmail.modify_message(message, add_labels=["UNREAD"])
    return {"status": "success", "is_unread": message.is_unread}


@router.post("/messages/{message_id}/star")
async def star_message(message_id: str, gmail: GmailDep) -> dict[str, Any]:
    """Star a message."""
    message = await gmail.get_message(message_id)
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")
    await gmail.modify_message(message, add_labels=["STARRED"])
    return {"status": "success", "is_starred": message.is_starred}


@router.delete("/messages/{message_id}/star")
async def unstar_message(message_id: str, gmail: GmailDep) -> dict[str, Any]:
    """Remove star from message."""
    message = await gmail.get_message(message_id)
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")
    await gmail.modify_message(message, remove_labels=["STARRED"])
    return {"status": "success", "is_starred": message.is_starred}


@router.post("/messages/{message_id}/important")
async def mark_important(message_id: str, gmail: GmailDep) -> dict[str, Any]:
    """Mark message as important."""
    message = await gmail.get_message(message_id)
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")
    await gmail.modify_message(message, add_labels=["IMPORTANT"])
    return {"status": "success", "is_important": message.is_important}


@router.delete("/messages/{message_id}/important")
async def mark_not_important(message_id: str, gmail: GmailDep) -> dict[str, Any]:
    """Remove important mark from message."""
    message = await gmail.get_message(message_id)
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")
    await gmail.modify_message(message, remove_labels=["IMPORTANT"])
    return {"status": "success", "is_important": message.is_important}


@router.delete("/messages/{message_id}")
async def trash_message(message_id: str, gmail: GmailDep) -> dict[str, Any]:
    """Move message to trash."""
    message = await gmail.get_message(message_id)
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")
    await gmail.trash(message_id)
    return {"status": "success", "message": f"Message {message_id} moved to trash"}


@router.post("/messages/{message_id}/untrash")
async def untrash_message(message_id: str, gmail: GmailDep) -> dict[str, Any]:
    """Remove message from trash."""
    message = await gmail.get_message(message_id)
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")
    await gmail.untrash(message_id)
    return {"status": "success", "message": f"Message {message_id} removed from trash"}


@router.post("/messages/{message_id}/archive")
async def archive_message(message_id: str, gmail: GmailDep) -> dict[str, Any]:
    """Archive message (remove from inbox)."""
    message = await gmail.get_message(message_id)
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")
    await gmail.modify_message(message, remove_labels=["INBOX"])
    return {"status": "success", "message": f"Message {message_id} archived"}


@router.post("/messages/{message_id}/inbox")
async def move_to_inbox(message_id: str, gmail: GmailDep) -> dict[str, Any]:
    """Move message to inbox."""
    message = await gmail.get_message(message_id)
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")
    await gmail.modify_message(message, add_labels=["INBOX"])
    return {"status": "success", "message": f"Message {message_id} moved to inbox"}


# ========== Labels on Messages ==========


@router.post("/messages/{message_id}/labels")
async def modify_labels(
    message_id: str, request: ModifyLabelsRequest, gmail: GmailDep
) -> dict[str, Any]:
    """Add or remove labels from a message."""
    message = await gmail.get_message(message_id)
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")

    # Added, then removed, as before; unknown label names are skipped
    if request.add_labels:
        await gmail.modify_message(message, add_labels=request.add_labels)
    if request.remove_labels:
        await gmail.modify_message(message, remove_labels=request.remove_labels)

    return {
        "status": "success",
        "labels": message.labels,
        "added": request.add_labels or [],
        "removed": request.remove_labels or [],
    }


# ========== Reply ==========


@router.post("/messages/{message_id}/reply")
async def reply_to_message(
    message_id: str, request: ReplyRequest, gmail: GmailDep
) -> dict[str, Any]:
    """Reply to a message (keeps thread)."""
    message = await gmail.get_message(message_id)
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")

    reply = await gmail.reply(
        message,
        request.body,
        html=request.html,
        signature=request.signature,
        reply_all=request.reply_all,
    )

    return {"id": reply.id, "thread_id": reply.thread_id, "status": "sent"}


@router.post("/messages/{message_id}/forward")
async def forward_message(
    message_id: str, request: ForwardRequest, gmail: GmailDep
) -> dict[str, Any]:
    """Forward a message (with its attachments unless include_attachments=false)."""
    message = await gmail.get_message(message_id)
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")

    sent = await gmail.forward(
        message,
        [str(e) for e in request.to],
        request.body,
        include_attachments=request.include_attachments,
    )
    return {"id": sent.id, "thread_id": sent.thread_id, "status": "sent"}


# ========== Attachments ==========


@router.get("/messages/{message_id}/attachments/{attachment_id}")
async def download_attachment(message_id: str, attachment_id: str, gmail: GmailDep) -> Response:
    """Download an attachment."""
    message = await gmail.get_message(message_id)
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")

    attachment = next((a for a in message.attachments if a.id == attachment_id), None)
    if not attachment:
        raise HTTPException(status_code=404, detail="Attachment not found")

    content = (
        attachment.download()  # small attachments come inline with the message
        if attachment.is_inline
        else await gmail.download_attachment(message_id, attachment_id)
    )

    return download_response(content, attachment.filename, attachment.mime_type)


# ========== Threads ==========


@router.get("/threads/{thread_id}")
async def get_thread(thread_id: str, gmail: GmailDep) -> ThreadResponse:
    """Get a full email thread with all messages."""
    thread = await gmail.get_thread(thread_id)
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
async def list_labels(gmail: GmailDep) -> dict[str, Any]:
    """List all labels with stats."""
    labels = await gmail.get_labels()
    return {
        "labels": [
            LabelResponse(
                id=label.id,
                name=label.name,
                type=label.type.value,
                messages_total=label.messages_total,
                messages_unread=label.messages_unread,
                threads_total=label.threads_total,
                threads_unread=label.threads_unread,
            )
            for label in labels
        ],
        "count": len(labels),
    }


# ========== Profile ==========


@router.get("/profile")
async def get_profile(gmail: GmailDep) -> dict[str, Any]:
    """Get authenticated user's profile."""
    return await gmail.get_profile()


@router.get("/threads")
async def list_threads(
    gmail: GmailDep,
    query: str | None = Query(None, description="Gmail search query"),
    limit: int = Query(25, ge=1, le=100),
) -> dict[str, Any]:
    """List conversations."""
    threads = await gmail.get_threads(query=query, max_results=limit)
    return {
        "threads": [
            {
                "id": t.id,
                "subject": t.subject,
                "snippet": t.snippet,
                "message_count": t.message_count,
                "has_unread": t.has_unread,
            }
            for t in threads
        ],
        "count": len(threads),
    }


# ========== Drafts ==========


def _draft(draft: Any) -> dict[str, Any]:
    return {"id": draft.id, "message": _message_to_response(draft.message)}


@router.get("/drafts")
async def list_drafts(gmail: GmailDep, limit: int = Query(25, ge=1, le=100)) -> dict[str, Any]:
    """List drafts."""
    drafts = await gmail.list_drafts(max_results=limit)
    return {"drafts": [_draft(d) for d in drafts], "count": len(drafts)}


@router.post("/drafts")
async def create_draft(request: DraftRequest, gmail: GmailDep) -> dict[str, Any]:
    """Save a draft."""
    draft = await gmail.create_draft(
        to=[str(e) for e in request.to],
        subject=request.subject,
        body=request.body,
        cc=[str(e) for e in request.cc] if request.cc else None,
        bcc=[str(e) for e in request.bcc] if request.bcc else None,
        html=request.html,
        reply_to=request.reply_to,
    )
    return _draft(draft)


@router.get("/drafts/{draft_id}")
async def get_draft(draft_id: str, gmail: GmailDep) -> dict[str, Any]:
    """Get a draft."""
    draft = await gmail.get_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")
    return _draft(draft)


@router.post("/drafts/{draft_id}/send")
async def send_draft(draft_id: str, gmail: GmailDep) -> dict[str, Any]:
    """Send a draft."""
    sent = await gmail.send_draft(draft_id)
    return {"id": sent.id, "thread_id": sent.thread_id, "status": "sent"}


@router.delete("/drafts/{draft_id}")
async def delete_draft(draft_id: str, gmail: GmailDep) -> dict[str, Any]:
    """Discard a draft."""
    if not await gmail.delete_draft(draft_id):
        raise HTTPException(status_code=404, detail="Draft not found")
    return {"id": draft_id, "deleted": True}


# ========== Label management ==========


@router.post("/labels")
async def create_label(request: LabelRequest, gmail: GmailDep) -> LabelResponse:
    """Create a label ("Parent/Child" nests it)."""
    label = await gmail.create_label(request.name)
    return LabelResponse(
        id=label.id,
        name=label.name,
        type=label.type.value,
        messages_total=label.messages_total,
        messages_unread=label.messages_unread,
        threads_total=label.threads_total,
        threads_unread=label.threads_unread,
    )


@router.patch("/labels/{label}")
async def rename_label(label: str, request: LabelRequest, gmail: GmailDep) -> dict[str, Any]:
    """Rename a label (by name or ID)."""
    renamed = await gmail.rename_label(label, request.name)
    return {"id": renamed.id, "name": renamed.name}


@router.delete("/labels/{label}")
async def delete_label(label: str, gmail: GmailDep) -> dict[str, Any]:
    """Delete a label (by name or ID); messages keep existing."""
    if not await gmail.delete_label(label):
        raise HTTPException(status_code=404, detail="Label not found")
    return {"label": label, "deleted": True}


# ========== Filters ==========


@router.get("/filters")
async def list_filters(gmail: GmailDep) -> dict[str, Any]:
    """List filters."""
    filters = await gmail.list_filters()
    return {"filters": filters, "count": len(filters)}


@router.post("/filters")
async def create_filter(request: FilterRequest, gmail: GmailDep) -> dict[str, Any]:
    """Create a filter; label names in the action are resolved to IDs."""
    return await gmail.create_filter(request.criteria, request.action)


@router.delete("/filters/{filter_id}")
async def delete_filter(filter_id: str, gmail: GmailDep) -> dict[str, Any]:
    """Delete a filter."""
    if not await gmail.delete_filter(filter_id):
        raise HTTPException(status_code=404, detail="Filter not found")
    return {"id": filter_id, "deleted": True}
