from fastapi import APIRouter
from pydantic import BaseModel

from .. import __version__
from ..ids import now_iso

router = APIRouter(tags=["health"])


class Health(BaseModel):
    status: str
    version: str
    time: str


@router.get("/health", response_model=Health)
def health() -> Health:
    """No auth. Used by Voroa and UseShipReady uptime checks."""
    return Health(status="ok", version=__version__, time=now_iso())
