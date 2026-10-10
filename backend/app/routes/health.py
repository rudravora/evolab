from fastapi import APIRouter, Request
from pydantic import BaseModel

from .. import __version__
from ..ids import now_iso

router = APIRouter(tags=["health"])


class Health(BaseModel):
    status: str
    version: str
    time: str
    mode: str          # "live" or "simulated" (scripted AI, labelled in the UI per D-027)


@router.get("/health", response_model=Health)
def health(request: Request) -> Health:
    """No auth. Used by Voroa and UseShipReady uptime checks."""
    mode = "simulated" if request.app.state.settings.simulation else "live"
    return Health(status="ok", version=__version__, time=now_iso(), mode=mode)
