from fastapi import APIRouter, Depends, Response
from typing import Dict, Any, List
from sqlalchemy.orm import Session

from backend.app.schemas.analytics_schema import AnalyticsSummaryResponse
from backend.app.services.analytics_service import AnalyticsService
from backend.app.database.database import get_db
from backend.app.models.database_models import Simulation, AnalyticsRecord

def create_analytics_router(sim_service):
    router = APIRouter(prefix="/api/analytics", tags=["Analytics & Reports"])

    @router.get("/summary", response_model=AnalyticsSummaryResponse)
    def get_summary():
        return AnalyticsService.compute_analytics(sim_service.engine.history)

    @router.get("/history")
    def get_simulation_history(db: Session = Depends(get_db)):
        sims = db.query(Simulation).order_by(Simulation.created_at.desc()).limit(10).all()
        result = []
        for s in sims:
            an = db.query(AnalyticsRecord).filter(AnalyticsRecord.simulation_id == s.id).first()
            result.append({
                "simulation_id": s.id,
                "name": s.name,
                "scenario": s.scenario,
                "status": s.status,
                "total_evs": s.total_evs,
                "timestep_minutes": s.timestep_minutes,
                "created_at": s.created_at.isoformat() if s.created_at else None,
                "metrics": {
                    "total_charging_cost_inr": an.total_charging_cost_inr if an else 0.0,
                    "peak_grid_load_kw": an.peak_grid_load_kw if an else 0.0,
                    "renewable_utilization_pct": an.renewable_utilization_pct if an else 0.0,
                    "v2g_revenue_earned_inr": an.v2g_revenue_earned_inr if an else 0.0
                } if an else None
            })
        return {"simulations": result}

    @router.get("/export")
    def export_report_markdown(format: str = "markdown"):
        report = sim_service.generate_report()
        if format == "json":
            return report
        return Response(
            content=report["markdown_report"],
            media_type="text/markdown",
            headers={"Content-Disposition": f"attachment; filename=gridwise_report_{sim_service.engine.simulation_id[:8]}.md"}
        )

    return router
