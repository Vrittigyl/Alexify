from typing import Any, Optional
from pydantic import BaseModel, Field
from .enums import ActionSource, ActionType, DeviceType, EventType, NotificationChannel, RulePriority, RuleType

class RuleTrigger(BaseModel):
    """What triggers the rule."""
    event_type: Optional[EventType] = None
    device_type: Optional[DeviceType] = None
    field: Optional[str] = None
    op: Optional[str] = None
    value: Optional[Any] = None

class RuleCondition(BaseModel):
    """Extra conditions evaluated after the trigger."""
    field: str
    op: str
    value: Any
    on_fail: Optional[str] = None

class RuleAction(BaseModel):
    """What the rule executes."""
    type: ActionType
    command: Optional[str] = None
    target_device_id: Optional[str] = None
    target_member_ids: Optional[list[str]] = None
    message_template: Optional[str] = None
    channel: Optional[NotificationChannel] = None
    timer_minutes: Optional[int] = None

class Rule(BaseModel):
    """Household rule definition."""
    household_id: str = Field(..., description="Use 'FLEET' for global rules")
    rule_id: str
    rule_type: RuleType
    rule_version: int = 1
    name: Optional[str] = None
    description: Optional[str] = None

    # Triggers & conditions
    trigger: RuleTrigger
    conditions: list[RuleCondition] = Field(default_factory=list)

    # Execution
    action: RuleAction

    # Settings
    safety_critical: bool = False
    override_allowed: bool = True
    idempotency_window_secs: Optional[int] = None
    active: bool = True

    # Pattern promotion tracking
    source_pattern_id: Optional[str] = None
    observation_days: Optional[int] = None
    original_confidence: Optional[float] = None
    demotion_trigger: Optional[str] = None

    @property
    def priority(self) -> int:
        """Returns numeric priority for resolving conflicts."""
        priority_map = {
            RuleType.SAFETY: RulePriority.SAFETY,
            RuleType.HEALTH: RulePriority.HEALTH,
            RuleType.CUSTOM: RulePriority.CUSTOM,
            RuleType.PROMOTED_PATTERN: RulePriority.PROMOTED_PATTERN,
            RuleType.FLEET: RulePriority.FLEET,
        }
        return priority_map.get(self.rule_type, RulePriority.FLEET).value

class EvaluationResult(BaseModel):
    """Result of evaluating a rule."""
    match: bool = False
    actions: list[RuleAction] = Field(default_factory=list)
    escalate_to_bedrock: bool = False
    reason: Optional[str] = None
    source: ActionSource = ActionSource.RULE_ENGINE
    rule_id: Optional[str] = None
    rule_version: Optional[int] = None
    explanation: Optional[str] = None
