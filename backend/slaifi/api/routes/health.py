"""Process health endpoint."""

from fastapi import APIRouter

router = APIRouter(tags=["system"])


@router.get("/health")
async def health() -> dict[str, str]:
    """Report process liveness without checking external dependencies."""

    return {"status": "ok"}
