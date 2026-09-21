from fastapi import APIRouter, HTTPException
from typing import Dict, Any, List
from pydantic import BaseModel
from backend.app.schemas.decision_schema import AIDecisionRequest, AIDecisionResponse
from backend.app.services.openai_service import OpenAIService
from backend.app.simulator.ev_simulator import EVDigitalTwin
from backend.app.ai.constraints import ConstraintEngine
from backend.app.ai.environment import EVChargingGymEnv

import asyncio
import uuid
from datetime import datetime

class TrainRequest(BaseModel):
    episodes: int = 50
    background: bool = False

def create_ai_router(sim_service):
    router = APIRouter(prefix="/api/ai", tags=["AI Engine & Training Center"])
    active_jobs: Dict[str, Dict[str, Any]] = {}

    @router.get("/status")
    def get_ai_status():
        ppo = sim_service.engine.rl_agent.ppo
        return {
            "algorithm": "PPO (Proximal Policy Optimization)",
            "framework": "Gymnasium 1.3.0 + Neural Actor-Critic Policy",
            "action_space": ["0: IDLE", "1: CHARGE", "2: DISCHARGE (V2G)"],
            "observation_space_dim": 10,
            "safety_constraint_layer": "ACTIVE",
            "episodes_trained": ppo.episodes_trained,
            "mean_reward": ppo.mean_reward,
            "best_reward": ppo.best_reward,
            "training_status": ppo.model_status,
            "model_file": ppo.model_filename,
            "safety_rules": [
                "Departure Urgency SLA Guarantee",
                "Maximum SOC Protection Bound",
                "Minimum SOC / V2G Lower Bound",
                "V2G Departure Risk Buffer",
                "Grid Feeder Stress Throttling",
                "Battery Pack Degradation Safeguard"
            ],
            "current_simulation_hour": sim_service.engine.current_hour,
            "realtime_status": "RUNNING" if sim_service.is_running else "PAUSED"
        }

    @router.get("/training/status")
    def get_training_status():
        ppo = sim_service.engine.rl_agent.ppo
        latest_job = list(active_jobs.values())[-1] if active_jobs else None

        status_val = "TRAINED"
        if latest_job and latest_job.get("status") == "running":
            status_val = "running"
        elif latest_job and latest_job.get("status") == "completed":
            status_val = "completed"

        res = {
            "algorithm": "PPO (Proximal Policy Optimization)",
            "environment": "Gymnasium EVChargingGymEnv",
            "observation_space": 10,
            "action_space": 3,
            "episodes_trained": ppo.episodes_trained,
            "mean_reward": ppo.mean_reward,
            "best_reward": ppo.best_reward,
            "final_reward": getattr(ppo, "final_reward", ppo.mean_reward),
            "status": status_val,
            "model_filename": ppo.model_filename,
            "training_curves": ppo.training_history
        }
        if latest_job:
            res["active_job"] = latest_job
            res["job_id"] = latest_job.get("job_id")
            res["episode"] = latest_job.get("episode", ppo.episodes_trained)
            res["total_episodes"] = latest_job.get("total_episodes", ppo.episodes_trained)
            res["progress_percent"] = latest_job.get("progress_percent", 100.0)
            if latest_job.get("metrics"):
                res["metrics"] = latest_job["metrics"]
                for k, v in latest_job["metrics"].items():
                    if k not in res:
                        res[k] = v
        return res

    @router.post("/train")
    async def trigger_training(req: TrainRequest = TrainRequest(episodes=50)):
        env = EVChargingGymEnv(energy_provider=sim_service.engine.energy_provider)
        ppo = sim_service.engine.rl_agent.ppo
        num_eps = min(500, max(5, req.episodes))

        if req.background:
            job_id = f"job-{uuid.uuid4().hex[:8]}"
            active_jobs[job_id] = {
                "job_id": job_id,
                "status": "running",
                "episode": 0,
                "total_episodes": num_eps,
                "progress_percent": 0.0,
                "start_time": datetime.utcnow().isoformat(),
                "metrics": None
            }

            def run_bg_job():
                def prog_cb(cur, tot, pct, rew):
                    if job_id in active_jobs:
                        active_jobs[job_id]["episode"] = cur
                        active_jobs[job_id]["progress_percent"] = pct

                try:
                    res = ppo.train_on_env(env, num_episodes=num_eps, progress_callback=prog_cb)
                    if job_id in active_jobs:
                        active_jobs[job_id]["status"] = "completed"
                        active_jobs[job_id]["progress_percent"] = 100.0
                        active_jobs[job_id]["metrics"] = res
                except Exception as ex:
                    if job_id in active_jobs:
                        active_jobs[job_id]["status"] = "failed"
                        active_jobs[job_id]["error"] = str(ex)

            asyncio.create_task(asyncio.to_thread(run_bg_job))

            return {
                "status": "started",
                "job_id": job_id,
                "episodes": num_eps,
                "message": f"PPO background training job {job_id} initiated for {num_eps} episodes."
            }

        # Synchronous completion but executed in worker thread to prevent event-loop blocking
        result = await asyncio.to_thread(ppo.train_on_env, env, num_eps)
        response = {
            **result,
            "status": "success",
            "model_status": result.get("status", "TRAINED"),
            "message": f"Successfully executed PPO training step for {result['episodes_added']} episodes.",
            "metrics": result,
            "training_curves": ppo.training_history
        }
        return response

    @router.get("/constraints/events")
    def get_constraint_events(limit: int = 50):
        events = ConstraintEngine.get_recent_events(limit)
        return {
            "events": events,
            "recent_events": events,
            "total": len(ConstraintEngine._events_log),
            "total_events": len(ConstraintEngine._events_log),
            "limit": limit
        }

    @router.get("/explain/{ev_id}")
    def explain_decision(ev_id: str):
        engine = sim_service.engine
        ev = engine.evs.get(ev_id)
        if not ev:
            norm_id = ev_id.lower().replace("-00", "-").replace("-0", "-")
            for k, v in engine.evs.items():
                k_norm = k.lower().replace("-00", "-").replace("-0", "-")
                if k_norm == norm_id or k.lower() == ev_id.lower():
                    ev = v
                    break
        if not ev:
            raise HTTPException(status_code=404, detail="EV not found")

        current_hour = engine.current_hour
        grid_state = engine.energy_provider.get_grid_state(current_hour)
        price_info = engine.energy_provider.get_electricity_price(current_hour)
        solar_kw = engine.energy_provider.get_solar_generation(current_hour)

        obs = engine.rl_agent.build_observation(ev, current_hour)
        raw_action, probs, val, conf = engine.rl_agent.ppo.predict(obs)
        final_action, power, overrides = ConstraintEngine.validate_action(
            ev, raw_action, current_hour, grid_state["utilization_pct"], price_info["current_price"]
        )

        time_remaining = max(0.0, ev.departure_time - current_hour)
        soc_needed = max(0.0, ev.target_soc - ev.current_soc)

        # Build deep-dive explanation text
        action_names = {0: "IDLE", 1: "CHARGE", 2: "DISCHARGE (V2G)"}
        proposed_str = action_names.get(raw_action, "IDLE")
        final_str = action_names.get(final_action, "IDLE")

        if overrides:
            explanation = f"The PPO neural network proposed {proposed_str}. However, the Safety Constraint Engine intervened: {'; '.join(overrides)}. Action safely clamped to {final_str} ({power} kW)."
        else:
            if final_action == 1:
                explanation = f"The PPO policy selected CHARGE (+{power:.1f} kW) with {conf*100:.1f}% confidence. Rationale: Current price is low (₹{price_info['current_price']}/kWh) and solar array is supplying {solar_kw:.1f} kW. Grid utilization ({grid_state['utilization_pct']:.1f}%) is well within feeder safety headroom."
            elif final_action == 2:
                explanation = f"The PPO policy selected V2G DISCHARGE ({power:.1f} kW) with {conf*100:.1f}% confidence. Rationale: High grid load ({grid_state['utilization_pct']:.1f}%) and peak tariff (₹{price_info['current_price']}/kWh). EV has {ev.current_soc:.1f}% SOC, safely exceeding reserve requirements."
            else:
                explanation = f"The PPO policy selected IDLE (0.0 kW). Rationale: EV battery is at {ev.current_soc:.1f}% with {time_remaining:.1f}h remaining before departure. Deferring charge avoids peak tariffs and transformer congestion until optimal solar windows."

        return {
            "ev_id": ev.ev_id,
            "ev_name": ev.name,
            "current_hour": round(current_hour, 2),
            "current_soc": round(ev.current_soc, 1),
            "target_soc": round(ev.target_soc, 1),
            "departure_time": ev.departure_time,
            "battery_capacity_kwh": ev.battery_capacity_kwh,
            "time_to_departure_hours": round(time_remaining, 1),
            "battery_temperature_c": getattr(ev.battery, "temperature_c", 25.0),
            "temperature_c": getattr(ev.battery, "temperature_c", 25.0),
            "battery_soh_pct": getattr(ev.battery, "battery_health", 100.0),
            "soh_pct": getattr(ev.battery, "battery_health", 100.0),
            "is_thermally_throttled": getattr(ev.battery, "is_thermally_throttled", False),
            "grid_utilization_pct": round(grid_state["utilization_pct"], 1),
            "solar_generation_kw": round(solar_kw, 1),
            "electricity_price": round(price_info["current_price"], 2),
            "neural_network_probabilities": probs,
            "actor_probabilities": probs,
            "critic_state_value": val,
            "confidence_score": conf,
            "proposed_action": proposed_str,
            "raw_proposed_action": proposed_str,
            "final_action": final_str,
            "final_approved_action": final_str,
            "approved_power_kw": power,
            "safety_interventions": overrides,
            "is_safety_overridden": len(overrides) > 0 and (raw_action != final_action),
            "detailed_explanation": explanation,
            "explanation": explanation,
            "constraint_checks": {
                "overcharge_prevented": ev.current_soc >= 99.0,
                "deep_discharge_prevented": ev.current_soc <= getattr(ev, "min_soc", getattr(ev, "min_soc_pct", 20.0)),
                "departure_urgency_enforced": time_remaining <= 1.5 and ev.current_soc < ev.target_soc,
                "grid_transformer_limit_checked": True
            }
        }

    @router.get("/schedule")
    def get_24h_predictive_schedule():
        schedule = {}
        engine = sim_service.engine

        for h in range(24):
            hour = float(h)
            for ev in engine.evs.values():
                if ev.ev_id not in schedule:
                    schedule[ev.ev_id] = {"ev_name": ev.name, "timeline": []}

                if hour < ev.arrival_time or hour >= ev.departure_time:
                    act_name = "IDLE"
                else:
                    temp_twin = EVDigitalTwin(
                        ev_id=ev.ev_id,
                        name=ev.name,
                        battery_capacity_kwh=ev.battery_capacity_kwh,
                        current_soc=ev.current_soc,
                        minimum_soc=ev.minimum_soc,
                        maximum_soc=ev.maximum_soc,
                        target_soc=ev.target_soc,
                        arrival_time=ev.arrival_time,
                        departure_time=ev.departure_time,
                        max_charge_power_kw=ev.max_charge_power_kw,
                        max_discharge_power_kw=ev.max_discharge_power_kw
                    )
                    temp_twin.update_schedule_status(hour)
                    dec = engine.rl_agent.select_action(temp_twin, hour)
                    act_name = dec["action_name"]

                schedule[ev.ev_id]["timeline"].append({
                    "hour": h,
                    "action": act_name
                })

        return {"schedule": schedule}

    @router.post("/decision")
    def single_decision(payload: AIDecisionRequest):
        ev_id = payload.ev_id
        ev = sim_service.engine.evs.get(ev_id) if ev_id else next(iter(sim_service.engine.evs.values()), None)
        if not ev:
            raise HTTPException(status_code=404, detail="No EV found for evaluation")

        hour = payload.hour if payload.hour is not None else sim_service.engine.current_hour
        decision = sim_service.engine.rl_agent.select_action(ev, hour)
        return decision

    @router.get("/insight")
    def get_llm_strategic_insight():
        engine = sim_service.engine
        grid_state = engine.energy_provider.get_grid_state(engine.current_hour)
        price_info = engine.energy_provider.get_electricity_price(engine.current_hour)
        solar_kw = engine.energy_provider.get_solar_generation(engine.current_hour)

        evs_summary = ", ".join([f"{ev.ev_id}: SOC {ev.current_soc}%, Status {ev.status}" for ev in engine.evs.values()])

        insight = OpenAIService.generate_llm_insight(
            grid_load_pct=grid_state["utilization_pct"],
            electricity_price=price_info["current_price"],
            solar_kw=solar_kw,
            ev_summary=evs_summary
        )

        return {"insight": insight}

    return router
