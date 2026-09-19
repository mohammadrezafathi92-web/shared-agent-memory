import json
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

Text = Annotated[str, Field(min_length=1, max_length=12000)]
Key = Annotated[str, Field(min_length=1, max_length=200)]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1] = 1


class SessionStart(Contract):
    project_id: UUID
    external_session_id: Key
    task_key: Key | None = None
    parent_session_id: UUID | None = None


class EventAppend(Contract):
    session_id: UUID
    source_event_id: Key
    event_type: Literal["message", "tool_result", "session_start", "turn_end", "session_end"]
    occurred_at: datetime
    payload: dict

    @field_validator("occurred_at")
    @classmethod
    def aware_time(cls, value):
        if value.tzinfo is None:
            raise ValueError("occurred_at must include a timezone")
        return value

    @field_validator("payload")
    @classmethod
    def payload_limit(cls, value):
        if len(json.dumps(value, ensure_ascii=False).encode()) > 65536:
            raise ValueError("payload exceeds 64 KiB")
        return value


class DecisionRecord(Contract):
    session_id: UUID
    statement: Text
    rationale: Annotated[str, Field(max_length=12000)] = ""
    source_ids: list[UUID] = Field(default_factory=list, max_length=100)
    idempotency_key: Key
    supersedes_id: UUID | None = None
    expected_version: int | None = Field(default=None, ge=1)


class SessionCheckpoint(Contract):
    session_id: UUID
    summary: Text
    open_items: list[Annotated[str, Field(max_length=2000)]] = Field(
        default_factory=list, max_length=30
    )
    next_action: Annotated[str, Field(max_length=2000)] = ""
    last_event_id: UUID | None = None
    idempotency_key: Key


class MemorySearch(Contract):
    project_id: UUID
    query: Annotated[str, Field(max_length=1000)] = ""
    task_key: Key | None = None
    include_history: bool = False
    limit: int = Field(default=20, ge=1, le=100)


class ContextGet(Contract):
    project_id: UUID
    task_key: Key | None = None
    query: Annotated[str, Field(max_length=1000)] = ""
    token_budget: int = Field(default=3000, ge=256, le=8000)


class MemoryGet(Contract):
    memory_id: UUID


class SessionLink(Contract):
    source_session_id: UUID
    target_session_id: UUID
    relation_type: Literal["continues", "branches_from", "references"]


CONTRACTS = {
    "session_start": SessionStart,
    "event_append": EventAppend,
    "decision_record": DecisionRecord,
    "session_checkpoint": SessionCheckpoint,
    "memory_search": MemorySearch,
    "context_get": ContextGet,
    "memory_get": MemoryGet,
    "session_link": SessionLink,
}
