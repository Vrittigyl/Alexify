from enum import Enum

class DeviceType(str, Enum):
    """Supported device types."""
    WATER_MOTOR = "water_motor"
    GEYSER = "geyser"
    PRESSURE_COOKER = "pressure_cooker"
    TELEVISION = "television"
    SMART_FRIDGE = "smart_fridge"
    AC = "ac"
    LIGHT = "light"

class EventType(str, Enum):
    """Recognized event types."""
    DEVICE_STATE = "device_state"
    LIFE_EVENT = "life_event"
    ROUTINE_TRIGGER = "routine_trigger"
    HEALTH_ALERT = "health_alert"
    GUEST_ARRIVAL = "guest_arrival"
    FESTIVAL_DECLARATION = "festival_declaration"
    HEALTH_EMERGENCY = "health_emergency"
    PRESENCE_UPDATE = "presence_update"
    SCHEDULE_EVENT = "schedule_event"

class ImpactLevel(str, Enum):
    """Urgency classification for events."""
    CRITICAL = "CRITICAL"    # Immediate action required
    HIGH = "HIGH"            # Act within seconds
    MEDIUM = "MEDIUM"        # Act within minutes
    LOW = "LOW"              # Informational
    INFO = "INFO"            # Log only

class RouteDecision(str, Enum):
    """Routing outcomes."""
    RULE_ENGINE = "RULE_ENGINE"
    BEDROCK = "BEDROCK"
    SUPPRESS = "SUPPRESS"

class ActionSource(str, Enum):
    """Ensures every action is traceable to its source."""
    RULE_ENGINE = "RULE_ENGINE"
    BEDROCK = "BEDROCK"
    SYSTEM = "SYSTEM"

class ActionType(str, Enum):
    """Available action types."""
    DEVICE_COMMAND = "device_command"
    NOTIFICATION = "notification"
    REMINDER = "reminder"
    TIMER_START = "timer_start"
    TIMER_CANCEL = "timer_cancel"
    SCHEDULE_ADJUST = "schedule_adjust"

class RuleType(str, Enum):
    """Rule priorities: safety > health > custom > promoted > fleet."""
    SAFETY = "safety"
    HEALTH = "health"
    CUSTOM = "custom"
    PROMOTED_PATTERN = "promoted_pattern"
    FLEET = "fleet"

class RulePriority(int, Enum):
    """Numeric priorities for conflict resolution (lower is higher priority)."""
    SAFETY = 1
    HEALTH = 2
    CUSTOM = 3
    PROMOTED_PATTERN = 4
    FLEET = 5

class ConfidenceBand(str, Enum):
    """Pattern lifecycle states based on confidence score."""
    OBSERVING = "OBSERVING"
    LEARNING = "LEARNING"
    PROMOTED = "PROMOTED"
    DEMOTED = "DEMOTED"
    RETIRED = "RETIRED"

class CircuitState(str, Enum):
    """Circuit breaker states for Bedrock."""
    CLOSED = "CLOSED"            # Normal
    OPEN = "OPEN"                # Down, fail-fast
    HALF_OPEN = "HALF_OPEN"      # Probing

class NotificationChannel(str, Enum):
    """Delivery channels for notifications."""
    ALEXA_VOICE = "alexa_voice"
    MOBILE_PUSH = "mobile_push"
    WHATSAPP = "whatsapp"
    SMS = "sms"
    VOICE_AND_MOBILE = "voice_and_mobile"

class ConsentLevel(str, Enum):
    """Consent levels for executing actions."""
    OBSERVE = "observe"          # Log only
    SUGGEST = "suggest"          # Prompt user
    AUTO_NOTIFY = "auto_notify"  # Execute and notify
    FULL_AUTO = "full_auto"      # Execute silently
