"""Hardware orchestration controller."""

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_current_user
from app.services.hardware_service import hardware_service

hardware_controller = APIRouter(prefix="/hardware", tags=["Hardware"], dependencies=[Depends(get_current_user)])


@hardware_controller.get("/overview")
def get_hardware_overview(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
) -> dict[str, Any]:
    """Accelerator fleet summary, per-type details (gpu/mpu/cpu/lpu) and savings suggestions."""
    return hardware_service.get_overview(db, current_user.tenant_id)
