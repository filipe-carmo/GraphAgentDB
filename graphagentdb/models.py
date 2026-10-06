"""Domain models shared by the storage layer, the LLM extraction step and the API."""

from enum import StrEnum

from pydantic import BaseModel, Field, field_validator


class NodeType(StrEnum):
    AGENT = "agent"
    SKILL = "skill"
    TOOL = "tool"
    BEST_PRACTICE = "best_practice"
    THEORETICAL_KNOWLEDGE = "theoretical_knowledge"
    CONCEPT = "concept"


class NodeStatus(StrEnum):
    ACTIVE = "active"
    DEPRECATED = "deprecated"


class RelationType(StrEnum):
    HAS_SKILL = "HAS_SKILL"
    HAS_TOOL = "HAS_TOOL"
    REQUIRES_TOOL = "REQUIRES_TOOL"
    BASED_ON = "BASED_ON"
    REFERENCES = "REFERENCES"
    MENTIONS = "MENTIONS"
    IS_A = "IS_A"
    SUPERSEDES = "SUPERSEDES"


def normalize_id(value: str) -> str:
    """Node ids are stored lower-case so LLM output with mixed casing still links up."""
    value = value.strip().lower()
    if not value:
        raise ValueError("Node id cannot be empty.")
    return value


class KnowledgeNode(BaseModel):
    id: str = Field(..., description="Unique slug-formatted identifier.")
    type: NodeType = NodeType.CONCEPT
    name: str
    description: str
    status: NodeStatus = NodeStatus.ACTIVE
    superseded_by: str = Field("", description="Id of the node that replaced this one.")
    supersession_reason: str = ""

    _normalize_id = field_validator("id")(normalize_id)

    @field_validator("name", "description")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Field cannot be empty or whitespace.")
        return v.strip()


# --- Schemas the LLM fills in during extraction -------------------------------------------


class ExtractedNode(BaseModel):
    id: str = Field(description="Unique snake_case identifier, e.g. graph_rag or mcp_protocol.")
    type: str = Field(
        description="Exactly one of: agent, skill, tool, best_practice, theoretical_knowledge, concept"
    )
    name: str = Field(description="Concise human-readable name.")
    description: str = Field(description="What the entity is or does, taken from the text.")

    _normalize_id = field_validator("id")(normalize_id)


class ExtractedEdge(BaseModel):
    source_id: str = Field(description="Id of the source node.")
    target_id: str = Field(description="Id of the target node.")
    relation_type: str = Field(
        description="Exactly one of: HAS_SKILL, HAS_TOOL, REQUIRES_TOOL, BASED_ON, REFERENCES, MENTIONS, IS_A"
    )
    description: str = Field(description="Why the two entities are connected.")

    _normalize_ids = field_validator("source_id", "target_id")(normalize_id)


class ExtractedGraph(BaseModel):
    nodes: list[ExtractedNode] = Field(default_factory=list)
    edges: list[ExtractedEdge] = Field(default_factory=list)


class ConflictResolution(BaseModel):
    decision: str = Field(description="Exactly one of: new, update, duplicate")
    target_id: str | None = Field(
        None, description="Id of the matching existing node for update or duplicate, else null."
    )
    reason: str = Field(description="Short explanation of the decision.")
