"""AeroGrid UTM Prototype (Phase 1) - Main Execution Entrypoint.

Orchestrates multi-agent simulation scenarios, conflict arbitration,
SQLite WAL audit logging, and Parquet analytical export.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

# Add backend and project root to Python module search path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.config import settings
from backend.audit.logger import AuditEngine
from backend.knowledge_base.retrieval import PolicyRetriever
from backend.agents.aviation_agent import AviationAgent
from backend.agents.telecom_agent import TelecomAgent
from backend.agents.fleet_agent import FleetAgent
from backend.agents.coordination_agent import CoordinationEngine

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
)
logger = logging.getLogger("aerogrid.main")


def build_llm_client():
    """Attempt to construct an OpenAI client if configured and mock mode is off."""
    if settings.mock_llm_mode or not settings.openai_api_key:
        logger.info("Operating in deterministic mock LLM mode (no API calls required).")
        return None

    try:
        from openai import OpenAI
        client = OpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url or None,
        )
        logger.info("Initialized live OpenAI LLM client with model '%s'", settings.openai_model)
        return client
    except ImportError:
        logger.warning("openai package not installed. Falling back to deterministic reasoning.")
        return None


def run_simulation_pipeline() -> None:
    """Execute end-to-end multi-agent UTM conflict resolution scenarios."""
    print("=" * 80)
    print("  AEROGRID (PHASE 1) - MODULAR MULTI-AGENT UTM SIMULATION")
    print("=" * 80)

    # 1. Initialize Infrastructure Components
    audit_engine = AuditEngine(db_path=settings.db_path)
    retriever = PolicyRetriever()
    llm_client = build_llm_client()

    # 2. Instantiate Domain Agents
    aviation_agent = AviationAgent(
        llm_client=llm_client,
        retriever=retriever,
        model_name=settings.openai_model,
    )
    telecom_agent = TelecomAgent(
        llm_client=llm_client,
        retriever=retriever,
        model_name=settings.openai_model,
    )
    fleet_agent = FleetAgent(
        llm_client=llm_client,
        retriever=retriever,
        model_name=settings.openai_model,
    )

    # 3. Instantiate Coordination Engine
    coordinator = CoordinationEngine(
        audit_engine=audit_engine,
        retriever=retriever,
        llm_client=llm_client,
        model_name=settings.openai_model,
    )

    # 4. Define Realistic Operational Test Scenarios
    scenarios = [
        {
            "id": "SCENARIO_01_HEMS_AIRSPACE_CONFLICT",
            "name": "Manned Medical Helicopter (HEMS) Airspace Incursion vs Low Battery",
            "state": {
                "drone_id": "UAS_CARGO_DXB_104",
                "timestamp": "2026-11-08T17:00:00Z",
                "altitude_m": 120,
                "ground_speed_mps": 22.5,
                "airspace_traffic": {
                    "manned_traffic_detected": True,
                    "hems_in_vicinity": True,
                    "intruder_distance_m": 820,
                    "closing_velocity_mps": 65.0,
                },
                "telecom_metrics": {
                    "rtt_latency_ms": 42,
                    "packet_loss_pct": 0.1,
                    "link_lost": False,
                    "urban_canyon_shadowing": False,
                },
                "fleet_telemetry": {
                    "drone_id": "UAS_CARGO_DXB_104",
                    "battery_soc_pct": 21.5,
                    "cargo_type": "standard_parcel",
                    "expedited_medical_payload": False,
                },
            },
        },
        {
            "id": "SCENARIO_02_URBAN_CANYON_C2_DEGRADATION",
            "name": "Urban Canyon 5G Shadowing Spike vs Commercial Delivery Cruise",
            "state": {
                "drone_id": "UAS_DELIVERY_AUH_209",
                "timestamp": "2026-11-08T17:05:00Z",
                "altitude_m": 90,
                "ground_speed_mps": 18.0,
                "airspace_traffic": {
                    "manned_traffic_detected": False,
                    "intruder_distance_m": 4500,
                },
                "telecom_metrics": {
                    "rtt_latency_ms": 295,
                    "packet_loss_pct": 3.8,
                    "link_lost": False,
                    "urban_canyon_shadowing": True,
                },
                "fleet_telemetry": {
                    "drone_id": "UAS_DELIVERY_AUH_209",
                    "battery_soc_pct": 58.0,
                    "cargo_type": "high_value_retail",
                    "expedited_medical_payload": False,
                },
            },
        },
        {
            "id": "SCENARIO_03_CRITICAL_BATTERY_RESERVE_DIVERT",
            "name": "Depleted Battery Reserve (<18%) in Clear Controlled Airspace",
            "state": {
                "drone_id": "UAS_MED_SHJ_311",
                "timestamp": "2026-11-08T17:10:00Z",
                "altitude_m": 105,
                "ground_speed_mps": 20.0,
                "airspace_traffic": {
                    "manned_traffic_detected": False,
                    "intruder_distance_m": 8000,
                },
                "telecom_metrics": {
                    "rtt_latency_ms": 38,
                    "packet_loss_pct": 0.05,
                    "link_lost": False,
                    "urban_canyon_shadowing": False,
                },
                "fleet_telemetry": {
                    "drone_id": "UAS_MED_SHJ_311",
                    "battery_soc_pct": 16.2,
                    "cargo_type": "lab_blood_samples",
                    "expedited_medical_payload": True,
                },
            },
        },
    ]

    # 5. Process Scenarios Through the UTM Pipeline
    for i, sc in enumerate(scenarios, 1):
        print("\n" + "-" * 80)
        print(f"  EXECUTION RUN #{i}: {sc['id']}")
        print(f"  Description: {sc['name']}")
        print("-" * 80)

        state = sc["state"]
        drone_id = state["drone_id"]

        # Step A: Domain Agents Evaluate State Independently
        av_resp = aviation_agent.evaluate_state(state)
        tc_resp = telecom_agent.evaluate_state(state)
        fl_resp = fleet_agent.evaluate_state(state)

        print(f"\n[Domain Recommendations for {drone_id}]:")
        print(f"  - Aviation Safety:  '{av_resp.recommended_action}' (conf: {av_resp.confidence})")
        print(f"  - Telecom C2:       '{tc_resp.recommended_action}' (conf: {tc_resp.confidence})")
        print(f"  - Fleet Logistics:  '{fl_resp.recommended_action}' (conf: {fl_resp.confidence})")

        # Step B: Coordination Engine Arbitrates and Enforces Policy Hierarchy
        cmd = coordinator.resolve_conflict(
            aviation_resp=av_resp,
            telecom_resp=tc_resp,
            fleet_resp=fl_resp,
            state=state,
            target_drone_id=drone_id,
        )

        print(f"\n[Coordination Engine Operational Command]:")
        print(f"  * Command ID:       {cmd.command_id}")
        print(f"  * Deciding Agent:   {cmd.selected_agent}")
        print(f"  * Action Directive: {cmd.action}")
        print(f"  * Conflict Status:  {'YES (Resolved)' if cmd.conflict_detected else 'NO (Consensus)'}")
        print(f"  * Confidence Score: {cmd.confidence_score}")
        print(f"  * Audit Event ID:   {cmd.audit_event_id}")
        print(f"  * Justification:    {cmd.justification}")

        if cmd.overruled_recommendations:
            print(f"  * Overruled Directives ({len(cmd.overruled_recommendations)}):")
            for ovr in cmd.overruled_recommendations:
                print(f"    - Overruled: [{ovr.get('agent_id')}] '{ovr.get('action')}'")
                print(f"      Reason: {ovr.get('reason')}")

    # 6. Audit Trail Summary & Verification
    print("\n" + "=" * 80)
    print("  SQLITE WAL AUDIT ENGINE VERIFICATION")
    print("=" * 80)
    all_logs = audit_engine.get_all_logs()
    print(f"Total immutable decision records logged in SQLite WAL: {len(all_logs)}")
    print(f"Database File: {audit_engine.db_path}\n")

    print(f"{'Event ID':<20} | {'Agent ID':<22} | {'Parent Event ID':<20} | {'Action':<35}")
    print("-" * 105)
    for log in all_logs[-8:]:  # Show recent 8 logs
        pid = log["parent_decision_id"] or "[ROOT COORDINATOR]"
        print(f"{log['event_id']:<20} | {log['agent_id']:<22} | {pid:<20} | {log['recommended_action'][:35]:<35}")

    # 7. Parquet Analytical Export
    print("\n" + "=" * 80)
    print("  ANALYTICAL PARQUET EXPORT")
    print("=" * 80)
    parquet_path = Path(settings.parquet_dir) / "utm_audit_trace.parquet"
    try:
        exported_path = audit_engine.export_to_parquet(str(parquet_path))
        print(f"[OK] Audit logs exported successfully to Parquet:\n     {exported_path}")
    except ImportError as e:
        print(f"[INFO] Parquet export skipped (optional analytical dependencies): {e}")
        print("       Install via: pip install pandas pyarrow")

    print("\n[SUCCESS] AeroGrid Phase 1 Modular Multi-Agent UTM Pipeline execution complete.\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="AeroGrid Phase 1 UTM Prototype Runner")
    parser.add_argument("--export", action="store_true", help="Export audit logs to Parquet")
    parser.add_argument("--db-path", type=str, default=None, help="Custom SQLite DB path")
    args = parser.parse_args()

    if args.db_path:
        settings.db_path = args.db_path

    run_simulation_pipeline()


if __name__ == "__main__":
    main()

