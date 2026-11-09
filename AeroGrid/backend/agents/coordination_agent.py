"""AeroGrid Coordination Engine.

Implements the multi-agent arbitration and conflict resolution engine for UTM.
Arbitrates between Aviation Safety, Telecom C2 health, and Fleet Logistics,
and logs the complete decision lineage to SQLite WAL.
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

# Attempt standard Pydantic v2 import with lightweight fallback
try:
    from pydantic import BaseModel, Field

    class OperationalCommand(BaseModel):
        """Final operational directive issued by the Coordination Engine."""
        command_id: str = Field(..., description="Unique command tracking identifier.")
        timestamp: str = Field(..., description="ISO-8601 UTC execution timestamp.")
        target_drone_id: str = Field(..., description="Target UAS identifier.")
        context_hash: str = Field(..., description="SHA-256 fingerprint of the simulation state.")
        action: str = Field(..., description="Executable physical/network operational directive.")
        justification: str = Field(..., description="Comprehensive arbitration rationale.")
        selected_agent: str = Field(..., description="Agent whose mandate determined the resolution.")
        conflict_detected: bool = Field(..., description="Whether input recommendations were in conflict.")
        accepted_recommendations: List[Dict[str, Any]] = Field(
            default_factory=list,
            description="Agent recommendations accepted or synthesized into final command.",
        )
        overruled_recommendations: List[Dict[str, Any]] = Field(
            default_factory=list,
            description="Agent recommendations overruled during arbitration with reasons.",
        )
        confidence_score: float = Field(
            ...,
            ge=0.0,
            le=1.0,
            description="Arbitration confidence score.",
        )
        audit_event_id: str = Field(..., description="Primary audit log ID in SQLite WAL.")
        child_event_ids: List[str] = Field(
            default_factory=list,
            description="Audit log IDs of the contributory domain agents.",
        )

except ImportError:
    class OperationalCommand:  # type: ignore[no-redef]
        """Fallback OperationalCommand container matching Pydantic interface."""
        def __init__(
            self,
            command_id: str,
            timestamp: str,
            target_drone_id: str,
            context_hash: str,
            action: str,
            justification: str,
            selected_agent: str,
            conflict_detected: bool,
            accepted_recommendations: List[Dict[str, Any]],
            overruled_recommendations: List[Dict[str, Any]],
            confidence_score: float,
            audit_event_id: str,
            child_event_ids: List[str],
        ) -> None:
            self.command_id = command_id
            self.timestamp = timestamp
            self.target_drone_id = target_drone_id
            self.context_hash = context_hash
            self.action = action
            self.justification = justification
            self.selected_agent = selected_agent
            self.conflict_detected = conflict_detected
            self.accepted_recommendations = accepted_recommendations
            self.overruled_recommendations = overruled_recommendations
            self.confidence_score = round(float(confidence_score), 4)
            self.audit_event_id = audit_event_id
            self.child_event_ids = child_event_ids

        def model_dump(self) -> Dict[str, Any]:
            return {
                "command_id": self.command_id,
                "timestamp": self.timestamp,
                "target_drone_id": self.target_drone_id,
                "context_hash": self.context_hash,
                "action": self.action,
                "justification": self.justification,
                "selected_agent": self.selected_agent,
                "conflict_detected": self.conflict_detected,
                "accepted_recommendations": self.accepted_recommendations,
                "overruled_recommendations": self.overruled_recommendations,
                "confidence_score": self.confidence_score,
                "audit_event_id": self.audit_event_id,
                "child_event_ids": self.child_event_ids,
            }

from backend.agents.base_agent import AgentResponse
from backend.audit.logger import AuditEngine
from backend.knowledge_base.retrieval import PolicyRetriever

logger = logging.getLogger("aerogrid.coordination")


class CoordinationEngine:
    """The central authority in AeroGrid UTM.

    Evaluates Pydantic outputs of Aviation, Telecom, and Fleet agents against
    statutory priority hierarchies (ASTM F3411, ICAO, UAE Civil Aviation Law)
    to output an actionable OperationalCommand with complete audit provenance.
    """

    def __init__(
        self,
        audit_engine: Optional[AuditEngine] = None,
        retriever: Optional[PolicyRetriever] = None,
        llm_client: Any = None,
        model_name: str = "gpt-4o",
    ) -> None:
        """Initialize CoordinationEngine."""
        self.audit = audit_engine or AuditEngine()
        self.retriever = retriever or PolicyRetriever()
        self.llm_client = llm_client
        self.model_name = model_name

    def resolve_conflict(
        self,
        aviation_resp: AgentResponse,
        telecom_resp: AgentResponse,
        fleet_resp: AgentResponse,
        state: Dict[str, Any],
        target_drone_id: Optional[str] = None,
    ) -> OperationalCommand:
        """Arbitrate between agent recommendations and generate an OperationalCommand.

        Enforces the regulatory priority hierarchy:
        1. Tier 1: Airspace Safety & Regulatory Non-Negotiables (Aviation Agent)
        2. Tier 2: C2 Link & Communication Integrity (Telecom Agent)
        3. Tier 3: Fleet Logistics & Energy Management (Fleet Agent)

        Logs all recommendations and the final command to the SQLite WAL database.
        """
        # Determine target drone ID and context fingerprint
        drone_id = (
            target_drone_id
            or state.get("drone_id")
            or state.get("fleet_telemetry", {}).get("drone_id")
            or "DRONE_UAS_01"
        )
        context_hash = aviation_resp.context_hash or hashlib.sha256(
            json.dumps(state, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()

        # Step 1: Pre-generate parent command event ID for audit linkage
        command_id = f"cmd_{uuid.uuid4().hex[:10]}"
        parent_audit_event_id = f"evt_{uuid.uuid4().hex}"
        timestamp_now = datetime.now(timezone.utc).isoformat()

        # Step 2: Log individual domain agent decisions to SQLite WAL
        av_event_id = self.audit.insert_log(
            agent_id=aviation_resp.agent_id or "aviation_safety_agent",
            context_hash=context_hash,
            recommended_action=aviation_resp.recommended_action,
            decision_justification=aviation_resp.justification,
            retrieved_policy_sources=aviation_resp.policy_citations,
            confidence_score=aviation_resp.confidence,
            timestamp=timestamp_now,
            parent_decision_id=parent_audit_event_id,
            target_drone_id=drone_id,
        )

        tc_event_id = self.audit.insert_log(
            agent_id=telecom_resp.agent_id or "telecom_c2_agent",
            context_hash=context_hash,
            recommended_action=telecom_resp.recommended_action,
            decision_justification=telecom_resp.justification,
            retrieved_policy_sources=telecom_resp.policy_citations,
            confidence_score=telecom_resp.confidence,
            timestamp=timestamp_now,
            parent_decision_id=parent_audit_event_id,
            target_drone_id=drone_id,
        )

        fl_event_id = self.audit.insert_log(
            agent_id=fleet_resp.agent_id or "fleet_ops_agent",
            context_hash=context_hash,
            recommended_action=fleet_resp.recommended_action,
            decision_justification=fleet_resp.justification,
            retrieved_policy_sources=fleet_resp.policy_citations,
            confidence_score=fleet_resp.confidence,
            timestamp=timestamp_now,
            parent_decision_id=parent_audit_event_id,
            target_drone_id=drone_id,
        )

        child_event_ids = [av_event_id, tc_event_id, fl_event_id]

        # Step 3: Query coordination hierarchy policy
        coord_policies = self.retriever.query_policy("coordination", "hierarchy conflict priority")
        coord_citations = [p["source"] for p in coord_policies]

        # Step 4: Evaluate recommendations against conflict rules
        resolved_action: str
        rationale: str
        winning_agent: str
        conflict_detected: bool = False
        accepted: List[Dict[str, Any]] = []
        overruled: List[Dict[str, Any]] = []
        final_confidence: float

        # Detect safety emergencies from aviation
        av_action = aviation_resp.recommended_action.upper()
        tc_action = telecom_resp.recommended_action.upper()
        fl_action = fleet_resp.recommended_action.upper()

        is_aviation_critical = (
            "EMERGENCY" in av_action
            or "CLIMB" in av_action
            or "REVERSE" in av_action
            or "EVACUATION" in av_action
            or aviation_resp.confidence >= 0.93
        ) and "MAINTAIN" not in av_action

        is_telecom_critical = (
            "FAILSAFE" in tc_action
            or "LOST_LINK" in tc_action
            or "HOVER" in tc_action
            or "DESCEND" in tc_action
        ) and "MAINTAIN" not in tc_action

        is_fleet_critical = (
            "EMERGENCY" in fl_action
            or "DIVERT" in fl_action
        ) and "CONTINUE" not in fl_action

        # Conflict Arbitration Matrix
        if is_aviation_critical:
            winning_agent = aviation_resp.agent_id or "aviation_safety_agent"
            resolved_action = aviation_resp.recommended_action
            rationale = (
                f"ARBITRATION DECISION: Tier 1 Airspace Safety Priority Enforced. "
                f"Aviation agent identified an active airspace conflict or regulatory mandate "
                f"('{aviation_resp.recommended_action}'). Pursuant to ASTM F3411 and UAE Federal "
                f"Decree-Law No. 26 Art. 14, mid-air deconfliction and manned right-of-way "
                f"strictly override telecommunication preferences and fleet logistics SLA."
            )
            final_confidence = aviation_resp.confidence
            accepted.append({
                "agent_id": winning_agent,
                "action": aviation_resp.recommended_action,
                "weight": "Tier 1 (Airspace Law)",
            })

            # Document overruled
            if tc_action != av_action and "MAINTAIN" not in tc_action:
                overruled.append({
                    "agent_id": telecom_resp.agent_id or "telecom_c2_agent",
                    "action": telecom_resp.recommended_action,
                    "reason": "Subordinated to Tier 1 immediate collision/separation avoidance.",
                })
            if fl_action != av_action:
                overruled.append({
                    "agent_id": fleet_resp.agent_id or "fleet_ops_agent",
                    "action": fleet_resp.recommended_action,
                    "reason": "Commercial SLA / energy preservation subordinated to life-safety separation minima.",
                })

        elif is_telecom_critical:
            winning_agent = telecom_resp.agent_id or "telecom_c2_agent"
            resolved_action = telecom_resp.recommended_action
            rationale = (
                f"ARBITRATION DECISION: Tier 2 C2 Link Integrity Priority Enforced. "
                f"Aviation safety is nominal, but Telecom agent detected safety-critical C2 degradation "
                f"('{telecom_resp.recommended_action}'). Pursuant to TDRA UAS guidelines and ICAO Annex 10, "
                f"unreliable command link requires immediate altitude/failsafe adjustments, "
                f"overriding commercial delivery schedules."
            )
            final_confidence = telecom_resp.confidence
            accepted.append({
                "agent_id": winning_agent,
                "action": telecom_resp.recommended_action,
                "weight": "Tier 2 (C2 Link Integrity)",
            })
            if fl_action != tc_action:
                overruled.append({
                    "agent_id": fleet_resp.agent_id or "fleet_ops_agent",
                    "action": fleet_resp.recommended_action,
                    "reason": "UAS cannot maintain autonomous flight plan without compliant C2 link QoS.",
                })

        elif is_fleet_critical:
            # e.g. Battery below reserve limit, with clear airspace and good link
            winning_agent = fleet_resp.agent_id or "fleet_ops_agent"
            resolved_action = fleet_resp.recommended_action
            rationale = (
                f"ARBITRATION DECISION: Tier 3 Energy Safety Directive Approved. "
                f"Airspace and C2 link are confirmed clear. Fleet agent requested critical diversion "
                f"('{fleet_resp.recommended_action}') due to battery reserve depletion. "
                f"Approved pursuant to AeroGrid Fleet SOP Sec. 4.2."
            )
            final_confidence = fleet_resp.confidence
            accepted.append({
                "agent_id": winning_agent,
                "action": fleet_resp.recommended_action,
                "weight": "Tier 3 (Fleet Energy Threshold)",
            })
            if "MAINTAIN" in av_action or "MAINTAIN" in tc_action:
                # Aviation and Telecom were on nominal maintain, but fleet initiated a diversion
                accepted.append({"agent_id": "aviation_safety_agent", "action": "Clear corridor for emergency diversion"})
                accepted.append({"agent_id": "telecom_c2_agent", "action": "Maintain link during diversion vector"})

        else:
            # Nominal consensus across all 3 agents
            winning_agent = "consensus_coordinator"
            resolved_action = "MAINTAIN_NOMINAL_FLIGHT_PLAN_AND_MONITOR"
            rationale = (
                "ARBITRATION DECISION: Multi-Agent Consensus. "
                "All domain agents (Aviation, Telecom, Fleet) report nominal operational envelopes. "
                "Standard cruise flight plan maintained."
            )
            final_confidence = min(aviation_resp.confidence, telecom_resp.confidence, fleet_resp.confidence)
            accepted.extend([
                {"agent_id": aviation_resp.agent_id, "action": aviation_resp.recommended_action},
                {"agent_id": telecom_resp.agent_id, "action": telecom_resp.recommended_action},
                {"agent_id": fleet_resp.agent_id, "action": fleet_resp.recommended_action},
            ])

        conflict_detected = len(overruled) > 0

        # Step 5: Log the final OperationalCommand root record to SQLite WAL
        self.audit.insert_log(
            agent_id="coordination_engine",
            context_hash=context_hash,
            recommended_action=resolved_action,
            decision_justification=rationale,
            retrieved_policy_sources=coord_citations,
            confidence_score=final_confidence,
            timestamp=timestamp_now,
            parent_decision_id=None,  # Root decision record
            event_id=parent_audit_event_id,
            target_drone_id=drone_id,
        )

        # Step 6: Construct and return the validated OperationalCommand
        command_data = {
            "command_id": command_id,
            "timestamp": timestamp_now,
            "target_drone_id": drone_id,
            "context_hash": context_hash,
            "action": resolved_action,
            "justification": rationale,
            "selected_agent": winning_agent,
            "conflict_detected": conflict_detected,
            "accepted_recommendations": accepted,
            "overruled_recommendations": overruled,
            "confidence_score": final_confidence,
            "audit_event_id": parent_audit_event_id,
            "child_event_ids": child_event_ids,
        }

        if hasattr(OperationalCommand, "model_validate"):
            command = OperationalCommand.model_validate(command_data)
        else:
            command = OperationalCommand(**command_data)

        logger.info(
            "Coordination resolved command %s -> %s for %s (Audit ID: %s)",
            command_id,
            resolved_action,
            drone_id,
            parent_audit_event_id,
        )
        return command
