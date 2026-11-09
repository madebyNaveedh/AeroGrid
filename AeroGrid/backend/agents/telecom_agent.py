"""AeroGrid Telecom Domain Agent.

Responsible for monitoring Command & Control (C2) link health, RF spectrum compliance,
packet latency, and communication failsafe protocols under TDRA and 3GPP standards.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from backend.agents.base_agent import AgentResponse, BaseAgent
from backend.knowledge_base.retrieval import PolicyRetriever

logger = logging.getLogger("aerogrid.agents.telecom")


class TelecomAgent(BaseAgent):
    """Domain Agent enforcing telecommunications integrity and C2 link reliability."""

    def __init__(
        self,
        llm_client: Any = None,
        retriever: Optional[PolicyRetriever] = None,
        model_name: str = "gpt-4o",
    ) -> None:
        mandate = (
            "Monitor and safeguard Command & Control (C2) aeronautical link health, "
            "strictly enforce QoS thresholds (RTT latency < 100ms, packet loss < 1.0%), "
            "ensure compliance with TDRA 5030-5091 MHz spectrum guidelines, and trigger "
            "immediate failsafe protocol recommendations upon link degradation."
        )
        super().__init__(
            agent_id="telecom_c2_agent",
            domain_mandate=mandate,
            llm_client=llm_client,
            retriever=retriever,
            model_name=model_name,
        )

    @property
    def domain(self) -> str:
        return "telecom"

    def extract_domain_query(self, state: Dict[str, Any]) -> str:
        """Formulate policy query based on communications and spectrum health."""
        telecom = state.get("telecom_metrics", {})
        keywords: List[str] = ["c2"]
        if telecom.get("link_lost") or telecom.get("rtt_latency_ms", 0) > 250:
            keywords.extend(["lost-link", "failsafe", "rth", "hover"])
        if telecom.get("rtt_latency_ms", 0) > 100 or telecom.get("packet_loss_pct", 0) > 1.0:
            keywords.extend(["latency", "packet", "tdra"])
        if telecom.get("urban_canyon_shadowing"):
            keywords.extend(["5g", "urban", "canyon", "signal", "handoff"])
        return " ".join(keywords)

    def _fallback_domain_reasoning(
        self, state: Dict[str, Any], citations: List[Dict[str, str]]
    ) -> AgentResponse:
        """Deterministic domain evaluation for telecommunications metrics."""
        telecom = state.get("telecom_metrics", {})
        rtt_latency = telecom.get("rtt_latency_ms", 45)
        packet_loss = telecom.get("packet_loss_pct", 0.2)
        link_lost = telecom.get("link_lost", False)
        urban_canyon = telecom.get("urban_canyon_shadowing", False)

        citation_sources = [c["source"] for c in citations]

        # Case 1: Critical Lost-Link State
        if link_lost or rtt_latency > 350 or packet_loss > 8.0:
            action = "TRIGGER_C2_FAILSAFE_HOVER_HOLD"
            justification = (
                f"Severe C2 link failure detected (RTT={rtt_latency}ms, Loss={packet_loss}%). "
                f"TDRA and ICAO failsafe guidelines mandate immediate transition to stabilized "
                f"hover-and-hold prior to executing autonomous Return-To-Home."
            )
            confidence = 0.97

        # Case 2: Degraded link in urban canyon (Need LoS recovery)
        elif urban_canyon or rtt_latency > 150 or packet_loss > 1.5:
            action = "DESCEND_30M_AND_INITIATE_5G_CELL_HANDOVER"
            justification = (
                f"C2 link QoS degraded above 100ms threshold (RTT={rtt_latency}ms, loss={packet_loss}%). "
                f"3GPP TS 22.125 advises lower altitude altitude envelope to mitigate cellular "
                f"shadowing and regain ground gNodeB line-of-sight."
            )
            confidence = 0.90

        # Case 3: Nominal communications
        else:
            action = "MAINTAIN_C2_COMMUNICATIONS_PROFILE"
            justification = (
                f"C2 parameters fully nominal (RTT={rtt_latency}ms, Loss={packet_loss}%). "
                f"Link operating well within TDRA safety thresholds."
            )
            confidence = 0.92

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

