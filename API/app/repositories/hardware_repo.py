"""
Hardware (accelerator) repository.
"""

from datetime import timedelta
from typing import List

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import Accelerator, K8sCluster, K8sNode, ResourceHourlyMetric
from app.repositories.base import BaseRepository


class HardwareRepository(BaseRepository[Accelerator]):
    """Accelerator fleet and usage-metric queries."""

    def get_fleet(self, db: Session, tenant_id: str) -> List:
        """All accelerators for a tenant with the name of the K8s cluster they run in (if any)."""
        return (
            db.query(Accelerator, K8sCluster.name.label("cluster_name"))
            .outerjoin(K8sNode, Accelerator.node_id == K8sNode.id)
            .outerjoin(K8sCluster, K8sNode.cluster_id == K8sCluster.id)
            .filter(Accelerator.tenant_id == tenant_id)
            .order_by(Accelerator.hourly_cost_usd.desc())
            .all()
        )

    def get_usage_by_accelerator(self, db: Session, tenant_id: str, hours: int) -> dict:
        """Average usage per accelerator over the latest `hours` hours of recorded metrics.

        The window ends at the newest metric for the tenant (not "now"), so stored
        data keeps showing even if collection paused.
        """
        latest = (
            db.query(func.max(ResourceHourlyMetric.hour_ts))
            .filter(ResourceHourlyMetric.tenant_id == tenant_id)
            .scalar()
        )
        if latest is None:
            return {}

        rows = (
            db.query(
                ResourceHourlyMetric.accelerator_id,
                func.avg(ResourceHourlyMetric.avg_utilization_pct).label("utilization"),
                func.avg(ResourceHourlyMetric.avg_memory_used_gb).label("memory_used_gb"),
                func.avg(ResourceHourlyMetric.avg_temp_celsius).label("temp_c"),
                func.avg(ResourceHourlyMetric.avg_power_watts).label("power_w"),
            )
            .filter(
                ResourceHourlyMetric.tenant_id == tenant_id,
                ResourceHourlyMetric.hour_ts > latest - timedelta(hours=hours),
            )
            .group_by(ResourceHourlyMetric.accelerator_id)
            .all()
        )
        return {row.accelerator_id: row for row in rows}


hardware_repo = HardwareRepository(Accelerator)
