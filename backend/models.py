from typing import Optional, List
from enum import Enum
from pydantic import BaseModel, Field, field_validator

class NodeType(str, Enum):
    AGENT = "agent"
    SKILL = "skill"
    TOOL = "tool"
    BEST_PRACTICE = "best_practice"
    THEORETICAL_KNOWLEDGE = "theoretical_knowledge"
    CONCEPT = "concept"

class NodeStatus(str, Enum):
    ACTIVE = "active"
    DEPRECATED = "deprecated"

class SourceDocument(BaseModel):
    source_hash: str = Field(..., description="Unique MD5 or SHA256 identifier based on document content.")
    title: str = Field(..., description="The title of the scraped source page.")
    url: Optional[str] = Field(None, description="The origin scraping URL.")
    body: str = Field(..., description="Raw text context parsed from source.")

class KnowledgeNode(BaseModel):
    id: str = Field(..., description="Unique slug-formatted ID identifier.")
    type: NodeType = Field(NodeType.CONCEPT, description="The category classification type of this concept node.")
    name: str = Field(..., description="Canonical clear name for this node.")
    description: str = Field(..., description="Structured, comprehensive technical detail or rule description.")
    status: NodeStatus = Field(NodeStatus.ACTIVE, description="Active status of this concept, deprecations indicate supersession.")
    superseded_by: str = Field("", description="Pointer link ID to updated node if this concept is deprecated.")
    supersession_reason: str = Field("", description="Explanation of why this node has been superseded.")

    @field_validator("id")
    @classmethod
    def validate_id(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Node ID cannot be empty or pure whitespace.")
        return v.strip().lower()

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Node name cannot be empty or pure whitespace.")
        return v.strip()

    @field_validator("description")
    @classmethod
    def validate_description(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Node description cannot be empty or pure whitespace.")
        return v.strip()
