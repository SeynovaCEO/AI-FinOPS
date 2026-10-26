"""
Hardware orchestration service.

Builds the Hardware Orchestration page payload from the accelerator fleet and its
hourly usage metrics. Status labels, totals and savings suggestions are derived here,
not stored.
"""

from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.models import AcceleratorType
from app.repositories.hardware_repo import hardware_repo

USAGE_WINDOW_HOURS = 24
HOURS_PER_MONTH = 720

# Utilization thresholds (%) used for status labels and savings rules
SATURATED_PCT = 85
HEALTHY_PCT = 40
IDLE_PCT = 10

RIGHT_SIZE_SAVINGS_RATE = 0.5    # underutilized device -> assume half its cost can be cut
ARM_MIGRATION_SAVINGS_RATE = 0.22  # x86 -> Graviton price-performance gain

CATEGORY_LABELS = {"gpu": "GPU", "mpu": "TPU", "cpu": "CPU", "lpu": "LPU"}


def _category(accelerator) -> Optional[str]:
    """Map an accelerator to the page tab it belongs to (CPU pools are stored as OTHER)."""
    if accelerator.accelerator_type == AcceleratorType.GPU:
        return "gpu"
    if accelerator.accelerator_type == AcceleratorType.TPU:
        return "mpu"
    if accelerator.accelerator_type == AcceleratorType.LPU:
        return "lpu"
    if (accelerator.extra or {}).get("category") == "cpu":
        return "cpu"
    return None


def _status(utilization: Optional[float]) -> str:
    if utilization is None:
        return "No Data"
    if utilization >= SATURATED_PCT:
        return "Saturated"
    if utilization >= HEALTHY_PCT:
        return "Healthy"
    if utilization >= IDLE_PCT:
        return "Underutilized"
    return "Idle / Zombie"


def _avg(values: List[float]) -> float:
    return round(sum(values) / len(values), 1) if values else 0.0


def _money(value: float) -> str:
    return f"${value:,.0f} / mo"


class HardwareService:
    """Hardware orchestration service."""

    @staticmethod
    def get_overview(db: Session, tenant_id: str) -> Dict[str, Any]:
        """Summary, per-category fleet details and savings suggestions for a tenant."""
        usage = hardware_repo.get_usage_by_accelerator(db, tenant_id, USAGE_WINDOW_HOURS)
        devices: Dict[str, List[Dict[str, Any]]] = {key: [] for key in CATEGORY_LABELS}

        for accelerator, cluster_name in hardware_repo.get_fleet(db, tenant_id):
            category = _category(accelerator)
            if category is None:
                continue
            metrics = usage.get(accelerator.id)
            extra = accelerator.extra or {}
            utilization = round(float(metrics.utilization), 1) if metrics else None
            devices[category].append({
                "accelerator": accelerator,
                "extra": extra,
                "cluster": cluster_name or extra.get("cluster") or extra.get("region") or "—",
                "utilization": utilization,
                "memory_used_gb": round(float(metrics.memory_used_gb or 0)) if metrics else 0,
                "temp_c": round(float(metrics.temp_c or 0)) if metrics else 0,
                "power_w": round(float(metrics.power_w or 0)) if metrics else 0,
                "cost_per_hour": float(accelerator.hourly_cost_usd or 0),
                "status": _status(utilization),
            })

        recommendations = HardwareService._recommendations(devices)
        all_devices = [d for group in devices.values() for d in group]
        measured = [d["utilization"] for d in all_devices if d["utilization"] is not None]
        hourly_burn = sum(d["cost_per_hour"] for d in all_devices)

        return {
            "summary": {
                "totalAccelerators": len(all_devices),
                "activeCount": sum(1 for u in measured if u >= IDLE_PCT),
                "idleCount": sum(1 for u in measured if u < IDLE_PCT),
                "totalHourlyBurn": round(hourly_burn, 2),
                "avgComputeUtilization": _avg(measured),
                "monthlyHardwareSpend": round(hourly_burn * HOURS_PER_MONTH),
                "potentialMonthlySavings": round(sum(r["savings"] for r in recommendations)),
                "usageWindowHours": USAGE_WINDOW_HOURS,
            },
            "accelerators": {
                "gpu": HardwareService._gpu(devices["gpu"]),
                "mpu": HardwareService._mpu(devices["mpu"]),
                "cpu": HardwareService._cpu(devices["cpu"]),
                "lpu": HardwareService._lpu(devices["lpu"]),
            },
            "recommendations": recommendations,
        }

    @staticmethod
    def _utilizations(group: List[Dict[str, Any]]) -> List[float]:
        return [d["utilization"] for d in group if d["utilization"] is not None]

    @staticmethod
    def _hourly(group: List[Dict[str, Any]]) -> float:
        return round(sum(d["cost_per_hour"] for d in group), 2)

    @staticmethod
    def _gpu(group: List[Dict[str, Any]]) -> Dict[str, Any]:
        return {
            "overview": {
                "count": len(group),
                "avgUtilization": _avg(HardwareService._utilizations(group)),
                "totalVRAM_GB": sum(d["accelerator"].vram_gb or 0 for d in group),
                "allocatedVRAM_GB": sum(d["memory_used_gb"] for d in group),
                "hourlyCost": HardwareService._hourly(group),
            },
            "devices": [
                {
                    "id": d["accelerator"].device_id,
                    "type": d["accelerator"].model,
                    "cluster": d["cluster"],
                    "smUtil": round(d["utilization"] or 0),
                    "vramAllocatedGB": d["memory_used_gb"],
                    "vramTotalGB": d["accelerator"].vram_gb or 0,
                    "tempC": d["temp_c"],
                    "powerW": d["power_w"],
                    "costPerHour": d["cost_per_hour"],
                    "status": d["status"],
                    "model": d["extra"].get("workload", "—"),
                }
                for d in group
            ],
        }

    @staticmethod
    def _mpu(group: List[Dict[str, Any]]) -> Dict[str, Any]:
        return {
            "overview": {
                "count": sum(d["accelerator"].compute_units or 0 for d in group),  # chips
                "podSlices": len(group),
                "avgUtilization": _avg(HardwareService._utilizations(group)),
                "hourlyCost": HardwareService._hourly(group),
            },
            "devices": [
                {
                    "id": d["accelerator"].device_id,
                    "type": d["accelerator"].model,
                    "region": d["cluster"],
                    "mxuDutyCycle": round(d["utilization"] or 0),
                    "hbmThroughputGBs": d["extra"].get("hbm_throughput_gbs", 0),
                    "costPerHour": d["cost_per_hour"],
                    "status": d["status"],
                    "workload": d["extra"].get("workload", "—"),
                }
                for d in group
            ],
        }

    @staticmethod
    def _cpu(group: List[Dict[str, Any]]) -> Dict[str, Any]:
        total_cores = sum(d["accelerator"].compute_units or 0 for d in group)
        arm_cores = sum(d["accelerator"].compute_units or 0 for d in group if d["extra"].get("arch") == "arm")
        arm_pct = round(arm_cores / total_cores * 100) if total_cores else 0
        return {
            "overview": {
                "totalCores": total_cores,
                "avgUtilization": _avg(HardwareService._utilizations(group)),
                "architectureBreakdown": f"{arm_pct}% ARM / {100 - arm_pct}% x86" if total_cores else "—",
                "hourlyCost": HardwareService._hourly(group),
            },
            "devices": [
                {
                    "id": d["accelerator"].device_id,
                    "type": d["accelerator"].model,
                    "cores": d["accelerator"].compute_units or 0,
                    "utilization": round(d["utilization"] or 0),
                    "memoryGB": d["extra"].get("memory_gb", 0),
                    "costPerHour": d["cost_per_hour"],
                    "status": d["status"],
                    "role": d["extra"].get("role", "—"),
                }
                for d in group
            ],
        }

    @staticmethod
    def _lpu(group: List[Dict[str, Any]]) -> Dict[str, Any]:
        token_costs = [d["extra"]["cost_per_million_tokens"] for d in group if "cost_per_million_tokens" in d["extra"]]
        return {
            "overview": {
                "count": len(group),
                "avgTokensPerSec": round(_avg([d["extra"].get("throughput_tok_sec", 0) for d in group])),
                "sramBandwidthTBps": sum(d["extra"].get("sram_bandwidth_tbps", 0) for d in group),
                "minCostPerMillionTokens": min(token_costs) if token_costs else None,
                "hourlyCost": HardwareService._hourly(group),
            },
            "devices": [
                {
                    "id": d["accelerator"].device_id,
                    "type": d["accelerator"].model,
                    "targetModel": d["extra"].get("workload", "—"),
                    "throughputTokSec": d["extra"].get("throughput_tok_sec", 0),
                    "latencyFirstTokenMs": d["extra"].get("ttft_ms", 0),
                    "costPerMillionTokens": d["extra"].get("cost_per_million_tokens", 0),
                    "status": d["status"],
                }
                for d in group
            ],
        }

    @staticmethod
    def _recommendations(devices: Dict[str, List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
        """Rule-based savings suggestions, highest savings first."""
        recs = []
        for category, group in devices.items():
            label = CATEGORY_LABELS[category]
            for d in group:
                util = d["utilization"]
                if util is None:
                    continue
                device_id = d["accelerator"].device_id
                monthly_cost = d["cost_per_hour"] * HOURS_PER_MONTH

                if util < IDLE_PCT and monthly_cost > 0:
                    recs.append({
                        "type": f"{label} Idle Shutdown",
                        "severity": "High",
                        "savings": monthly_cost,
                        "description": f"{device_id} averaged {util}% utilization over the last "
                                       f"{USAGE_WINDOW_HOURS} hours. Auto-hibernate or return to spot pool.",
                    })
                elif util < HEALTHY_PCT and category in ("gpu", "mpu"):
                    recs.append({
                        "type": f"Right-size Underutilized {label}",
                        "severity": "Medium",
                        "savings": monthly_cost * RIGHT_SIZE_SAVINGS_RATE,
                        "description": f"{device_id} averaged {util}% utilization. Move its workload to a "
                                       f"smaller instance or share the device (MIG / time-slicing).",
                    })

                if category == "cpu" and d["extra"].get("arch") == "x86":
                    recs.append({
                        "type": "ARM CPU Migration",
                        "severity": "Low",
                        "savings": monthly_cost * ARM_MIGRATION_SAVINGS_RATE,
                        "description": f"Migrate {device_id} ({d['extra'].get('role', 'x86 pool')}) to AWS "
                                       f"Graviton4 for about 22% better price-performance.",
                    })

        recs.sort(key=lambda r: r["savings"], reverse=True)
        for rec in recs:
            rec["savings"] = round(rec["savings"])
            rec["impact"] = _money(rec["savings"])
        return recs


hardware_service = HardwareService()
