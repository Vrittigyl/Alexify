"""
schemas/onboarding.py
=====================
Pydantic models that define the canonical onboarding payload.
This is the contract between the browser onboarding flow and the backend.

POST /onboarding/preview  → OnboardingPayload → PreviewResponse
POST /onboarding/complete → OnboardingPayload → CompleteResponse
"""

from __future__ import annotations
from typing import Optional
from pydantic import BaseModel, Field


# ── Member ────────────────────────────────────────────────────

class OnboardingMember(BaseModel):
    """One family member as collected by the onboarding UI."""
    id: str                          # client-generated temp id (e.g. "abc123")
    name: str
    role: str                        # owner | partner | child | parent | grandparent | other
    age_group: str                   # baby | child | teen | adult | senior
    care_needs: list[str] = Field(default_factory=list)  # e.g. ["medicine_reminders"]


# ── Device ────────────────────────────────────────────────────

class OnboardingDevice(BaseModel):
    """One smart device as collected by the onboarding UI."""
    id: str                          # client-generated temp id
    name: str
    device_type: str                 # ac | tv | water_motor | geyser | fridge | ...
    room: str


# ── Routine ───────────────────────────────────────────────────

class OnboardingRoutine(BaseModel):
    """A selected household routine."""
    id: str                          # e.g. "medicine_morning"
    label: str
    time: Optional[str] = None       # e.g. "08:30"


# ── Payload ───────────────────────────────────────────────────

class OnboardingPayload(BaseModel):
    """
    Full onboarding payload sent by the browser on Step 9.
    All fields mirror the onboarding store state.
    """
    household_name: str
    household_city: str
    members: list[OnboardingMember]
    devices: list[OnboardingDevice] = Field(default_factory=list)
    routines: list[OnboardingRoutine] = Field(default_factory=list)
    priorities: list[str] = Field(default_factory=list)


# ── Response shapes ───────────────────────────────────────────

class GraphNodePreview(BaseModel):
    node_id: str
    node_type: str
    name: str
    attributes: dict = Field(default_factory=dict)


class GraphEdgePreview(BaseModel):
    from_node: str
    edge_type: str
    to_node: str
    attributes: dict = Field(default_factory=dict)


class PreviewResponse(BaseModel):
    valid: bool
    household_summary: dict
    graph_nodes: list[GraphNodePreview]
    graph_edges: list[GraphEdgePreview]
    warnings: list[str]


class CompleteResponse(BaseModel):
    household_id: str
    created_nodes: int
    created_edges: int
    member_node_ids: list[str]
    device_node_ids: list[str]
    routine_node_ids: list[str]
