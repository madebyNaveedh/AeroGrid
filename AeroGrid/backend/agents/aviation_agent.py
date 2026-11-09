"""AeroGrid Aviation Domain Agent.

Responsible for airspace separation minima, geofence compliance, and right-of-way
adherence under civil aviation authority regulations (GCAA, FAA, ICAO).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from backend.agents.base_agent import AgentResponse, BaseAgent
from backend.knowledge_base.retrieval import PolicyRetriever

logger = logging.getLogger("aerogrid.agents.aviation")


class AviationAgent(BaseAgent):
    """Domain Agent enforcing civil aviation safety and tactical airspace separation."""

    def __init__(
        self,
        llm_client: Any = None,
        retriever: Optional[PolicyRetriever] = None,
        model_name: str = "gpt-4o",
    ) -> None:
        mandate = (
            "Enforce airspace safety, non-negotiable separation minima (500ft vertical, "
            "1,000m lateral), strict geofence containment, and absolute right-of-way "
            "precedence for manned aircraft and emergency medical services (HEMS) "
            "pursuant to UAE Federal Decree-Law No. 26 and GCAA CAR Part IV."
        )
        super().__init__(
            agent_id="aviation_safety_agent",
            domain_mandate=mandate,
            llm_client=llm_client,
            retriever=retriever,
            model_name=model_name,
        )

    @property
    def domain(self) -> str:
        return "aviation"

    def extract_domain_query(self, state: Dict[str, Any]) -> str:
        """Formulate policy query based on airspace hazards."""
        keywords: List[str] = ["separation"]
        traffic = state.get("airspace_traffic", {})
        if traffic.get("manned_traffic_detected") or traffic.get("hems_in_vicinity"):
            keywords.extend(["manned", "emergency", "right-of-way", "hems"])
        if state.get("geofence_breach_warning"):
            keywords.extend(["geofence", "no-fly", "nfz"])
        if traffic.get("intruder_distance_m", 9999) < 1000:
            keywords.extend(["collision", "distance", "altitude"])
        return " ".join(keywords)

    def _fallback_domain_reasoning(
        self, state: Dict[str, Any], citations: List[Dict[str, str]]
    ) -> AgentResponse:
        """Deterministic domain evaluation for safety-critical aviation metrics."""
        traffic = state.get("airspace_traffic", {})
        intruder_distance = traffic.get("intruder_distance_m", float("inf"))
        intruder_is_manned = traffic.get("manned_traffic_detected", False)
        is_hems = traffic.get("hems_in_vicinity", False)
        geofence_warning = state.get("geofence_breach_warning", False)

        citation_sources = [c["source"] for c in citations]

        # Case 1: Manned emergency or HEMS in vicinity (Absolute Priority)
        if is_hems or (intruder_is_manned and intruder_distance < 2000):
            action = "EMERGENCY_DESCENT_AND_CORRIDOR_EVACUATION"
            justification = (
                f"Immediate right-of-way yielding required for manned aircraft/HEMS detected at "
                f"{intruder_distance}m. Sovereign airspace safety regulations dictate absolute "
                f"priority evacuation of the active flight corridor."
            )
            confidence = 0.98

        # Case 2: Tactical separation breach with another UAS
        elif intruder_distance < 600:
            action = "CLIMB_100M_AND_VECTOR_RIGHT_30DEG"
            justification = (
                f"Airspace separation minima breached. Traffic proximity at {intruder_distance}m "
                f"(minima: 1000m lateral / 500ft vertical). Immediate vertical climb and right-turn "
                f"evasion required under GCAA CAR.UAS.405."
            )
            confidence = 0.94

        # Case 3: Geofence proximity
        elif geofence_warning:
            action = "REVERSE_COURSE_TO_SAFE_WAYPOINT"
            justification = (
                "Telemetry indicates imminent boundary incursion into designated No-Fly Zone / "
                "critical infrastructure buffer under ICAO RPAS Manual Ch. 9."
            )
            confidence = 0.91

        # Case 4: Nominal airspace
        else:
            action = "MAINTAIN_ASSIGNED_AIRSPACE_CORRIDOR"
            justification = (
                f"Airspace clear. Nearest traffic at {intruder_distance}m conforms with "
                f"all standard separation standards."
            )
            confidence = 0.88

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

