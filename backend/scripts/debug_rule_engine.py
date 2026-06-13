"""
debug_rule_engine.py
Full execution trace for engine.run() returning 0 actions.
Prints every step with actual runtime values.
"""
import json
import sys

# ── Step 0: Import + event construction ──────────────────────
print("=" * 60)
print("STEP 0: Import and event construction")
print("=" * 60)

from schemas import NormalizedEvent
from schemas.enums import DeviceType, EventType

event = NormalizedEvent(
    household_id="hh_xk92p_sharma",
    event_type="device_state",
    device_type="water_motor",
    device_id="dev_water_motor_001",
    payload={"tank_level_percent": 96},
)

print(f"  event.household_id   : {event.household_id!r}")
print(f"  event.event_type     : {event.event_type!r}  (type={type(event.event_type).__name__})")
print(f"  event.device_type    : {event.device_type!r}  (type={type(event.device_type).__name__})")
print(f"  event.payload        : {event.payload}")
print(f"  event.event_type.val : {event.event_type.value!r}")
print(f"  event.device_type.val: {event.device_type.value!r}")

# ── Step 1: Rule loading ──────────────────────────────────────
print("\n" + "=" * 60)
print("STEP 1: Rule loading from DynamoDB")
print("=" * 60)

from rule_engine import RuleRegistry
from schemas import Rule

registry = RuleRegistry()
registry.load("hh_xk92p_sharma")

all_rules = registry.all_rules()
print(f"  Total rules loaded: {len(all_rules)}")
for r in all_rules:
    print(f"  - {r.rule_id:<40} type={r.rule_type.value:<18} active={r.active}")

# Check specifically for our target rule
target = next((r for r in all_rules if r.rule_id == "rl_water_motor_tank_full"), None)
if target:
    print(f"\n  [FOUND] rl_water_motor_tank_full")
    print(f"    trigger.event_type : {target.trigger.event_type!r}")
    print(f"    trigger.device_type: {target.trigger.device_type!r}")
    print(f"    trigger.field      : {target.trigger.field!r}")
    print(f"    trigger.op         : {target.trigger.op!r}")
    print(f"    trigger.value      : {target.trigger.value!r}  (type={type(target.trigger.value).__name__})")
    print(f"    active             : {target.active}")
    print(f"    idempotency_window : {target.idempotency_window_secs!r}")
else:
    print("\n  [MISSING] rl_water_motor_tank_full NOT FOUND in registry")

# ── Step 2: Registry index inspection ────────────────────────
print("\n" + "=" * 60)
print("STEP 2: Registry cache keys")
print("=" * 60)

for key, rules in registry._cache.items():
    print(f"  key={key!r}  ->  {[r.rule_id for r in rules]}")

# What key would our event produce?
et_val = event.event_type.value if event.event_type else None
dt_val = event.device_type.value if event.device_type else None
print(f"\n  Event lookup keys (in order tried):")
print(f"    1. ({et_val!r}, {dt_val!r})")
print(f"    2. ({et_val!r}, None)")
print(f"    3. (None, {dt_val!r})")
print(f"    4. (None, None)")

# ── Step 3: Candidate selection ───────────────────────────────
print("\n" + "=" * 60)
print("STEP 3: Candidate rule selection")
print("=" * 60)

candidates = registry.get_candidates("hh_xk92p_sharma", event)
print(f"  Total candidates returned: {len(candidates)}")
for c in candidates:
    print(f"  - {c.rule_id}")

# ── Step 4: Trigger evaluation ────────────────────────────────
print("\n" + "=" * 60)
print("STEP 4: Trigger evaluation")
print("=" * 60)

from rule_engine import RuleEvaluationEngine

evaluator = RuleEvaluationEngine()

for rule in candidates:
    print(f"\n  Rule: {rule.rule_id}")
    trigger = rule.trigger

    # event_type check
    et_match = True
    if trigger.event_type is not None:
        et_match = event.event_type == trigger.event_type
    print(f"    event_type check : trigger={trigger.event_type!r} vs event={event.event_type!r}  →  match={et_match}")

    # device_type check
    dt_match = True
    if trigger.device_type is not None:
        dt_match = event.device_type == trigger.device_type
    print(f"    device_type check: trigger={trigger.device_type!r} vs event={event.device_type!r}  →  match={dt_match}")

    # field/op/value check
    fv_match = True
    if trigger.field and trigger.op and trigger.value is not None:
        field_val = event.payload.get(trigger.field)
        print(f"    field={trigger.field!r}  payload_val={field_val!r} (type={type(field_val).__name__})")
        print(f"    op={trigger.op!r}  trigger_val={trigger.value!r} (type={type(trigger.value).__name__})")
        try:
            cmp_result = evaluator._compare(field_val, trigger.op, trigger.value)
            print(f"    compare({field_val!r}, {trigger.op!r}, {trigger.value!r}) = {cmp_result}")
            fv_match = cmp_result
        except Exception as e:
            print(f"    compare() EXCEPTION: {e}")
            fv_match = False
    else:
        print(f"    no field/op/value check (field={trigger.field!r})")

    overall = et_match and dt_match and fv_match
    print(f"    TRIGGER MATCHES: {overall}")

# ── Step 5: Full EvaluationResult ────────────────────────────
print("\n" + "=" * 60)
print("STEP 5: Full evaluation result")
print("=" * 60)

for rule in candidates:
    result = evaluator.evaluate(event, {}, rule)
    print(f"  Rule: {rule.rule_id}")
    print(f"    match              : {result.match}")
    print(f"    escalate_to_bedrock: {result.escalate_to_bedrock}")
    print(f"    reason             : {result.reason!r}")
    print(f"    explanation        : {result.explanation!r}")
    print(f"    actions            : {len(result.actions)}")

# ── Step 6: Idempotency state ─────────────────────────────────
print("\n" + "=" * 60)
print("STEP 6: Idempotency cache state")
print("=" * 60)
print(f"  Cache entries: {len(evaluator._idempotency_cache)}")
for k, v in evaluator._idempotency_cache.items():
    print(f"  {k}: expires={v}")

# ── Step 7: Full engine.run() ─────────────────────────────────
print("\n" + "=" * 60)
print("STEP 7: engine.run() end-to-end")
print("=" * 60)

from rule_engine import RuleEngine
engine = RuleEngine()
# Force reload so we use the same DynamoDB data
engine._registry.load("hh_xk92p_sharma")

actions = engine.run(event)
print(f"  Actions returned: {len(actions)}")
for a in actions:
    print(f"  - action_type={a.action_type!r}  command={a.command!r}  source={a.source!r}  rule_id={a.rule_id!r}")

# ── Step 8: Test audit — why did 11/11 pass? ──────────────────
print("\n" + "=" * 60)
print("STEP 8: Test blindspot analysis")
print("=" * 60)
print("  All automated tests construct Rule objects directly in-memory.")
print("  They never call registry.load() or go through DynamoDB.")
print("  => Any bug in loading/deserializing/indexing rules from DynamoDB")
print("     would be invisible to the test suite.")
