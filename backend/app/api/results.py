"""
GridWise AI - Results & Benchmarking API Router
"""

from pathlib import Path
import json
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from typing import Dict, Any

from backend.app.schemas.results import BenchmarkComparisonResponse
from backend.app.analytics.comparison import run_benchmark_comparison
from backend.app.utils.plotting import generate_all_plots

router = APIRouter(prefix="/api/results", tags=["Analytics & Results"])

RESULTS_DIR = Path(__file__).resolve().parent.parent.parent.parent / "results"


@router.get("/compare", response_model=BenchmarkComparisonResponse)
@router.post("/compare", response_model=BenchmarkComparisonResponse)
def get_benchmark_comparison():
    summary_file = RESULTS_DIR / "benchmark_summary.json"
    if summary_file.exists():
        try:
            with open(summary_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                return BenchmarkComparisonResponse(**data)
        except Exception:
            pass

    # Run fresh benchmark
    res = run_benchmark_comparison(save_json=True)
    summary_data = {
        "uncontrolled": {k: v for k, v in res["uncontrolled"].items() if not k.endswith("_history") and k != "time_labels"},
        "rule_based": {k: v for k, v in res["rule_based"].items() if not k.endswith("_history") and k != "time_labels"},
        "drl": {k: v for k, v in res["drl"].items() if not k.endswith("_history") and k != "time_labels"},
        "summary": res["summary"]
    }
    return BenchmarkComparisonResponse(**summary_data)


@router.post("/generate-plots")
def generate_plots():
    # Run comparison and generate charts
    comp = run_benchmark_comparison(save_json=True)
    files = generate_all_plots(comp)
    return {
        "status": "success",
        "plots_generated": len(files),
        "files": [Path(f).name for f in files]
    }


@router.get("/plots/{filename}")
def get_plot_image(filename: str):
    fpath = RESULTS_DIR / filename
    if not fpath.exists():
        raise HTTPException(status_code=404, detail=f"Plot '{filename}' not found.")
    return FileResponse(str(fpath), media_type="image/png")

