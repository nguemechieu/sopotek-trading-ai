from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_terminal_service
from app.core.security import get_current_user, get_db
from app.models.user import User
from app.schemas.terminal import TerminalCommandRequest, TerminalCommandResponse, TerminalManifestResponse


router = APIRouter()


@router.get("/manifest", response_model=TerminalManifestResponse)
async def get_terminal_manifest(
    terminal_id: str | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    terminal_service=Depends(get_terminal_service),
) -> TerminalManifestResponse:
    return await terminal_service.get_manifest(db, user=current_user, terminal_id=terminal_id)


@router.get("/history", response_model=list[TerminalCommandResponse])
async def get_terminal_history(
    limit: int = Query(default=25, ge=1, le=100),
    terminal_id: str | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    terminal_service=Depends(get_terminal_service),
) -> list[TerminalCommandResponse]:
    return terminal_service.get_history(current_user.id, limit=limit, terminal_id=terminal_id)


@router.post("/execute", response_model=TerminalCommandResponse, status_code=status.HTTP_200_OK)
async def execute_terminal_command(
    payload: TerminalCommandRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    terminal_service=Depends(get_terminal_service),
) -> TerminalCommandResponse:
    response = await terminal_service.execute(db, user=current_user, command=payload.command, terminal_id=payload.terminal_id)
    await db.commit()
    return response
