"""
FinOps Platform - Database Seeder Script
Initializes tables and populates a test organization, admin user, and sample FinOps / AIOps data.
"""

from __future__ import annotations
import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import uuid

from dotenv import load_dotenv

load_dotenv()

from app.core.config import settings
from app.core.security import get_password_hash
from app.db.session import SessionLocal, engine
from app.models import (
    Base,
    Tenant,
    User,
    CloudAccount,
    K8sCluster,
    K8sNode,
    K8sPod,
    Accelerator,
    AcceleratorType,
    AcceleratorStatus,
    K8sNodeStatus,
    PodPhase,
    Agent,
    AgentStatus,
    OrchestrationJob,
    JobStatus,
    CostLineItem,
    CostLineItemType,
    Budget,
    BudgetStatus,
    Recommendation,
    RecommendationStatus,
    RecommendationImpact,
    RecommendationEffort,
    Anomaly,
    AnomalySeverity,
    AnomalyStatus,
    Team,
    CostAllocationRule,
)


# Sample cost data (mirrors App/public/fakedata.json so pages look the same after switching to the DB).
# (service, provider, line item type, latest monthly cost, month-over-month trend %, usage per month, unit, team)
SAMPLE_SERVICES = [
    ("EC2 Instances", "aws", CostLineItemType.COMPUTE, 68500, 12.3, 1240, "vCPU-Hrs", "platform-engineering"),
    ("GKE Clusters", "gcp", CostLineItemType.COMPUTE, 34200, 22.1, 5840, "Node-Hrs", "platform-engineering"),
    ("S3 Storage", "aws", CostLineItemType.STORAGE, 28400, -2.4, 450, "TB-Mo", "security"),
    ("Azure VMs", "azure", CostLineItemType.COMPUTE, 24800, 9.7, 380, "Instances", "data-science"),
    ("Cloud SQL", "gcp", CostLineItemType.OTHER, 18900, 5.2, 12, "Instances", "data-science"),
    ("RDS Instances", "aws", CostLineItemType.OTHER, 16200, 3.1, 24, "Instances", "qa"),
    ("Azure Blob", "azure", CostLineItemType.STORAGE, 14800, -1.8, 280, "TB-Mo", "security"),
    ("Lambda Functions", "aws", CostLineItemType.COMPUTE, 12600, 18.4, 45000000, "Requests", "devops"),
    ("Cloud CDN", "gcp", CostLineItemType.NETWORK, 11200, 25.6, 890, "TB-Egress", "frontend"),
    ("Azure AKS", "azure", CostLineItemType.COMPUTE, 9800, 14.2, 2160, "Node-Hrs", "devops"),
]
SAMPLE_MONTHS = 12

# (team tag, name, department, variance % of actual vs allocated budget)
SAMPLE_TEAMS = [
    ("platform-engineering", "Platform Engineering", "Engineering", 8.7),
    ("data-science", "Data Science", "Engineering", -10.5),
    ("frontend", "Frontend", "Engineering", -5.4),
    ("devops", "DevOps", "Operations", 10.0),
    ("qa", "QA", "Operations", -11.4),
    ("security", "Security", "Operations", -4.2),
]

# (name, limit, spent, status, owner)
SAMPLE_BUDGETS = [
    ("Compute Budget", 130000, 120000, BudgetStatus.AT_RISK, "Platform Engineering"),
    ("Storage Budget", 60000, 54000, BudgetStatus.UNDER_BUDGET, "Data Science"),
    ("Network Budget", 45000, 38000, BudgetStatus.UNDER_BUDGET, "DevOps"),
    ("K8s Budget", 40000, 47000, BudgetStatus.EXCEEDED, "Platform Engineering"),
    ("Database Budget", 30000, 25750, BudgetStatus.UNDER_BUDGET, "Data Science"),
]

# (service, days ago, severity, spike %, description, recent daily cost points)
SAMPLE_ANOMALIES = [
    ("Lambda Functions", 2, AnomalySeverity.CRITICAL, 340,
     "Sudden 340% spike in Lambda invocations — potential infinite loop in event trigger.",
     [10, 12, 11, 13, 12, 45, 48]),
    ("Cloud CDN", 3, AnomalySeverity.HIGH, 180,
     "CDN egress costs jumped 180% — possible cache miss storm or DDoS.",
     [20, 22, 21, 23, 42, 58, 60]),
    ("EC2 Instances", 4, AnomalySeverity.MEDIUM, 65,
     "EC2 spend increased 65% in ap-southeast-1 — unauthorized instance provisioning suspected.",
     [30, 32, 31, 33, 35, 50, 52]),
    ("Azure Blob", 6, AnomalySeverity.HIGH, 120,
     "Blob storage transactions spiked 120% — large batch job may need optimization.",
     [15, 14, 16, 15, 18, 33, 35]),
    ("RDS Instances", 8, AnomalySeverity.MEDIUM, 45,
     "RDS IOPS charges increased 45% — query optimization recommended.",
     [25, 26, 24, 27, 28, 38, 40]),
]

# (title, category, impact, effort, savings, status, description, steps)
SAMPLE_RECOMMENDATIONS = [
    ("Right-size EC2 instances in us-east-1", "Compute", RecommendationImpact.HIGH, RecommendationEffort.LOW,
     18500, RecommendationStatus.OPEN,
     "Several EC2 instances in us-east-1 average under 20% CPU over the last 30 days.",
     ["Identify underutilized instances with <20% CPU", "Migrate to smaller instance types",
      "Validate performance after migration"]),
    ("Delete orphaned EBS volumes", "Storage", RecommendationImpact.MEDIUM, RecommendationEffort.LOW,
     4200, RecommendationStatus.OPEN,
     "Unattached EBS volumes are still billed every month.",
     ["List all unattached EBS volumes", "Verify no snapshots depend on them", "Delete confirmed orphans"]),
    ("Purchase Reserved Instances for stable workloads", "Compute", RecommendationImpact.HIGH,
     RecommendationEffort.MEDIUM, 12000, RecommendationStatus.IN_PROGRESS,
     "Baseline compute usage has been stable for 90 days and is billed at on-demand rates.",
     ["Analyze 90-day usage patterns", "Identify stable baseline workloads",
      "Purchase 1-year RIs for qualifying instances"]),
    ("Optimize GKE node pool autoscaling", "Kubernetes", RecommendationImpact.HIGH, RecommendationEffort.HIGH,
     8500, RecommendationStatus.OPEN,
     "GKE node pools keep idle nodes running outside peak hours.",
     ["Review current autoscaler config", "Set appropriate min/max node counts",
      "Enable vertical pod autoscaling"]),
    ("Migrate infrequent S3 data to Glacier", "Storage", RecommendationImpact.MEDIUM, RecommendationEffort.LOW,
     2800, RecommendationStatus.DONE,
     "A large share of S3 objects has not been accessed in 90 days.",
     ["Identify objects not accessed in 90 days", "Create lifecycle policy", "Monitor retrieval patterns"]),
    ("Consolidate underused Azure SQL databases", "Database", RecommendationImpact.MEDIUM,
     RecommendationEffort.MEDIUM, 3200, RecommendationStatus.OPEN,
     "Several Azure SQL databases run below 10% DTU utilization.",
     ["Audit database utilization metrics", "Identify consolidation candidates", "Plan migration and test"]),
]


def _month_start(months_back: int) -> datetime:
    """First day (UTC) of the month `months_back` months before the current one."""
    now = datetime.now(timezone.utc)
    year, month = now.year, now.month - months_back
    while month <= 0:
        month += 12
        year -= 1
    return datetime(year, month, 1, tzinfo=timezone.utc)


def seed_cost_data(db, tenant: Tenant) -> None:
    """Seed cost line items, teams with allocation rules, extra budgets and anomalies.

    Each part is skipped when its data already exists, so the seeder can be re-run safely.
    """
    accounts = {
        acc.provider: acc
        for acc in db.query(CloudAccount).filter(CloudAccount.tenant_id == tenant.id).all()
    }

    # Cost line items: one row per service per month; each month grows by the service's trend
    if db.query(CostLineItem).filter(CostLineItem.tenant_id == tenant.id).count() == 0:
        items = []
        for service, provider, item_type, latest_cost, trend, usage, unit, team in SAMPLE_SERVICES:
            for months_back in range(SAMPLE_MONTHS):
                factor = Decimal(str((1 + trend / 100) ** months_back))
                items.append(CostLineItem(
                    tenant_id=tenant.id,
                    cloud_account_id=accounts[provider].id,
                    line_item_type=item_type,
                    service=service,
                    resource_id=f"{provider}-{service.lower().replace(' ', '-')}",
                    usage_start=_month_start(months_back),
                    usage_end=_month_start(months_back - 1),
                    usage_amount=(Decimal(usage) / factor).quantize(Decimal("0.000001")),
                    usage_unit=unit,
                    cost_usd=(Decimal(latest_cost) / factor).quantize(Decimal("0.01")),
                    tags={"team": team, "env": "production"},
                ))
        db.add_all(items)
        db.flush()
        print(f"[OK] Seeded {len(items)} cost line items ({len(SAMPLE_SERVICES)} services x {SAMPLE_MONTHS} months).")
    else:
        print("[OK] Cost line items already present.")

    # Teams + one allocation rule per team (matches cost line items by their 'team' tag).
    # Allocated budget is derived from the team's seeded spend so the variance matches the sample.
    if db.query(Team).filter(Team.tenant_id == tenant.id).count() == 0:
        for tag, name, department, variance in SAMPLE_TEAMS:
            actual = sum(
                (item.cost_usd for item in db.query(CostLineItem).filter(
                    CostLineItem.tenant_id == tenant.id,
                    CostLineItem.tags["team"].astext == tag,
                )),
                Decimal("0"),
            )
            team = Team(
                tenant_id=tenant.id,
                name=name,
                department=department,
                allocated_budget_usd=(actual / Decimal(str(1 + variance / 100))).quantize(Decimal("0.01")),
            )
            db.add(team)
            db.flush()
            db.add(CostAllocationRule(
                tenant_id=tenant.id,
                name=f"{name} tag rule",
                tag_key="team",
                tag_value=tag,
                team_id=team.id,
                category="Compute" if department == "Engineering" else "Operations",
            ))
        print(f"[OK] Seeded {len(SAMPLE_TEAMS)} teams with cost allocation rules.")
    else:
        print("[OK] Teams already present.")

    existing_budgets = {
        name for (name,) in db.query(Budget.name).filter(Budget.tenant_id == tenant.id)
    }
    new_budgets = [
        Budget(
            tenant_id=tenant.id,
            name=name,
            limit_usd=Decimal(limit),
            current_spend_usd=Decimal(spent),
            status=status,
            owner=owner,
        )
        for name, limit, spent, status, owner in SAMPLE_BUDGETS
        if name not in existing_budgets
    ]
    db.add_all(new_budgets)
    print(f"[OK] Seeded {len(new_budgets)} budgets ({len(SAMPLE_BUDGETS) - len(new_budgets)} already present).")

    existing_anomalies = {
        desc for (desc,) in db.query(Anomaly.description).filter(Anomaly.tenant_id == tenant.id)
    }
    now_utc = datetime.now(timezone.utc)
    new_anomalies = [
        Anomaly(
            tenant_id=tenant.id,
            service=service,
            detected_at=now_utc - timedelta(days=days_ago),
            severity=severity,
            spike_percentage=Decimal(spike),
            description=description,
            data=data,
            status=AnomalyStatus.OPEN,
        )
        for service, days_ago, severity, spike, description, data in SAMPLE_ANOMALIES
        if description not in existing_anomalies
    ]
    db.add_all(new_anomalies)
    print(f"[OK] Seeded {len(new_anomalies)} anomalies ({len(SAMPLE_ANOMALIES) - len(new_anomalies)} already present).")

    existing_recommendations = {
        title for (title,) in db.query(Recommendation.title).filter(Recommendation.tenant_id == tenant.id)
    }
    new_recommendations = [
        Recommendation(
            tenant_id=tenant.id,
            title=title,
            category=category,
            impact=impact,
            effort=effort,
            savings_usd=Decimal(savings),
            status=status,
            description=description,
            steps=steps,
        )
        for title, category, impact, effort, savings, status, description, steps in SAMPLE_RECOMMENDATIONS
        if title not in existing_recommendations
    ]
    db.add_all(new_recommendations)
    print(f"[OK] Seeded {len(new_recommendations)} recommendations "
          f"({len(SAMPLE_RECOMMENDATIONS) - len(new_recommendations)} already present).")


def seed_database() -> None:
    print("=" * 60)
    print("AI FinOps Platform - Database Seeder")
    print("Database:", settings.SQLALCHEMY_DATABASE_URI)
    print("=" * 60)

    # 1. Create all schema tables
    print("[1/7] Creating database tables...")
    Base.metadata.create_all(bind=engine)
    print("[OK] Database tables verified/created successfully.")

    db = SessionLocal()
    try:
        # 2. Check / Create Tenant
        print("[2/7] Checking tenant organization...")
        tenant_slug = "finops-corp"
        tenant = db.query(Tenant).filter(Tenant.slug == tenant_slug).first()

        if not tenant:
            tenant = Tenant(
                name="FinOps Enterprise Corp",
                slug=tenant_slug,
                plan="enterprise",
                is_active=True,
                metadata_={
                    "industry": "Artificial Intelligence / Cloud Infrastructure",
                    "region": "Global",
                    "admin_name": "FinOps Admin",
                },
            )
            db.add(tenant)
            db.flush()
            print(f"[OK] Created Organization: '{tenant.name}' (ID: {tenant.id}, Slug: {tenant.slug})")
        else:
            print(f"[OK] Existing Organization found: '{tenant.name}' (ID: {tenant.id})")

        # 3. Check / Create Test User
        print("[3/7] Checking test user account...")
        test_email = "testuser@finops.com"
        test_password = "admin@123"

        user = (
            db.query(User)
            .filter(User.tenant_id == tenant.id, User.email == test_email)
            .first()
        )

        if not user:
            user = User(
                email=test_email,
                password_hash=get_password_hash(test_password),
                role="admin",
                tenant_id=tenant.id,
                is_active=True,
            )
            db.add(user)
            db.flush()
            print(f"[OK] Created Test User: {test_email} (Role: {user.role}, ID: {user.id})")
        else:
            user.password_hash = get_password_hash(test_password)
            user.is_active = True
            db.flush()
            print(f"[OK] Updated existing Test User: {test_email}")

        # 4. Seed Cloud Accounts
        print("[4/7] Seeding multi-cloud accounts...")
        existing_accounts = db.query(CloudAccount).filter(CloudAccount.tenant_id == tenant.id).count()
        if existing_accounts == 0:
            aws_acc = CloudAccount(
                tenant_id=tenant.id,
                provider="aws",
                account_id="123456789012",
                alias="AWS AI Production",
                currency="USD",
                is_active=True,
            )
            gcp_acc = CloudAccount(
                tenant_id=tenant.id,
                provider="gcp",
                account_id="gcp-finops-prod-01",
                alias="GCP Vertex & TPU Cluster",
                currency="USD",
                is_active=True,
            )
            azure_acc = CloudAccount(
                tenant_id=tenant.id,
                provider="azure",
                account_id="sub-8899-2211-azure",
                alias="Azure OpenAI Services",
                currency="USD",
                is_active=True,
            )
            db.add_all([aws_acc, gcp_acc, azure_acc])
            db.flush()
            print("[OK] Seeded 3 Cloud Accounts: AWS, GCP, Azure")
        else:
            print(f"[OK] Cloud accounts already present ({existing_accounts} accounts).")

        # 5. Seed Accelerators (GPU/TPU/LPU) & Kubernetes Infrastructure
        print("[5/7] Seeding AI Accelerators & K8s clusters...")
        existing_clusters = db.query(K8sCluster).filter(K8sCluster.tenant_id == tenant.id).count()
        if existing_clusters == 0:
            cluster = K8sCluster(
                tenant_id=tenant.id,
                name="ai-inference-prod-us",
                provider="gcp",
                region="us-central1",
                k8s_version="1.29.2",
                labels={"env": "production", "tier": "gpu-accelerated"},
            )
            db.add(cluster)
            db.flush()

            node1 = K8sNode(
                tenant_id=tenant.id,
                cluster_id=cluster.id,
                name="gke-node-h100-pool-1",
                instance_type="a3-highgpu-8g",
                status=K8sNodeStatus.READY,
            )
            node2 = K8sNode(
                tenant_id=tenant.id,
                cluster_id=cluster.id,
                name="gke-node-a100-pool-2",
                instance_type="a2-highgpu-4g",
                status=K8sNodeStatus.READY,
            )
            db.add_all([node1, node2])
            db.flush()

            # Pods
            pod1 = K8sPod(
                tenant_id=tenant.id,
                cluster_id=cluster.id,
                node_id=node1.id,
                namespace="llm-serving",
                name="vllm-deepseek-r1-70b-worker-0",
                phase=PodPhase.RUNNING,
            )
            pod2 = K8sPod(
                tenant_id=tenant.id,
                cluster_id=cluster.id,
                node_id=node2.id,
                namespace="agent-ops",
                name="agent-orchestrator-service-1",
                phase=PodPhase.RUNNING,
            )
            db.add_all([pod1, pod2])

            # Accelerators
            h100_gpu = Accelerator(
                tenant_id=tenant.id,
                node_id=node1.id,
                accelerator_type=AcceleratorType.GPU,
                model="NVIDIA H100 SXM5",
                vendor="NVIDIA",
                device_id="GPU-H100-001",
                vram_gb=80,
                compute_units=132,
                status=AcceleratorStatus.IN_USE,
                hourly_cost_usd=Decimal("3.85"),
                extra={"pcie_id": "0000:00:04.0"},
            )
            a100_gpu = Accelerator(
                tenant_id=tenant.id,
                node_id=node2.id,
                accelerator_type=AcceleratorType.GPU,
                model="NVIDIA A100-SXM4-80GB",
                vendor="NVIDIA",
                device_id="GPU-A100-002",
                vram_gb=80,
                compute_units=108,
                status=AcceleratorStatus.IN_USE,
                hourly_cost_usd=Decimal("2.95"),
                extra={"instance": "p4d.24xlarge"},
            )
            tpu_v5 = Accelerator(
                tenant_id=tenant.id,
                accelerator_type=AcceleratorType.TPU,
                model="Google TPU v5e",
                vendor="Google",
                device_id="TPU-V5E-001",
                vram_gb=32,
                compute_units=4,
                status=AcceleratorStatus.AVAILABLE,
                hourly_cost_usd=Decimal("1.20"),
                extra={"chip_count": 4},
            )
            db.add_all([h100_gpu, a100_gpu, tpu_v5])
            print("[OK] Seeded K8s Clusters, Nodes, Pods, and AI Accelerators (H100, A100, TPU v5e).")

        # 6. Seed AI Agents, Jobs, Cost Items, Budgets, and Recommendations
        print("[6/7] Seeding AI Agents, Budgets, Recommendations, and Anomalies...")
        existing_agents = db.query(Agent).filter(Agent.tenant_id == tenant.id).count()
        if existing_agents == 0:
            agent1 = Agent(
                tenant_id=tenant.id,
                name="Cost-Anomaly-Guardian-Agent",
                framework="langgraph",
                model_id="claude-3-5-sonnet",
                version="2.4.0",
                status=AgentStatus.ACTIVE,
                config={"cadence": "continuous", "budget_limit": 500},
            )
            agent2 = Agent(
                tenant_id=tenant.id,
                name="LLM-Cache-Router-Agent",
                framework="custom",
                model_id="gpt-4o",
                version="1.1.2",
                status=AgentStatus.ACTIVE,
                config={"cache_hit_rate": "42%", "savings_pct": "35%"},
            )
            db.add_all([agent1, agent2])
            db.flush()

            # Orchestration Job
            job1 = OrchestrationJob(
                tenant_id=tenant.id,
                agent_id=agent1.id,
                name="nightly-finops-token-reconciliation",
                job_type="inference-eval",
                status=JobStatus.COMPLETED,
                prompt_tokens=850000,
                completion_tokens=600000,
                started_at=datetime.now(timezone.utc) - timedelta(hours=3),
                finished_at=datetime.now(timezone.utc) - timedelta(hours=2),
                tags={"environment": "production"},
                metadata_={"total_cost_usd": 14.85},
            )
            db.add(job1)

            # Budget
            budget = Budget(
                tenant_id=tenant.id,
                name="Q1 Global Cloud & AI Workload Budget",
                limit_usd=Decimal("45000.00"),
                current_spend_usd=Decimal("28430.50"),
                owner="FinOps Admin",
                status=BudgetStatus.UNDER_BUDGET,
            )
            db.add(budget)

            # Recommendations
            rec1 = Recommendation(
                tenant_id=tenant.id,
                title="Consolidate Underutilized H100 GPU Allocations",
                category="GPU Compute",
                description="Node gke-node-h100-pool-1 averaged < 18% SM utilization between 00:00 - 06:00 UTC. Auto-suspend saves ~$1,420/month.",
                impact=RecommendationImpact.HIGH,
                effort=RecommendationEffort.LOW,
                status=RecommendationStatus.OPEN,
                savings_usd=Decimal("1420.00"),
                resource_type="GPU",
                resource_id="h100-sxm5-01",
            )
            rec2 = Recommendation(
                tenant_id=tenant.id,
                title="Migrate Batch Inference to Spot TPU Instances",
                category="AI Accelerators",
                description="Move non-latency sensitive inference pipelines from On-Demand GPUs to Preemptible Google TPU v5e.",
                impact=RecommendationImpact.HIGH,
                effort=RecommendationEffort.MEDIUM,
                status=RecommendationStatus.OPEN,
                savings_usd=Decimal("2850.00"),
                resource_type="Compute",
                resource_id="batch-inference-queue",
            )
            db.add_all([rec1, rec2])

            # Anomaly
            now_utc = datetime.now()
            anomaly = Anomaly(
                tenant_id=tenant.id,
                service="OpenAI API Gateway",
                description="Unexpected 320% token consumption jump on gpt-4o endpoints from team 'data-science'.",
                spike_percentage=Decimal("320.50"),
                severity=AnomalySeverity.HIGH,
                status=AnomalyStatus.OPEN,
                detected_at=now_utc - timedelta(hours=5),
            )
            db.add(anomaly)
            print("[OK] Seeded AI Agents, Jobs, Budget, Recommendations, and Anomalies.")

        # 7. Seed cost data, teams, budgets and anomalies used by the cost pages
        print("[7/7] Seeding cost line items, teams, budgets, anomalies, and recommendations...")
        seed_cost_data(db, tenant)

        db.commit()
        print("\n" + "=" * 60)
        print("SEEDING COMPLETED SUCCESSFULLY!")
        print("=" * 60)
        print(f"Tenant Organization : {tenant.name} ({tenant.slug})")
        print(f"Admin Test User     : {test_email}")
        print(f"Password            : {test_password}")
        print("=" * 60)

    except Exception as exc:
        db.rollback()
        print(f"\n[ERROR] Seeding failed: {exc}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    seed_database()
