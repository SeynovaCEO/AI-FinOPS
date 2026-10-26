"""Recommendations controller."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_current_user
from app import schemas
from app.services.recommendation_service import recommendation_service

recommendations_controller = APIRouter(prefix="/recommendations", tags=["Recommendations"], dependencies=[Depends(get_current_user)])


def _not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="Recommendation not found")


@recommendations_controller.get("", response_model=list[schemas.Recommendation])
def get_recommendations(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
) -> list[schemas.Recommendation]:
    """Get all recommendations."""
    return recommendation_service.get_recommendations(db, current_user.tenant_id)


# Literal paths are declared before "/{recommendation_id}" so they are not captured as an ID.
@recommendations_controller.get("/filter", response_model=list[schemas.Recommendation])
def filter_recommendations(
    category: Optional[str] = None,
    impact: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
) -> list[schemas.Recommendation]:
    """Filter recommendations by category and/or impact."""
    try:
        return recommendation_service.filter_recommendations(db, current_user.tenant_id, category, impact)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@recommendations_controller.get("/savings-summary", response_model=schemas.SavingsSummary)
def get_savings_summary(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
) -> schemas.SavingsSummary:
    """Get total potential savings and counts per status."""
    return recommendation_service.get_savings_summary(db, current_user.tenant_id)


@recommendations_controller.get("/sample")
def sample_recommendations():
    return {
        'data': [],
        'msg': "Recommendations fetched successfully"
    }


@recommendations_controller.get("/category/{category}", response_model=list[schemas.Recommendation])
def get_recommendations_by_category(
    category: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
) -> list[schemas.Recommendation]:
    """Get recommendations in a category."""
    return recommendation_service.filter_recommendations(db, current_user.tenant_id, category=category)


@recommendations_controller.get("/{recommendation_id}", response_model=schemas.Recommendation)
def get_recommendation(
    recommendation_id: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
) -> schemas.Recommendation:
    """Get a specific recommendation."""
    recommendation = recommendation_service.get_recommendation(db, current_user.tenant_id, recommendation_id)
    if not recommendation:
        raise _not_found()
    return recommendation


@recommendations_controller.get("/{recommendation_id}/impact", response_model=schemas.RecommendationImpact)
def get_recommendation_impact(
    recommendation_id: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
) -> schemas.RecommendationImpact:
    """Get savings, impact and effort for a recommendation."""
    impact = recommendation_service.get_impact(db, current_user.tenant_id, recommendation_id)
    if not impact:
        raise _not_found()
    return impact


@recommendations_controller.put("/{recommendation_id}/status", response_model=schemas.Recommendation)
def update_recommendation_status(
    recommendation_id: str,
    payload: schemas.RecommendationUpdate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
) -> schemas.Recommendation:
    """Set status: open, in_progress, done or dismissed."""
    try:
        recommendation = recommendation_service.update_status(
            db, current_user.tenant_id, recommendation_id, payload.status
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not recommendation:
        raise _not_found()
    return recommendation


@recommendations_controller.post("/{recommendation_id}/apply", response_model=schemas.Recommendation)
def apply_recommendation(
    recommendation_id: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
) -> schemas.Recommendation:
    """Mark a recommendation as done."""
    recommendation = recommendation_service.update_status(db, current_user.tenant_id, recommendation_id, "done")
    if not recommendation:
        raise _not_found()
    return recommendation


@recommendations_controller.post("/{recommendation_id}/dismiss", response_model=schemas.Recommendation)
def dismiss_recommendation(
    recommendation_id: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
) -> schemas.Recommendation:
    """Dismiss a recommendation."""
    recommendation = recommendation_service.update_status(db, current_user.tenant_id, recommendation_id, "dismissed")
    if not recommendation:
        raise _not_found()
    return recommendation
