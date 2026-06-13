"""
main.py — SAATHI FastAPI Application v2.1
==========================================
Phase 10: Full pipeline wired. WebSocket hub. 13 REST endpoints.
Phase 11 (Production Readiness):
  - Structured JSON logging via services/logging_config.py
  - Request correlation ID middleware (X-Request-ID)
  - API key authentication middleware (X-API-Key, bypassed in dev_mode)
  - CORS restricted to settings.allowed_origins (wildcard only in dev_mode)
  - ActionPlanner promoted to module-level singleton (rate limiter now persists)
  - /health returns HTTP 503 when DynamoDB is unavailable

Run:
    uvicorn main:app --reload --port 8000

Endpoints:
  System:
    GET  /health
    POST /admin/seed

  Events:
    POST /events/ingest          — raw device payload → full pipeline
    POST /simulate/event/{name}  — fire named demo event

  RTE:
    GET  /rte/decision/{event_id}

  Metrics:
    GET  /metrics
    GET  /metrics/circuit-breaker

  Knowledge Graph:
    GET  /graph/{household_id}
    GET  /graph/{household_id}/members
    GET  /graph/{household_id}/devices

  Rules:
    GET  /rules
    POST /rules/reload

  Patterns:
    GET  /patterns
    POST /patterns/promote

  WebSocket:
    WS   /ws/{household_id}
"""

import asyncio
import logging
import time
import uuid
from contextlib import asynccontextmanager
from typing import Any
from mangum import Mangum

import uvicorn
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

# ── Configure structured JSON logging FIRST ──────────────────────
# Must be done before any other import that touches logging.
from services.logging_config import (
    configure_logging,
    request_id_var,
    household_id_var,
    event_id_var,
)
configure_logging()

from backend.services.action_planner import ActionPlanner
from backend.services.bedrock_layer import BedrockLayer, BedrockCircuitBreaker, ContextBuilder
from backend.config import settings
from backend.services.context_engine import ContextEngine
from backend.db.dynamo_client import health_check
from backend.db.seed_dynamo import run_full_seed
from backend.services.device_command_bus import DeviceCommandBus
from backend.services.event_batcher import EventBatcher
from backend.event_simulator import EventSimulator
from backend.graph_repository import GraphRepository
from backend.knowledge_graph import KnowledgeGraph
from backend.services.metrics_service import MetricsService
from backend.services.notification_service import NotificationService
from backend.services.pattern_engine import PatternEngine
from backend.services.presence_service import PresenceService
from backend.engines.rule_engine import RuleEngine
from backend.engines.rte import RTE
from backend.schemas import NormalizedEvent
from backend.schemas.actions import Action, Notification
from backend.schemas.enums import ActionType, ImpactLevel, RouteDecision
from backend.schemas.websocket import WSEventType, WSMessage
logger = logging.getLogger("saathi")

HH_ID = settings.household_id

# Protected endpoint prefixes — require X-API-Key when dev_mode=False
_PROTECTED_PREFIXES = ("/admin", "/simulate", "/rules/reload", "/patterns/promote")
# Paths always exempt from API key check (health probes, docs)
_EXEMPT_PATHS = {"/health", "/docs", "/redoc", "/openapi.json", "/ws"}


# ─────────────────────────────────────────────────────────────
# 10.6  WebSocket ConnectionManager
# ─────────────────────────────────────────────────────────────

class ConnectionManager:
    """Maintains per-household WebSocket connections and broadcasts typed messages."""

    def __init__(self):
        self._connections: dict[str, list[WebSocket]] = {}
        self.pod_id = uuid.uuid4().hex

    async def connect(self, household_id: str, ws: WebSocket) -> None:
        await ws.accept()
        self._connections.setdefault(household_id, []).append(ws)
        logger.info(f"WS: connected household={household_id} total={len(self._connections[household_id])}")

    def disconnect(self, household_id: str, ws: WebSocket) -> None:
        conns = self._connections.get(household_id, [])
        if ws in conns:
            conns.remove(ws)

    async def broadcast(self, household_id: str, event_type: str, data: dict) -> None:
        """Primary API. Performs local broadcast, then attempts to publish to Redis."""
        await self._local_broadcast(household_id, event_type, data)

        try:
            await self._publish_to_redis(household_id, event_type, data)
        except Exception as e:
            logger.warning(f"WS: Redis publish failed, falling back to local only: {e}")

    async def _local_broadcast(self, household_id: str, event_type: str, data: dict) -> None:
        """Sends the message to all connected WebSockets on THIS specific pod."""
        msg = WSMessage(
            type=WSEventType(event_type),
            household_id=household_id,
            data=data,
        )
        payload = msg.model_dump(mode="json")
        stale = []
        for ws in self._connections.get(household_id, []):
            try:
                await ws.send_json(payload)
            except Exception:
                stale.append(ws)
        for ws in stale:
            self.disconnect(household_id, ws)

    async def _publish_to_redis(self, household_id: str, event_type: str, data: dict) -> None:
        """Publishes the message to the global Redis channel for fanout."""
        import json
        import time
        from db.redis_client import redis_client
        if not redis_client.enabled or not redis_client._redis:
            return

        payload = json.dumps({
            "household_id": household_id,
            "event_type": event_type,
            "data": data,
            "request_id": request_id_var.get(""),
            "timestamp": time.time(),
            "origin_pod_id": self.pod_id
        })
        await redis_client._redis.publish("saathi:v1:ws:broadcast", payload)

    async def start_subscriber(self) -> None:
        """Background loop listening for distributed WS broadcasts."""
        import json
        import asyncio
        from db.redis_client import redis_pubsub_client

        backoff = 1
        max_backoff = 30

        while True:
            try:
                if not redis_pubsub_client.enabled:
                    await asyncio.sleep(5)
                    continue

                if not redis_pubsub_client.connected:
                    await redis_pubsub_client.connect()

                if not redis_pubsub_client._redis:
                    await asyncio.sleep(5)
                    continue

                pubsub = redis_pubsub_client._redis.pubsub()
                await pubsub.subscribe("saathi:v1:ws:broadcast")
                logger.info("WS Subscriber: Connected and listening to saathi:v1:ws:broadcast")
                
                # Reset backoff on successful connection
                backoff = 1

                async for message in pubsub.listen():
                    if message["type"] == "message":
                        try:
                            msg = json.loads(message["data"])
                            # Self-echo prevention
                            if msg.get("origin_pod_id") == self.pod_id:
                                continue
                            
                            # Deliver locally. Subscriber MUST NEVER call public `broadcast()`
                            await self._local_broadcast(
                                msg["household_id"],
                                msg["event_type"],
                                msg["data"]
                            )
                        except Exception as e:
                            logger.error(f"WS Subscriber parse error: {e}")
            except Exception as e:
                logger.warning(f"WS Subscriber connection lost: {e}. Retrying in {backoff}s...")
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, max_backoff)

    def connection_count(self, household_id: str) -> int:
        return len(self._connections.get(household_id, []))


# ─────────────────────────────────────────────────────────────
# Singletons — shared across all requests
# ─────────────────────────────────────────────────────────────

ws_manager = ConnectionManager()

graph_repo = GraphRepository()
presence   = PresenceService()
kg         = KnowledgeGraph(graph_repo)
ctx_engine = ContextEngine(graph_repo, presence)
rule_engine = RuleEngine()
circuit_breaker = BedrockCircuitBreaker()
bedrock    = BedrockLayer(circuit_breaker=circuit_breaker, mock_mode=settings.bedrock_mock_mode)
ctx_builder = ContextBuilder()
batcher    = EventBatcher()
pattern_engine = PatternEngine(graph_repo)
metrics    = MetricsService(HH_ID)
notif_svc  = NotificationService()
cmd_bus    = DeviceCommandBus()
# ── P1: ActionPlanner promoted to module-level singleton ────────────────
# The _rate_tracker dict now persists across all requests on this pod.
# broadcast_fn is injected per-request via plan(..., broadcast_fn=fn).
action_planner = ActionPlanner()

# Load promoted patterns for RTE Stage2
_promoted_cache: list[dict] = []
rte_engine: RTE | None = None


# ─────────────────────────────────────────────────────────────
# Lifespan
# ─────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    global rte_engine, _promoted_cache
    logger.info("=" * 60)
    logger.info("  SAATHI v2.0 — Starting up")
    logger.info(f"  Household    : {HH_ID}")
    logger.info(f"  Bedrock Mock : {settings.bedrock_mock_mode}")
    logger.info(f"  RTE Threshold: {settings.bedrock_complexity_threshold}")
    logger.info("=" * 60)

    dynamo = health_check()
    logger.info(f"  DynamoDB: {dynamo['status']}")

    # Boot rule registry
    rule_engine._registry.load(HH_ID)

    # Boot promoted patterns for RTE Stage2
    _promoted_cache = graph_repo.get_patterns(HH_ID, band="PROMOTED")
    rte_engine = RTE(rule_registry=rule_engine._registry, promoted_patterns=_promoted_cache)

    # Update metrics pattern counts
    all_patterns = graph_repo.get_patterns(HH_ID)
    promoted = [p for p in all_patterns if p.get("confidence_band") == "PROMOTED"]
    metrics.update_pattern_counts(
        active=len(all_patterns),
        promoted=len(promoted),
        learning=len([p for p in all_patterns if p.get("confidence_band") == "LEARNING"]),
        observing=len([p for p in all_patterns if p.get("confidence_band") == "OBSERVING"]),
    )
    
    # ── Phase 3.1: Initialize Redis Foundation ─────────────────
    from db.redis_client import redis_client, redis_pubsub_client
    await redis_client.connect()
    # The pubsub client connects automatically in its background loops, but we can explicitly connect here
    await redis_pubsub_client.connect()

    # ── Phase 3.4: Start Presence Pub/Sub ──────────────────────
    from services.task_tracker import task_tracker

    logger.info("  Starting Pub/Sub subscribers...")
    # These run forever until app shuts down
    task_tracker.spawn(presence.start_subscriber, fallback="drop")
    task_tracker.spawn(ws_manager.start_subscriber, fallback="drop")

    logger.info(f"  Rules loaded : {len(rule_engine._registry._raw_rules)}")
    logger.info(f"  Patterns     : {len(all_patterns)} ({len(promoted)} promoted)")
    logger.info("  SAATHI ready.")

    try:
        yield
    finally:
        logger.info("  SAATHI — Shutting down")
        # ── Phase 3.6: Clean task shutdown ─────────────────────────
        logger.info("  Draining background tasks...")
        await task_tracker.shutdown(timeout=5.0)
        
        await redis_client.close()
        await redis_pubsub_client.close()
        logger.info("============================================================")


# ─────────────────────────────────────────────────────────────
# App
# ─────────────────────────────────────────────────────────────

app = FastAPI(
    title="SAATHI",
    description=(
        "Smart Anticipatory Automation for The Home Intelligence — "
        "Two-Path Architecture: Rule Engine + AWS Bedrock"
    ),
    version="2.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# ── P1: Request Correlation ID middleware ─────────────────────────
# Generates a UUID per request and stores it in a contextvar so every
# logger call in the same coroutine automatically includes request_id.
@app.middleware("http")
async def correlation_id_middleware(request: Request, call_next):
    rid = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    request_id_var.set(rid)
    # Best-effort: set household_id from path param if present
    path_parts = request.url.path.split("/")
    if len(path_parts) >= 3 and path_parts[1] in ("graph", "ws"):
        household_id_var.set(path_parts[2])
    response = await call_next(request)
    response.headers["X-Request-ID"] = rid
    return response


# ── P1: API Key authentication middleware ──────────────────────
# Bypassed entirely when dev_mode=True (default for tests + local dev).
# In production (dev_mode=False), all non-exempt endpoints require
# the X-API-Key header matching settings.api_key.
@app.middleware("http")
async def api_key_middleware(request: Request, call_next):
    if settings.dev_mode:
        return await call_next(request)

    # Always exempt: health probes, API docs, WebSocket upgrades
    path = request.url.path
    if path in _EXEMPT_PATHS or path.startswith("/ws"):
        return await call_next(request)

    api_key = request.headers.get("X-API-Key", "")
    if api_key != settings.api_key:
        logger.warning(f"Rejected request: missing/invalid X-API-Key path={path}")
        return JSONResponse(
            status_code=401,
            content={"detail": "Missing or invalid X-API-Key header"},
            headers={"X-Request-ID": request_id_var.get("")},
        )
    return await call_next(request)


# ── P1: CORS ───────────────────────────────────────────────
# dev_mode=True  → ["*"]  (preserves current open behaviour)
# dev_mode=False → explicit list from ALLOWED_ORIGINS env var

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─────────────────────────────────────────────────────────────
# Full pipeline function
# ─────────────────────────────────────────────────────────────

async def run_full_pipeline(event: NormalizedEvent) -> dict[str, Any]:
    """
    Routes an event through the complete SAATHI pipeline:
    RTE → Rule Engine OR Bedrock → Action Planner → Dispatch
    Returns a result dict suitable for both API responses and WebSocket broadcast.
    """
    start = time.monotonic()

    # 1. Build context
    context = await ctx_engine.build(event, event.household_id)

    # 2. RTE classify
    decision = rte_engine.classify(event, context.model_dump(mode="json"))
    route = decision.route

    # Emit RTE decision via WebSocket
    await ws_manager.broadcast(event.household_id, WSEventType.RTE_DECISION.value, {
        "event_id": event.event_id,
        "route": route.value,
        "stage": decision.stage_decided,
        "score": decision.complexity_score,
        "rule_matched": decision.rule_matched,
        "pattern_matched": decision.pattern_matched,
    })

    proposed_actions: list[Action] = []
    bedrock_response = None

    # 3. Route
    if route == RouteDecision.RULE_ENGINE:
        re_start = time.monotonic()
        proposed_actions = await rule_engine.run(event)
        re_latency = (time.monotonic() - re_start) * 1000
        metrics.record_rule_engine(re_latency)

        await ws_manager.broadcast(event.household_id, WSEventType.RULE_ENGINE_RESULT.value, {
            "event_id": event.event_id,
            "actions_count": len(proposed_actions),
            "latency_ms": round(re_latency, 1),
        })

    elif route == RouteDecision.BEDROCK:
        bk_start = time.monotonic()
        batcher.add(event)

        # Build bedrock context
        batch = batcher.flush(event.household_id) or [event]
        rule_handled = [decision.rule_matched] if decision.rule_matched else []
        bedrock_ctx = ctx_builder.build_bedrock_context(
            batch, context,
            rule_engine_already_handled=rule_handled,
        )

        await ws_manager.broadcast(event.household_id, WSEventType.BEDROCK_REQUEST.value, {
            "event_id": event.event_id,
            "estimated_tokens": bedrock_ctx.estimated_tokens,
        })

        bedrock_response = bedrock.invoke(bedrock_ctx, event.household_id)
        bk_latency = (time.monotonic() - bk_start) * 1000
        metrics.record_bedrock(bk_latency, bedrock_response.total_tokens)
        metrics.update_circuit_breaker(circuit_breaker.state)

        await ws_manager.broadcast(event.household_id, WSEventType.BEDROCK_RESPONSE.value, {
            "event_id": event.event_id,
            "actions_count": len(bedrock_response.actions),
            "tokens": bedrock_response.total_tokens,
            "confidence": bedrock_response.confidence,
            "latency_ms": round(bk_latency, 1),
        })

        # Convert Bedrock raw action dicts → Action objects
        from schemas.enums import ActionSource, NotificationChannel
        for raw in bedrock_response.actions:
            at = raw.get("action_type", "notification")
            try:
                action = Action(
                    household_id=event.household_id,
                    action_type=ActionType(at),
                    source=ActionSource.BEDROCK,
                    device_id=raw.get("device_id"),
                    command=raw.get("command"),
                    target_member_ids=raw.get("target_member_ids", []),
                    message=raw.get("message"),
                    channel=NotificationChannel(raw["channel"]) if raw.get("channel") else None,
                    bedrock_request_id=bedrock_response.request_id,
                    event_id=event.event_id,
                )
                proposed_actions.append(action)
            except Exception as e:
                logger.warning(f"Pipeline: could not convert Bedrock action: {e}")

        # Ingest suggested patterns
        if bedrock_response.suggested_patterns:
            pattern_engine.ingest_suggestions(event.household_id, bedrock_response.suggested_patterns)

    else:
        # SUPPRESS
        metrics.record_suppressed()

    # 4. Action Planner — use module-level singleton; inject per-request broadcast_fn
    approved = await action_planner.plan(
        proposed_actions,
        context,
        broadcast_fn=lambda et, d: ws_manager.broadcast(event.household_id, et, d),
    )

    await ws_manager.broadcast(event.household_id, WSEventType.ACTION_PLANNED.value, {
        "event_id": event.event_id,
        "proposed": len(proposed_actions),
        "approved": len(approved),
    })

    # 5. Dispatch
    dispatched_results = []
    for action in approved:
        await ws_manager.broadcast(event.household_id, WSEventType.ACTION_PLANNED.value, {
            "action_id": action.action_id,
            "action_type": action.action_type.value,
            "device_id": action.device_id,
            "command": action.command,
            "source": action.source.value,
        })

        if action.action_type == ActionType.DEVICE_COMMAND:
            result = await cmd_bus.dispatch(action)
            metrics.record_action_dispatched()
            dispatched_results.append({
                "action_id": action.action_id,
                "type": "device_command",
                "device_id": action.device_id,
                "command": action.command,
                "success": result.success,
                "latency_ms": round(result.latency_ms, 1),
            })
            await ws_manager.broadcast(event.household_id, WSEventType.COMMAND_DISPATCHED.value, {
                "action_id": action.action_id,
                "device_id": action.device_id,
                "command": action.command,
                "success": result.success,
            })

        elif action.action_type == ActionType.NOTIFICATION:
            notif = notif_svc.from_action(action)
            sent = await notif_svc.notify(notif)
            if sent:
                metrics.record_notification_sent()
            else:
                metrics.record_rate_limited()
            dispatched_results.append({
                "action_id": action.action_id,
                "type": "notification",
                "target_members": action.target_member_ids,
                "sent": sent,
            })
            await ws_manager.broadcast(event.household_id, WSEventType.NOTIFICATION_SENT.value, {
                "action_id": action.action_id,
                "sent": sent,
                "members": action.target_member_ids,
            })

    total_latency = (time.monotonic() - start) * 1000
    return {
        "event_id": event.event_id,
        "route": route.value,
        "stage": decision.stage_decided,
        "complexity_score": decision.complexity_score,
        "actions_proposed": len(proposed_actions),
        "actions_approved": len(approved),
        "dispatched": dispatched_results,
        "actions_count": len(dispatched_results),
        "total_latency_ms": round(total_latency, 1),
    }


# ─────────────────────────────────────────────────────────────
# 10.6  WebSocket endpoint
# ─────────────────────────────────────────────────────────────

@app.websocket("/ws/{household_id}")
async def websocket_endpoint(websocket: WebSocket, household_id: str):
    await ws_manager.connect(household_id, websocket)
    try:
        while True:
            await websocket.receive_text()   # keep alive
    except WebSocketDisconnect:
        ws_manager.disconnect(household_id, websocket)
        logger.info(f"WS: disconnected household={household_id}")


# ─────────────────────────────────────────────────────────────
# 10.7  REST endpoints
# ─────────────────────────────────────────────────────────────

# ── System ───────────────────────────────────────────────────

@app.get("/health", tags=["System"])
async def health():
    """
    AWS ALB / ECS health check endpoint.
    DynamoDB unavailable → 503 so ALB/ECS stops routing to this pod.
    Redis unavailable → 200 OK (degraded) because system gracefully falls back.
    """
    dynamo = health_check()
    from db.redis_client import redis_client
    redis_health = redis_client.get_health()

    status = "ok" if redis_health["connected"] or not redis_health["enabled"] else "degraded"

    body = {
        "status": status,
        "household_id": HH_ID,
        "version": "2.1.0",
        "bedrock_mock_mode": settings.bedrock_mock_mode,
        "dynamo": dynamo["status"],
        "dynamo_region": dynamo.get("region", settings.aws_region),
        "redis": redis_health,
        "dev_mode": settings.dev_mode,
        "ws_connections": ws_manager.connection_count(HH_ID),
    }

    if dynamo["status"] == "unavailable":
        body["status"] = "unavailable"
        return JSONResponse(status_code=503, content=body)

    return body


@app.post("/admin/seed", tags=["Admin"])
async def seed_database():
    try:
        result = run_full_seed()
        return {"status": "ok", "summary": result}
    except Exception as e:
        logger.exception("Seeding failed")
        raise HTTPException(status_code=500, detail=str(e))


# ── Events ───────────────────────────────────────────────────

class RawEventRequest(BaseModel):
    household_id: str = HH_ID
    device_type: str | None = None
    device_id: str | None = None
    event_type: str = "device_state"
    payload: dict[str, Any] = {}
    impact_level: str = "MEDIUM"


@app.post("/events/ingest", tags=["Events"])
async def ingest_event(req: RawEventRequest):
    """
    Ingest a raw event through the full SAATHI pipeline.
    RTE → Rule Engine / Bedrock → Action Planner → Dispatch.
    """
    from schemas.enums import DeviceType, EventType, ImpactLevel
    _DT = {
        "water_motor": DeviceType.WATER_MOTOR, "geyser": DeviceType.GEYSER,
        "pressure_cooker": DeviceType.PRESSURE_COOKER, "television": DeviceType.TELEVISION,
        "smart_fridge": DeviceType.SMART_FRIDGE, "ac": DeviceType.AC, "light": DeviceType.LIGHT,
    }
    _ET = {
        "device_state": EventType.DEVICE_STATE, "life_event": EventType.LIFE_EVENT,
        "guest_arrival": EventType.GUEST_ARRIVAL, "routine_trigger": EventType.ROUTINE_TRIGGER,
        "schedule_event": EventType.SCHEDULE_EVENT, "health_emergency": EventType.HEALTH_EMERGENCY,
        "festival_declaration": EventType.FESTIVAL_DECLARATION,
    }
    event = NormalizedEvent(
        household_id=req.household_id,
        event_type=_ET.get(req.event_type, EventType.DEVICE_STATE),
        device_type=_DT.get(req.device_type or "", None),
        device_id=req.device_id,
        payload=req.payload,
        impact_level=ImpactLevel(req.impact_level),
    )

    await ws_manager.broadcast(req.household_id, WSEventType.EVENT_INGESTED.value, {
        "event_id": event.event_id,
        "event_type": event.event_type.value,
        "device_type": event.device_type.value if event.device_type else None,
    })

    result = await run_full_pipeline(event)
    return result


_NAMED_EVENTS = {
    "water_tank_full":          "water_tank_full",
    "board_exam":               "board_exam",
    "guest_arrival":            "guest_arrival",
    "pressure_cooker_5_whistles": "pressure_cooker_5_whistles",
    "dadaji_medicine":          "dadaji_medicine",
    "fridge_door_open":         "fridge_door_open",
}


@app.post("/simulate/event/{event_name}", tags=["Simulate"])
async def simulate_named_event(event_name: str):
    """Fire a named demo event through the full pipeline."""
    sim = EventSimulator(HH_ID, run_full_pipeline)

    builders = {
        "water_tank_full":          sim.water_tank_full,
        "board_exam":               sim.board_exam,
        "guest_arrival":            sim.guest_arrival,
        "pressure_cooker_5_whistles": sim.pressure_cooker_5_whistles,
        "dadaji_medicine":          sim.dadaji_medicine,
        "fridge_door_open":         sim.fridge_door_open,
    }

    if event_name not in builders:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown event '{event_name}'. Valid: {list(builders.keys())}"
        )

    event = builders[event_name]()
    result = await run_full_pipeline(event)
    return result


@app.post("/simulate/demo", tags=["Simulate"])
async def run_full_demo():
    """Async playback of all 10 demo_script.json events at 10x speed."""
    sim = EventSimulator(HH_ID, run_full_pipeline, speed_multiplier=10.0)
    results = await sim.run_demo()
    return {"status": "complete", "events_processed": len(results), "results": results}


# ── Metrics ──────────────────────────────────────────────────

@app.get("/metrics", tags=["Metrics"])
async def get_metrics():
    """Return full DashboardMetrics snapshot."""
    m = metrics.get_dashboard_metrics()
    return m.model_dump(mode="json")


@app.get("/metrics/circuit-breaker", tags=["Metrics"])
async def get_circuit_breaker():
    """Return Bedrock circuit breaker state."""
    return circuit_breaker.get_state_dict()


# ── Knowledge Graph ───────────────────────────────────────────

@app.get("/graph/{household_id}", tags=["Graph"])
async def get_graph(household_id: str):
    """Return full graph: nodes + edge summary."""
    try:
        subgraph = kg.get_subgraph_for_bedrock(household_id, "dev_water_motor_001")
        return {
            "household_id": household_id,
            "graph_version": graph_repo.get_graph_version(household_id),
            "status": "loaded",
            "subgraph_nodes": len(subgraph.get("nodes", [])),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/graph/{household_id}/members", tags=["Graph"])
async def get_members(household_id: str):
    """Return member nodes affected by board exam life event."""
    try:
        members = kg.get_affected_members_with_constraints(household_id, "le_rohan_boards")
    except Exception:
        members = []
    return {"household_id": household_id, "members": members}


@app.get("/graph/{household_id}/devices", tags=["Graph"])
async def get_devices(household_id: str):
    """Return device impact context for the water motor."""
    try:
        ctx = kg.get_device_impact(household_id, "dev_water_motor_001")
    except Exception:
        ctx = {}
    return {"household_id": household_id, "device_context": ctx}


# ── Rules ────────────────────────────────────────────────────

@app.get("/rules", tags=["Rules"])
async def get_rules():
    """List all active rules in the registry."""
    rules = rule_engine._registry._raw_rules
    return {
        "count": len(rules),
        "rules": [
            {
                "rule_id": r.rule_id,
                "rule_type": r.rule_type.value if hasattr(r.rule_type, 'value') else str(r.rule_type),
                "active": r.active,
                "priority": r.priority if isinstance(r.priority, int) else (r.priority.value if r.priority else None),
            }
            for r in rules
        ],
    }


@app.post("/rules/reload", tags=["Rules"])
async def reload_rules():
    """Force-refresh the rule registry from DynamoDB."""
    # Clear cache timestamp so load() fetches fresh data
    rule_engine._registry._last_load = 0.0
    rule_engine._registry.load(HH_ID)
    return {"status": "ok", "rules_loaded": len(rule_engine._registry._raw_rules)}


# ── Patterns ─────────────────────────────────────────────────

@app.get("/patterns", tags=["Patterns"])
async def get_patterns():
    """Return all patterns with their confidence bands."""
    patterns = graph_repo.get_patterns(HH_ID)
    return {
        "count": len(patterns),
        "patterns": [
            {
                "pattern_id": p.get("pattern_id"),
                "confidence": float(p.get("confidence", 0)),
                "confidence_band": p.get("confidence_band"),
                "observation_days": p.get("observation_days", 0),
                "promoted_rule_id": p.get("promoted_rule_id"),
            }
            for p in patterns
        ],
    }


@app.post("/patterns/promote", tags=["Patterns"])
async def run_promotion():
    """Scan all patterns and promote eligible ones."""
    newly_promoted = pattern_engine.promote_if_eligible(HH_ID)
    return {"status": "ok", "newly_promoted": newly_promoted}


# ─────────────────────────────────────────────────────────────
# Entrypoint
# ─────────────────────────────────────────────────────────────
# AWS Lambda entrypoint
handler = Mangum(app, lifespan="on")

if __name__ == "__main__":
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
