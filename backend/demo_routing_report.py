"""
demo_routing_report.py
Runs every event from demo_script.json through the RTE and prints:
  - event name, expected route, actual route, stage, score, rule/pattern matched, latency
  - routing distribution summary
  - pass/fail against expected_route
"""

import json
import time
from pathlib import Path
from schemas import NormalizedEvent
from schemas.enums import DeviceType, EventType
from rte import RTE
from rule_engine import RuleRegistry
from graph_repository import GraphRepository

HH_ID = "hh_xk92p_sharma"

# ── Load demo script ──────────────────────────────────────────
with open(Path("data") / "demo_script.json", encoding="utf-8") as f:
    demo_events = json.load(f)

# ── Boot RTE (load rules + promoted patterns once) ────────────
registry = RuleRegistry()
registry.load(HH_ID)
repo = GraphRepository()
promoted = repo.get_patterns(HH_ID, band="PROMOTED")
rte = RTE(rule_registry=registry, promoted_patterns=promoted)

# ── Map device_type strings to EventType ─────────────────────
_ET_MAP = {
    "schedule_event":       EventType.SCHEDULE_EVENT,
    "life_event":           EventType.LIFE_EVENT,
    "guest_arrival":        EventType.GUEST_ARRIVAL,
    "routine_trigger":      EventType.ROUTINE_TRIGGER,
    "health_alert":         EventType.HEALTH_ALERT,
    "festival_declaration": EventType.FESTIVAL_DECLARATION,
    "health_emergency":     EventType.HEALTH_EMERGENCY,
    "presence_update":      EventType.PRESENCE_UPDATE,
}

_DT_MAP = {
    "water_motor":    DeviceType.WATER_MOTOR,
    "geyser":         DeviceType.GEYSER,
    "pressure_cooker": DeviceType.PRESSURE_COOKER,
    "television":     DeviceType.TELEVISION,
    "smart_fridge":   DeviceType.SMART_FRIDGE,
    "ac":             DeviceType.AC,
    "light":          DeviceType.LIGHT,
}

# ── Run each event ────────────────────────────────────────────
results = []
for e in demo_events:
    raw = e["raw_payload"]

    # Determine event_type
    if e.get("device_type"):
        event_type = EventType.DEVICE_STATE
    else:
        et_str = raw.get("event_type", "life_event")
        event_type = _ET_MAP.get(et_str, EventType.LIFE_EVENT)

    device_type = _DT_MAP.get(e.get("device_type") or "", None)

    payload = {k: v for k, v in raw.items() if k != "event_type"}

    event = NormalizedEvent(
        household_id=HH_ID,
        event_type=event_type,
        device_type=device_type,
        device_id=e.get("device_id"),
        payload=payload,
    )

    start = time.monotonic()
    decision = rte.classify(event)
    latency_ms = (time.monotonic() - start) * 1000

    expected = e.get("expected_route", "")
    actual = decision.route.value
    match = "PASS" if actual == expected else "FAIL"

    results.append({
        "name":     e["event_name"],
        "expected": expected,
        "actual":   actual,
        "stage":    decision.stage_decided,
        "score":    decision.complexity_score,
        "matched":  decision.rule_matched or decision.pattern_matched or "-",
        "latency":  latency_ms,
        "verdict":  match,
    })

# ── Print results table ───────────────────────────────────────
print()
print("=" * 110)
print(f"{'EVENT':<40} {'EXPECTED':<14} {'ACTUAL':<14} {'ST':<4} {'SCORE':<7} {'MATCHED RULE':<36} {'LATENCY':>8}  OK?")
print("=" * 110)
for r in results:
    flag = "  OK" if r["verdict"] == "PASS" else "FAIL"
    print(
        f"{r['name']:<40} {r['expected']:<14} {r['actual']:<14} "
        f"{r['stage']:<4} {r['score']:<7} {r['matched']:<36} {r['latency']:>6.1f}ms  {flag}"
    )

# ── Distribution ──────────────────────────────────────────────
from collections import Counter
dist = Counter(r["actual"] for r in results)
total = len(results)
print()
print("=" * 50)
print("ROUTING DISTRIBUTION")
print("=" * 50)
for route, count in sorted(dist.items()):
    pct = count / total * 100
    print(f"  {route:<15} {count:>2} / {total}  ({pct:.0f}%)")

# ── Pass/fail summary ─────────────────────────────────────────
passed = sum(1 for r in results if r["verdict"] == "PASS")
failed = sum(1 for r in results if r["verdict"] == "FAIL")
print()
print(f"  Match vs expected_route: {passed}/{total} PASS, {failed}/{total} FAIL")
print("=" * 50)
