"""
Recommendation repository.
"""

import uuid
from typing import List, Optional

from sqlalchemy import func, and_
from sqlalchemy.orm import Session

from app.models import Recommendation, RecommendationStatus, RecommendationImpact
from app.repositories.base import BaseRepository


class RecommendationRepository(BaseRepository[Recommendation]):
    """Recommendation repository."""

    def get_by_tenant(self, db: Session, tenant_id: str) -> List[Recommendation]:
        """Get all recommendations for a tenant, highest savings first."""
        return (
            db.query(Recommendation)
            .filter(Recommendation.tenant_id == tenant_id)
            .order_by(Recommendation.savings_usd.desc())
            .all()
        )

    def get_for_tenant(self, db: Session, tenant_id: str, recommendation_id: str) -> Optional[Recommendation]:
        """Get one recommendation, only if it belongs to the tenant."""
        try:
            uuid.UUID(recommendation_id)
        except ValueError:
            return None  # not a valid id, so it cannot exist (avoids a DB cast error)
        return db.query(Recommendation).filter(
            and_(Recommendation.id == recommendation_id, Recommendation.tenant_id == tenant_id)
        ).first()

    def filter_by(
        self,
        db: Session,
        tenant_id: str,
        category: Optional[str] = None,
        impact: Optional[RecommendationImpact] = None,
    ) -> List[Recommendation]:
        """Get recommendations filtered by category (case-insensitive) and/or impact."""
        query = db.query(Recommendation).filter(Recommendation.tenant_id == tenant_id)
        if category:
            query = query.filter(func.lower(Recommendation.category) == category.lower())
        if impact:
            query = query.filter(Recommendation.impact == impact)
        return query.order_by(Recommendation.savings_usd.desc()).all()

    def get_status_totals(self, db: Session, tenant_id: str) -> List:
        """Get (status, count, savings) per status for a tenant."""
        return db.query(
            Recommendation.status,
            func.count(Recommendation.id),
            func.coalesce(func.sum(Recommendation.savings_usd), 0),
        ).filter(Recommendation.tenant_id == tenant_id).group_by(Recommendation.status).all()

    def update_status(
        self, db: Session, tenant_id: str, recommendation_id: str, new_status: RecommendationStatus
    ) -> Optional[Recommendation]:
        """Update a recommendation's status."""
        recommendation = self.get_for_tenant(db, tenant_id, recommendation_id)
        if recommendation:
            recommendation.status = new_status
            db.commit()
            db.refresh(recommendation)
        return recommendation


recommendation_repo = RecommendationRepository(Recommendation)
