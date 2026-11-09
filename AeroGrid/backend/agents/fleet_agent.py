"""AeroGrid Fleet Operations Domain Agent.

Responsible for energy reserve management, commercial delivery SLAs,
vertiport slot allocation, and route optimization.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from backend.agents.base_agent import AgentResponse, BaseAgent
from backend.knowledge_base.retrieval import PolicyRetriever

logger = logging.getLogger("aerogrid.agents.fleet")


class FleetAgent(BaseAgent):
    """Domain Agent optimizing logistics, energy conservation, and vertiport utilization."""

    def __init__(
        self,
        llm_client: Any = None,
        retriever: Optional[PolicyRetriever] = None,
        model_name: str = "gpt-4o",
    ) -> None:
        mandate = (
            "Maximize fleet logistics efficiency and SLA fulfillment while strictly "
            "enforcing the 20% State of Charge (SoC) diversion reserve policy pursuant "
            "to AeroGrid Fleet SOP Sec 4.2, and coordinating vertiport slot priority."
        )
        super().__init__(
            agent_id="fleet_ops_agent",
            domain_mandate=mandate,
            llm_client=llm_client,
            retriever=retriever,
            model_name=model_name,
        )

    @property
    def domain(self) -> str:
        return "fleet"

    def extract_domain_query(self, state: Dict[str, Any]) -> str:
        """Formulate policy query based on battery, cargo, and vertiport factors."""
        fleet = state.get("fleet_telemetry", {})
        keywords: List[str] = ["battery"]
        soc = fleet.get("battery_soc_pct", 100)
        if soc <= 20:
            keywords.extend(["reserve", "divert", "energy", "soc"])
        if fleet.get("expedited_medical_payload"):
            keywords.extend(["sla", "cargo", "delivery"])
        if fleet.get("vertiport_approach_active"):
            keywords.extend(["vertiport", "slot", "landing"])
        return " ".join(keywords)

    def _fallback_domain_reasoning(
        self, state: Dict[str, Any], citations: List[Dict[str, str]]
    ) -> AgentResponse:
        """Deterministic domain evaluation for fleet energy and logistical metrics."""
        fleet = state.get("fleet_telemetry", {})
        soc = fleet.get("battery_soc_pct", 65.0)
        is_medical = fleet.get("expedited_medical_payload", False)
        vertiport_approach = fleet.get("vertiport_approach_active", False)

        citation_sources = [c["source"] for c in citations]

        # Case 1: Critical Battery Depletion (<18% SoC)
        if soc < 18.0:
            action = "EMERGENCY_DIVERT_TO_NEAREST_VERTIPORT"
            justification = (
                f"Battery State of Charge is critically depleted at {soc}%, breaching the mandatory "
                f"20% diversion reserve threshold. AeroGrid Fleet SOP Sec. 4.2 mandates immediate "
                f"diversion to alternate landing pad."
            )
            confidence = 0.96

        # Case 2: Low Battery Warning (18% <= SoC < 25%)
        elif soc < 25.0:
            action = "THROTTLE_BACK_TO_MAX_ENDURANCE_SPEED_AVOID_EXTRA_MANEUVERS"
            justification = (
                f"Battery at {soc}% approaching reserve limit. Flight profile must conserve "
                f"energy and avoid extraneous holding maneuvers."
            )
            confidence = 0.88

        # Case 3: Expedited medical cargo with healthy battery
        elif is_medical:
            action = "REQUEST_PRIORITY_DIRECT_TRANSIT_VECTOR"
            justification = (
                "Aircraft is conveying temperature-sensitive medical cargo under priority SLA. "
                "Recommend direct waypoint vectoring with zero holding delays."
            )
            confidence = 0.89

        # Case 4: Vertiport approach sequencing
        elif vertiport_approach:
            action = "ENTER_TERMINAL_APPROACH_SLOT_SEQUENCE"
            justification = (
                "Entering vertiport arrival funnel. Recommend standard descent profile into "
                "designated landing slot."
            )
            confidence = 0.87

        # Case 5: Nominal cruise
        else:
            action = "CONTINUE_PLANNED_ECONOMIC_FLIGHT_PLAN"
            justification = (
                f"Fleet state fully nominal (Battery={soc}%). Cruise profile meets schedule and energy targets."
            )
            confidence = 0.90

        if hasattr(AgentResponse, "model_validate"):
            return AgentResponse.model_validate({
                "recommended_action": action,
                "justification": justification,
                "confidence": confidence,
                "policy_citations": citation_sources,
            })
        return AgentResponse(
            recommended_action=action,
            justification=justification,
            confidence=confidence,
            policy_citations=citation_sources,
        )

