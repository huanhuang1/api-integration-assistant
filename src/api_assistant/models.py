from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class KnowledgeError(ValueError):
    """Missing, stale, or inconsistent knowledge. Never an unsupported user request."""


class ProviderError(RuntimeError):
    """The configured local model could not complete its task."""


class UserIntent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    goal: Literal["open_account", "other", "unknown"] = Field(
        description="The user's business goal. Transfers, closing accounts and loans are other."
    )
    customer_type: Literal["PERSONAL", "BUSINESS", "UNKNOWN"] = Field(
        description="Use explicit user evidence. Individual/person=PERSONAL; company=BUSINESS."
    )
    customer_status: Literal["NEW", "EXISTING", "UNKNOWN"] = Field(
        description="NEW only if the user says new, first-time or equivalent; never assume it."
    )
    currency: str = Field(
        description="Requested currency code, e.g. USD or EUR; UNKNOWN if absent."
    )
    verification_status: Literal["PASSED", "FAILED", "PENDING", "UNKNOWN"] = Field(
        description="A verification result stated by the user; UNKNOWN unless provided."
    )


class Selection(UserIntent):
    workflow_id: str = Field(
        description="Matching candidate ID for account opening, or NONE if no suitable candidate."
    )
    evidence: dict[str, str] = Field(default_factory=dict)


class IntentEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")
    customer_type: str = Field(
        description="Exact user words stating individual/personal or company/business. Empty string if unstated."
    )
    customer_status: str = Field(
        description="Exact user words stating the CUSTOMER is new or existing. Empty if unstated."
    )
    currency: str = Field(
        description="Exact user words stating currency. Empty string if unstated."
    )
    verification_status: str = Field(
        description="Exact user words reporting a verification result. Empty string if unstated."
    )


class GroundedIntent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    evidence: IntentEvidence
    facts: UserIntent


class Narration(BaseModel):
    model_config = ConfigDict(extra="forbid")
    overview: str = Field(
        description="One or two sentences introducing the selected workflow.", max_length=800
    )


class Answer(BaseModel):
    status: Literal["matched", "needs_clarification", "unsupported", "data_error", "model_error"]
    message: str
    workflow_id: str | None = None
    steps: list[dict[str, Any]] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    trace: dict[str, Any] = Field(default_factory=dict)
