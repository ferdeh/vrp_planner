"""User guide routes."""

from __future__ import annotations

from io import BytesIO

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.services.solver_guide_pdf_service import build_solver_guide_pdf

router = APIRouter(prefix="/api/v1/user-guide", tags=["user-guide"])


@router.get("/solver-guide.pdf")
def download_solver_guide_pdf() -> StreamingResponse:
    """Download solver.md as a branded PDF document."""

    try:
        pdf_content = build_solver_guide_pdf()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return StreamingResponse(
        BytesIO(pdf_content),
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="vrp-planner-solver-guide.pdf"'},
    )
