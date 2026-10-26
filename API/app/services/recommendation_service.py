"""
Recommendations service.
"""

from decimal import Decimal
from typing import List, Optional

from sqlalchemy.orm import Session

from app.models import Recommendation, RecommendationStatus, RecommendationImpact
from app.repositories.recommendation_repo import recommendation_repo
from app import schemas


class RecommendationService:
    """Recommendations service."""

    @staticmethod
    def get_recommendations(db: Session, tenant_id: str) -> List[schemas.Recommendation]:
        """Get all recommendations for a tenant."""
        return [RecommendationService._to_schema(r) for r in recommendation_repo.get_by_tenant(db, tenant_id)]

    @staticmethod
    def get_recommendation(db: Session, tenant_id: str, recommendation_id: str) -> Optional[schemas.Recommendation]:
        """Get a specific recommendation."""
        recommendation = recommendation_repo.get_for_tenant(db, tenant_id, recommendation_id)
        return RecommendationService._to_schema(recommendation) if recommendation else None

    @staticmethod
    def filter_recommendations(
        db: Session, tenant_id: str, category: Optional[str] = None, impact: Optional[str] = None
    ) -> List[schemas.Recommendation]:
        """Filter recommendations by category and/or impact (Low/Medium/High)."""
        impact_enum = RecommendationService._parse_enum(RecommendationImpact, impact) if impact else None
        recommendations = recommendation_repo.filter_by(db, tenant_id, category, impact_enum)
        return [RecommendationService._to_schema(r) for r in recommendations]

    @staticmethod
    def get_impact(db: Session, tenant_id: str, recommendation_id: str) -> Optional[schemas.RecommendationImpact]:
        """Get savings, impact and effort for a recommendation."""
        recommendation = recommendation_repo.get_for_tenant(db, tenant_id, recommendation_id)
        if not recommendation:
            return None
        return schemas.RecommendationImpact(
            id=recommendation.id,
            savings=recommendation.savings_usd,
            impact=recommendation.impact.value,
            effort=recommendation.effort.value,
        )

    @staticmethod
    def update_status(
        db: Session, tenant_id: str, recommendation_id: str, status: str
    ) -> Optional[schemas.Recommendation]:
        """Set a recommendation's status (open / in_progress / done / dismissed)."""
        new_status = RecommendationService._parse_enum(RecommendationStatus, status)
        recommendation = recommendation_repo.update_status(db, tenant_id, recommendation_id, new_status)
        return RecommendationService._to_schema(recommendation) if recommendation else None

    @staticmethod
    def get_savings_summary(db: Session, tenant_id: str) -> schemas.SavingsSummary:
        """Total potential savings (excluding dismissed) and counts per status."""
        counts = {status: 0 for status in RecommendationStatus}
        total_savings = Decimal("0")
        for status, count, savings in recommendation_repo.get_status_totals(db, tenant_id):
            counts[status] = count
            if status != RecommendationStatus.DISMISSED:
                total_savings += Decimal(savings)
        return schemas.SavingsSummary(
            total_savings=total_savings,
            open=counts[RecommendationStatus.OPEN],
            in_progress=counts[RecommendationStatus.IN_PROGRESS],
            done=counts[RecommendationStatus.DONE],
        )

    @staticmethod
    def _parse_enum(enum_cls, value: str):
        """Match an enum by value, case-insensitively; raises ValueError if unknown."""
        for member in enum_cls:
            if member.value.lower() == value.strip().lower():
                return member
        allowed = ", ".join(m.value for m in enum_cls)
        raise ValueError(f"Invalid value '{value}'. Allowed: {allowed}")

    @staticmethod
    def _to_schema(recommendation: Recommendation) -> schemas.Recommendation:
        """Convert Recommendation model to schema."""
        return schemas.Recommendation(
            id=recommendation.id,
            title=recommendation.title,
            category=recommendation.category,
            impact=recommendation.impact.value,
            effort=recommendation.effort.value,
            savings=recommendation.savings_usd,
            description=recommendation.description,
            status=recommendation.status.value,
            steps=recommendation.steps or [],
        )


recommendation_service = RecommendationService()
