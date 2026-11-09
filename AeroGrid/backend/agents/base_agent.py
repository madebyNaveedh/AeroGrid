"""AeroGrid Base Agent Module.

Defines the abstract BaseAgent and strict Pydantic AgentResponse schema
for domain-specific UTM agents.
"""

from __future__ import annotations

import abc
import hashlib
import json
import logging
from typing import Any, Dict, List, Optional, Tuple, Union

# Attempt standard Pydantic v2 import with lightweight fallback
try:
    from pydantic import BaseModel, Field, field_validator

    class AgentResponse(BaseModel):
        """Strict output schema enforced across all AeroGrid domain agents."""
        recommended_action: str = Field(
            ...,
            description="The operational maneuver or directive recommended by the agent.",
        )
        justification: str = Field(
            ...,
            description="Technical, safety, or economic justification for the recommendation.",
        )
        confidence: float = Field(
            ...,
            ge=0.0,
            le=1.0,
            description="Numerical confidence score between 0.0 and 1.0.",
        )
        policy_citations: List[str] = Field(
            default_factory=list,
            description="List of regulatory, spectrum, or operational policy sources cited.",
        )
        agent_id: Optional[str] = Field(
            default=None,
            description="Identifier of the emitting agent.",
        )
        context_hash: Optional[str] = Field(
            default=None,
            description="Cryptographic SHA-256 hash of the evaluated state context.",
        )

        @field_validator("confidence")
        @classmethod
        def validate_confidence_range(cls, v: float) -> float:
            if not 0.0 <= v <= 1.0:
                raise ValueError("Confidence must be strictly between 0.0 and 1.0")
            return round(v, 4)

        @field_validator("recommended_action")
        @classmethod
        def validate_action_non_empty(cls, v: str) -> str:
            v_stripped = v.strip()
            if not v_stripped:
                raise ValueError("recommended_action cannot be empty")
            return v_stripped

except ImportError:
    # Minimal fallback schema if pydantic is not installed in runtime environment
    class AgentResponse:  # type: ignore[no-redef]
        """Fallback AgentResponse container matching Pydantic interface."""
        def __init__(
            self,
            recommended_action: str,
            justification: str,
            confidence: float,
            policy_citations: Optional[List[str]] = None,
            agent_id: Optional[str] = None,
            context_hash: Optional[str] = None,
        ) -> None:
            if not 0.0 <= confidence <= 1.0:
                raise ValueError("Confidence must be between 0.0 and 1.0")
            if not recommended_action or not recommended_action.strip():
                raise ValueError("recommended_action cannot be empty")

            self.recommended_action = recommended_action.strip()
            self.justification = justification
            self.confidence = round(float(confidence), 4)
            self.policy_citations = policy_citations or []
            self.agent_id = agent_id
            self.context_hash = context_hash

        def model_dump(self) -> Dict[str, Any]:
            return {
                "recommended_action": self.recommended_action,
                "justification": self.justification,
                "confidence": self.confidence,
                "policy_citations": self.policy_citations,
                "agent_id": self.agent_id,
                "context_hash": self.context_hash,
            }

        @classmethod
        def model_validate_json(cls, json_str: str) -> "AgentResponse":
            data = json.loads(json_str)
            return cls(**data)

        @classmethod
        def model_validate(cls, data: Dict[str, Any]) -> "AgentResponse":
            return cls(**data)

        def __repr__(self) -> str:
            return (
                f"AgentResponse(recommended_action='{self.recommended_action}', "
                f"confidence={self.confidence}, citations={len(self.policy_citations)})"
            )

from backend.knowledge_base.retrieval import PolicyRetriever

logger = logging.getLogger("aerogrid.agents.base")


class BaseAgent(abc.ABC):
    """Abstract Base Class for AeroGrid UTM Domain Agents.

    Adheres strictly to separation of concerns:
    - Agents do not execute physical or network commands.
    - Agents observe simulation state, query regulatory policy RAG, and output
      structured, validated Pydantic recommendations.
    """

    def __init__(
        self,
        agent_id: str,
        domain_mandate: str,
        llm_client: Any = None,
        retriever: Optional[PolicyRetriever] = None,
        model_name: str = "gpt-4o",
    ) -> None:
        """Initialize the domain agent.

        Args:
            agent_id: Unique string identifier for this agent.
            domain_mandate: Detailed domain role and non-negotiable responsibilities.
            llm_client: Standard LLM client instance (e.g. OpenAI / Google GenAI client).
            retriever: PolicyRetriever instance for regulatory citations.
            model_name: Target model identifier.
        """
        self.agent_id = agent_id
        self.domain_mandate = domain_mandate
        self.llm_client = llm_client
        self.retriever = retriever or PolicyRetriever()
        self.model_name = model_name

    @property
    @abc.abstractmethod
    def domain(self) -> str:
        """The regulatory domain string used for knowledge base retrieval."""
        pass

    @abc.abstractmethod
    def extract_domain_query(self, state: Dict[str, Any]) -> str:
        """Extract or synthesize a policy retrieval search query from simulation state."""
        pass

    @staticmethod
    def compute_context_hash(state: Dict[str, Any]) -> str:
        """Compute a deterministic SHA-256 fingerprint of the simulation state."""
        state_serialized = json.dumps(state, sort_keys=True, default=str)
        return hashlib.sha256(state_serialized.encode("utf-8")).hexdigest()

    def format_prompt(
        self, state: Dict[str, Any], citations: List[Dict[str, str]]
    ) -> Tuple[str, str]:
        """Construct system and user prompt strings for LLM evaluation."""
        formatted_citations = "\n".join(
            [
                f"[{i+1}] {c.get('source', 'Unknown')}: \"{c.get('excerpt', '')}\""
                for i, c in enumerate(citations)
            ]
        )

        system_prompt = (
            f"You are the AeroGrid {self.agent_id} in an Unmanned Traffic Management (UTM) system.\n"
            f"DOMAIN MANDATE: {self.domain_mandate}\n\n"
            "STRICT INSTRUCTIONS:\n"
            "1. You do not control hardware or issue direct commands.\n"
            "2. Analyze the simulation state exclusively from your domain perspective.\n"
            "3. Ground your recommendation strictly in the retrieved policy citations.\n"
            "4. Output MUST be valid JSON adhering strictly to this schema:\n"
            "   {\n"
            '     "recommended_action": "<concise action or maneuver>",\n'
            '     "justification": "<domain explanation referencing policy>",\n'
            '     "confidence": <float between 0.0 and 1.0>,\n'
            '     "policy_citations": ["<source citation 1>", ...]\n'
            "   }\n"
        )

        user_prompt = (
            f"CURRENT SIMULATION STATE:\n{json.dumps(state, indent=2)}\n\n"
            f"RETRIEVED DOMAIN POLICIES:\n{formatted_citations}\n\n"
            "Evaluate this state and output your JSON recommendation."
        )

        return system_prompt, user_prompt

    def evaluate_state(self, state: Dict[str, Any]) -> AgentResponse:
        """Query policy, format prompt, call LLM, and return validated AgentResponse.

        Args:
            state: Simulation state dictionary (telemetry, threats, link metrics, etc.).

        Returns:
            Validated AgentResponse Pydantic object.
        """
        context_hash = self.compute_context_hash(state)
        query = self.extract_domain_query(state)

        # 1. Query Knowledge Base for relevant policy
        citations = self.retriever.query_policy(domain=self.domain, query=query)
        citation_sources = [c["source"] for c in citations]

        # 2. Format LLM Prompts
        system_prompt, user_prompt = self.format_prompt(state, citations)

        # 3. Call LLM or fallback reasoning
        response: Optional[AgentResponse] = None

        if self.llm_client is not None:
            try:
                response = self._call_llm_api(system_prompt, user_prompt, citation_sources)
            except Exception as exc:
                logger.warning(
                    "LLM API call failed for %s (%s). Executing deterministic domain fallback.",
                    self.agent_id,
                    exc,
                )

        if response is None:
            response = self._fallback_domain_reasoning(state, citations)

        # Enforce trace metadata
        response.agent_id = self.agent_id
        response.context_hash = context_hash
        if not response.policy_citations:
            response.policy_citations = citation_sources

        logger.info(
            "Agent [%s] evaluated context %s -> Action: %s (Confidence: %.2f)",
            self.agent_id,
            context_hash[:8],
            response.recommended_action,
            response.confidence,
        )
        return response

    def _call_llm_api(
        self, system_prompt: str, user_prompt: str, default_citations: List[str]
    ) -> AgentResponse:
        """Execute structured completion via standard LLM client."""
        # Standard OpenAI-style client integration
        if hasattr(self.llm_client, "chat") and hasattr(self.llm_client.chat, "completions"):
            completion = self.llm_client.chat.completions.create(
                model=self.model_name,
                response_format={"type": "json_object"},
                temperature=0.1,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            )
            raw_content = completion.choices[0].message.content or "{}"
            if hasattr(AgentResponse, "model_validate_json"):
                return AgentResponse.model_validate_json(raw_content)
            data = json.loads(raw_content)
            return AgentResponse(**data)

        raise NotImplementedError("Provided LLM client interface is not currently supported.")

    @abc.abstractmethod
    def _fallback_domain_reasoning(
        self, state: Dict[str, Any], citations: List[Dict[str, str]]
    ) -> AgentResponse:
        """Domain-specific deterministic reasoning engine used for offline testing/fallbacks."""
        pass

