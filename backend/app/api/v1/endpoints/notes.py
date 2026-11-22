"""Personal notes (ADR-060). Owner only; others get 404."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from app.api.deps import DbDep, get_chat_provider, limit_ai_summaries, require_permissions
from app.core.permissions import P
from app.core.principal import CurrentUser
from app.schemas.messaging import NoteCreate, NoteOut, NoteSummaryOut, NoteUpdate
from app.services import notes as note_service
from app.services.ai.providers.base import ChatProvider

router = APIRouter(prefix="/notes", tags=["notes"])

NotesUser = Annotated[CurrentUser, Depends(require_permissions(P.NOTES_USE))]
ProviderDep = Annotated[ChatProvider | None, Depends(get_chat_provider)]


@router.get("", response_model=list[NoteSummaryOut], summary="My notes, newest first")
async def list_notes(db: DbDep, user: NotesUser, q: str | None = None) -> list[NoteSummaryOut]:
    return await note_service.list_notes(db, user, q)


@router.post("", response_model=NoteOut, status_code=status.HTTP_201_CREATED, summary="New note")
async def create_note(body: NoteCreate, db: DbDep, user: NotesUser) -> NoteOut:
    return await note_service.create_note(db, user, body)


@router.get("/{note_id}", response_model=NoteOut, summary="One of my notes")
async def get_note(note_id: uuid.UUID, db: DbDep, user: NotesUser) -> NoteOut:
    return await note_service.get_note(db, user, note_id)


@router.patch("/{note_id}", response_model=NoteOut, summary="Edit a note")
async def update_note(note_id: uuid.UUID, body: NoteUpdate, db: DbDep, user: NotesUser) -> NoteOut:
    return await note_service.update_note(db, user, note_id, body)


@router.delete("/{note_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a note")
async def delete_note(note_id: uuid.UUID, db: DbDep, user: NotesUser) -> Response:
    await note_service.delete_note(db, user, note_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{note_id}/summary",
    response_model=NoteOut,
    summary="Summarise the note with the AI model and store the summary",
    dependencies=[Depends(limit_ai_summaries)],
)
async def summarise_note(
    note_id: uuid.UUID, db: DbDep, user: NotesUser, provider: ProviderDep
) -> NoteOut:
    return await note_service.summarise_note(db, provider, user, note_id)
