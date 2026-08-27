"""
Saved-library API (Phase 11).

Every route here requires a signed-in user (Depends(get_current_user) → 401
when auth isn't configured or the token is missing/invalid). Handlers are thin:
they validate input and delegate to app/library_repository.py, which does all
the user-scoped data access. Anonymous research is unaffected — it lives on the
/research* endpoints in app/main.py and never touches this router.

Routes
------
  GET    /library                list saved reports (search / folder / starred / tag filters)
  POST   /library                save a finished research result
  GET    /library/{id}           full saved report (reconstructed ResearchResult)
  GET    /library/{id}/status    lightweight job-status poll (no report body)
  PATCH  /library/{id}           rename / star / move to folder
  DELETE /library/{id}           delete a saved report
  PUT    /library/{id}/tags      replace a report's tags

  GET    /folders                list the user's folders
  POST   /folders                create (idempotent) a folder
  DELETE /folders/{id}           delete a folder (its reports are un-filed, not deleted)

  GET    /tags                   list the user's tags
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app import library_repository as repo
from app.auth import AuthUser, CurrentUser
from app.db.session import get_db_session

router = APIRouter(tags=["library"])


# --------------------------------------------------------------------------- #
# Request bodies
# --------------------------------------------------------------------------- #

class SaveLibraryRequest(BaseModel):
    """A finished result plus the run settings, straight from the SSE
    'complete' event. `result` is the serialized ResearchResult dict."""

    result: dict[str, Any]
    citation_style: str = "apa"
    target_language: str = "English"
    num_sub_questions: Optional[int] = None
    max_results_per_subquestion: int = 5
    title: Optional[str] = Field(default=None, max_length=200)


class UpdateSessionRequest(BaseModel):
    """Partial update — only the provided fields change. `clear_folder` moves
    the report out of any folder (which `folder_id=None` alone can't express,
    since None also means 'leave unchanged')."""

    title: Optional[str] = Field(default=None, max_length=200)
    starred: Optional[bool] = None
    folder_id: Optional[str] = None
    clear_folder: bool = False


class TagsRequest(BaseModel):
    tags: list[str] = Field(default_factory=list)


class FolderRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)


# --------------------------------------------------------------------------- #
# Library entries
# --------------------------------------------------------------------------- #

@router.get("/library")
def list_library(
    user: AuthUser = CurrentUser,
    db: Session = Depends(get_db_session),
    search: Optional[str] = Query(default=None),
    folder_id: Optional[str] = Query(default=None),
    starred: Optional[bool] = Query(default=None),
    tag: Optional[str] = Query(default=None),
) -> list[dict]:
    return repo.list_sessions_for_user(
        db, user.id, search=search, folder_id=folder_id, starred=starred, tag=tag
    )


@router.post("/library", status_code=status.HTTP_201_CREATED)
def save_library(
    req: SaveLibraryRequest,
    user: AuthUser = CurrentUser,
    db: Session = Depends(get_db_session),
) -> dict:
    session = repo.save_result_for_user(
        db,
        user.id,
        req.result,
        citation_style=req.citation_style,
        target_language=req.target_language,
        num_sub_questions=req.num_sub_questions,
        max_results_per_subquestion=req.max_results_per_subquestion,
        title=req.title,
    )
    return {"id": session.id}


@router.get("/library/{session_id}")
def get_library_entry(
    session_id: str,
    user: AuthUser = CurrentUser,
    db: Session = Depends(get_db_session),
) -> dict:
    entry = repo.get_session_result(db, user.id, session_id)
    if entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found.")
    return entry


@router.get("/library/{session_id}/status")
def get_library_entry_status(
    session_id: str,
    user: AuthUser = CurrentUser,
    db: Session = Depends(get_db_session),
) -> dict:
    """Job-status poll for a saved run: id, status, error_text, timestamps —
    without loading the (large) report body. Lets the frontend track a run's
    lifecycle (running → complete/error) cheaply."""
    st = repo.get_session_status(db, user.id, session_id)
    if st is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found.")
    return st


@router.patch("/library/{session_id}")
def update_library_entry(
    session_id: str,
    req: UpdateSessionRequest,
    user: AuthUser = CurrentUser,
    db: Session = Depends(get_db_session),
) -> dict:
    if req.title is not None:
        if not repo.rename_session(db, user.id, session_id, req.title):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found.")

    if req.starred is not None:
        if not repo.set_starred(db, user.id, session_id, req.starred):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found.")

    if req.clear_folder:
        if not repo.move_to_folder(db, user.id, session_id, None):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found.")
    elif req.folder_id is not None:
        if not repo.move_to_folder(db, user.id, session_id, req.folder_id):
            # False here means either the report or the target folder isn't the
            # caller's — can't tell which, so report it as a bad request.
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Could not move report — unknown folder or report.",
            )

    return {"ok": True, "id": session_id}


@router.delete("/library/{session_id}")
def delete_library_entry(
    session_id: str,
    user: AuthUser = CurrentUser,
    db: Session = Depends(get_db_session),
) -> dict:
    if not repo.delete_session(db, user.id, session_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found.")
    return {"ok": True}


@router.put("/library/{session_id}/tags")
def set_library_tags(
    session_id: str,
    req: TagsRequest,
    user: AuthUser = CurrentUser,
    db: Session = Depends(get_db_session),
) -> dict:
    names = repo.set_session_tags(db, user.id, session_id, req.tags)
    if names is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found.")
    return {"tags": names}


# --------------------------------------------------------------------------- #
# Folders
# --------------------------------------------------------------------------- #

@router.get("/folders")
def list_folders(
    user: AuthUser = CurrentUser,
    db: Session = Depends(get_db_session),
) -> list[dict]:
    return repo.list_folders(db, user.id)


@router.post("/folders", status_code=status.HTTP_201_CREATED)
def create_folder(
    req: FolderRequest,
    user: AuthUser = CurrentUser,
    db: Session = Depends(get_db_session),
) -> dict:
    try:
        return repo.create_folder(db, user.id, req.name)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.delete("/folders/{folder_id}")
def delete_folder(
    folder_id: str,
    user: AuthUser = CurrentUser,
    db: Session = Depends(get_db_session),
) -> dict:
    if not repo.delete_folder(db, user.id, folder_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Folder not found.")
    return {"ok": True}


# --------------------------------------------------------------------------- #
# Tags
# --------------------------------------------------------------------------- #

@router.get("/tags")
def list_tags(
    user: AuthUser = CurrentUser,
    db: Session = Depends(get_db_session),
) -> list[dict]:
    return repo.list_tags(db, user.id)
