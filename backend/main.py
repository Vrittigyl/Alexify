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

from services.action_planner import ActionPlanner
from services.bedrock_layer import BedrockLayer, BedrockCircuitBreaker, ContextBuilder
from config import settings
from services.context_engine import ContextEngine
from db.dynamo_client import health_check, get_table
from db.seed_dynamo import run_full_seed
from services.device_command_bus import DeviceCommandBus
from services.event_batcher import EventBatcher
from event_simulator import EventSimulator
from graph_repository import GraphRepository
from knowledge_graph import KnowledgeGraph
from services.metrics_service import MetricsService
from services.notification_service import NotificationService
from services.pattern_engine import PatternEngine
from services.presence_service import PresenceService
from engines.rule_engine import RuleEngine
from engines.rte import RTE
from schemas import NormalizedEvent
from schemas.actions import Action, Notification
from schemas.enums import ActionType, EventType, ImpactLevel, RouteDecision
from schemas.websocket import WSEventType, WSMessage
from schemas.onboarding import OnboardingPayload, PreviewResponse, CompleteResponse
from services.onboarding_service import OnboardingService
from services.bootstrap_engine import BootstrapEngine

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

# ── Bootstrap engine — per-request injection of pipeline_fn ────────────────
# Instantiated lazily on first use via _get_bootstrap_engine()
_bootstrap_engine: BootstrapEngine | None = None

def _get_bootstrap_engine() -> BootstrapEngine:
    global _bootstrap_engine
    if _bootstrap_engine is None:
        # pipeline_fn is a forward reference resolved at call time
        # run_full_pipeline is defined later in this module
        import sys
        main_module = sys.modules[__name__]
        _bootstrap_engine = BootstrapEngine(
            pipeline_fn=lambda event: main_module.run_full_pipeline(event)
        )
    return _bootstrap_engine

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

    # Persist sensor/device-state readings so the Devices tab reflects ingested state
    if event.device_id and event.event_type == EventType.DEVICE_STATE and event.payload:
        from services.device_command_bus import persist_device_state
        await persist_device_state(event.household_id, event.device_id, event.payload)

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


# ── Onboarding ───────────────────────────────────────────────

@app.post("/onboarding/preview", tags=["Onboarding"], response_model=PreviewResponse)
async def onboarding_preview(payload: OnboardingPayload):
    """
    Validate onboarding payload and preview generated graph nodes and edges.
    Does NOT write to DynamoDB.
    """
    svc = OnboardingService()
    # Use a dummy ID for preview
    graph_data = svc.build_graph("preview_hh_id", payload)
    
    # Format graph nodes and edges for response
    graph_nodes = []
    for n in graph_data["nodes"]:
        node_id = n.get("node_id", "")
        node_type = n.get("node_type", "")
        name = n.get("name", n.get("description", node_id))
        attrs = {k: v for k, v in n.items() if k not in ("node_id", "node_type", "name", "description")}
        graph_nodes.append({
            "node_id": node_id,
            "node_type": node_type,
            "name": name,
            "attributes": attrs
        })
        
    graph_edges = []
    for e in graph_data["edges"]:
        from_node = e.get("from", "")
        edge_type = e.get("type", "")
        to_node = e.get("to", "")
        attrs = {k: v for k, v in e.items() if k not in ("from", "type", "to")}
        graph_edges.append({
            "from_node": from_node,
            "edge_type": edge_type,
            "to_node": to_node,
            "attributes": attrs
        })

    return PreviewResponse(
        valid=True,
        household_summary={
            "name": payload.household_name,
            "city": payload.household_city,
            "members_count": len(payload.members),
            "devices_count": len(payload.devices),
            "routines_count": len(payload.routines),
        },
        graph_nodes=graph_nodes,
        graph_edges=graph_edges,
        warnings=[]
    )


@app.post("/onboarding/complete", tags=["Onboarding"], response_model=CompleteResponse)
async def onboarding_complete(payload: OnboardingPayload):
    """
    Finalize onboarding: convert payload into graph data and write to DynamoDB.
    """
    import uuid
    # Generate a random household ID
    new_hh_id = f"hh_{uuid.uuid4().hex[:8]}"
    
    svc = OnboardingService()
    try:
        summary = svc.create_household(new_hh_id, payload)
        return CompleteResponse(**summary)
    except Exception as e:
        logger.exception("Onboarding complete failed")
        raise HTTPException(status_code=500, detail=str(e))


# ── Bootstrap ─────────────────────────────────────────────────

@app.post("/bootstrap/{household_id}", tags=["Bootstrap"])
async def bootstrap_household(
    household_id: str,
    days_of_history: int = 35,
    live_event_days: int = 3,
    events_per_day: int = 5,
):
    """
    Phase 12B — Household Learning Bootstrap Engine.

    Reads the newly onboarded household from DynamoDB, generates realistic
    historical intelligence (patterns, rules, events), and feeds it through
    the real SAATHI pipeline. Zero hardcoded data — all derived from the
    household's graph nodes.

    Parameters:
      days_of_history  — observation days to simulate for pattern confidence (default 35)
      live_event_days  — recent days to replay through the live pipeline (default 3)
      events_per_day   — events per live day (default 5)

    Returns a summary of what was learned and promoted.
    """
    engine = _get_bootstrap_engine()
    try:
        summary = await engine.run(
            household_id=household_id,
            days_of_history=days_of_history,
            live_event_days=live_event_days,
            events_per_day=events_per_day,
        )
        return summary
    except RuntimeError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        logger.exception(f"Bootstrap failed for {household_id}")
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/bootstrap/{household_id}/status", tags=["Bootstrap"])
async def bootstrap_status(household_id: str):
    """
    Check the status of a running or completed bootstrap job.
    Returns 404 if no bootstrap has been run for this household.
    """
    engine = _get_bootstrap_engine()
    status = engine.get_status(household_id)
    if status is None:
        raise HTTPException(
            status_code=404,
            detail=f"No bootstrap job found for {household_id}. Run POST /bootstrap/{household_id} first.",
        )
    return status


# ── Household deletion ────────────────────────────────────────

@app.delete("/household/{household_id}", tags=["Household"])
async def delete_household(household_id: str):
    """
    Permanently delete all data for a household across every DynamoDB table.

    Deletes from:
      - HouseholdGraph    (PK = HOUSEHOLD#{household_id})
      - HouseholdPatterns (household_id = household_id)
      - HouseholdRules    (household_id = household_id)
      - ActionLog         (household_id-index GSI)
      - RTEAuditLog       (household_id-index GSI)
      - HouseholdMetrics  (PK = household_id)

    After calling this endpoint, the user must go through onboarding again.
    This action is irreversible.
    """
    from boto3.dynamodb.conditions import Key as DKey
    from graph_repository import _decimal_to_native
    import asyncio

    deleted: dict[str, int] = {}

    # ── 1. HouseholdGraph ─────────────────────────────────────────────────
    # Single partition key HOUSEHOLD#{household_id} — query then batch delete
    try:
        graph_table = get_table("household_graph")
        pk = f"HOUSEHOLD#{household_id}"
        items_to_delete = []
        kwargs: dict = {"KeyConditionExpression": DKey("PK").eq(pk), "ProjectionExpression": "PK, SK"}
        while True:
            resp = graph_table.query(**kwargs)
            items_to_delete.extend(resp.get("Items", []))
            if not resp.get("LastEvaluatedKey"):
                break
            kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]
        with graph_table.batch_writer() as bw:
            for item in items_to_delete:
                bw.delete_item(Key={"PK": item["PK"], "SK": item["SK"]})
        deleted["household_graph"] = len(items_to_delete)
        # Evict from in-memory cache
        graph_repo.invalidate_cache(household_id)
    except Exception as exc:
        logger.warning(f"Delete: HouseholdGraph error for {household_id}: {exc}")
        deleted["household_graph"] = -1

    # ── 2. HouseholdPatterns ──────────────────────────────────────────────
    try:
        pat_table = get_table("household_patterns")
        items: list[dict] = []
        kwargs2: dict = {"KeyConditionExpression": DKey("household_id").eq(household_id), "ProjectionExpression": "household_id, pattern_id"}
        while True:
            resp = pat_table.query(**kwargs2)
            items.extend(resp.get("Items", []))
            if not resp.get("LastEvaluatedKey"):
                break
            kwargs2["ExclusiveStartKey"] = resp["LastEvaluatedKey"]
        with pat_table.batch_writer() as bw:
            for item in items:
                bw.delete_item(Key={"household_id": item["household_id"], "pattern_id": item["pattern_id"]})
        deleted["household_patterns"] = len(items)
    except Exception as exc:
        logger.warning(f"Delete: HouseholdPatterns error for {household_id}: {exc}")
        deleted["household_patterns"] = -1

    # ── 3. HouseholdRules ─────────────────────────────────────────────────
    try:
        rules_table = get_table("household_rules")
        items3: list[dict] = []
        kwargs3: dict = {"KeyConditionExpression": DKey("household_id").eq(household_id), "ProjectionExpression": "household_id, rule_id"}
        while True:
            resp = rules_table.query(**kwargs3)
            items3.extend(resp.get("Items", []))
            if not resp.get("LastEvaluatedKey"):
                break
            kwargs3["ExclusiveStartKey"] = resp["LastEvaluatedKey"]
        with rules_table.batch_writer() as bw:
            for item in items3:
                bw.delete_item(Key={"household_id": item["household_id"], "rule_id": item["rule_id"]})
        deleted["household_rules"] = len(items3)
    except Exception as exc:
        logger.warning(f"Delete: HouseholdRules error for {household_id}: {exc}")
        deleted["household_rules"] = -1

    # ── 4. ActionLog (household_id-index GSI) ─────────────────────────────
    try:
        action_table = get_table("action_log")
        items4: list[dict] = []
        kwargs4: dict = {
            "IndexName": "household_id-index",
            "KeyConditionExpression": DKey("household_id").eq(household_id),
            "ProjectionExpression": "action_id, created_at",
        }
        while True:
            resp = action_table.query(**kwargs4)
            items4.extend(resp.get("Items", []))
            if not resp.get("LastEvaluatedKey"):
                break
            kwargs4["ExclusiveStartKey"] = resp["LastEvaluatedKey"]
        with action_table.batch_writer() as bw:
            for item in items4:
                key: dict = {"action_id": item["action_id"]}
                if "created_at" in item:
                    key["created_at"] = item["created_at"]
                bw.delete_item(Key=key)
        deleted["action_log"] = len(items4)
    except Exception as exc:
        logger.warning(f"Delete: ActionLog error for {household_id}: {exc}")
        deleted["action_log"] = -1

    # ── 5. RTEAuditLog (household_id-index GSI) ───────────────────────────
    try:
        rte_table = get_table("rte_audit_log")
        items5: list[dict] = []
        kwargs5: dict = {
            "IndexName": "household_id-index",
            "KeyConditionExpression": DKey("household_id").eq(household_id),
            "ProjectionExpression": "event_id, #ts",
            "ExpressionAttributeNames": {"#ts": "timestamp"},
        }
        while True:
            resp = rte_table.query(**kwargs5)
            items5.extend(resp.get("Items", []))
            if not resp.get("LastEvaluatedKey"):
                break
            kwargs5["ExclusiveStartKey"] = resp["LastEvaluatedKey"]
        with rte_table.batch_writer() as bw:
            for item in items5:
                bw.delete_item(Key={"event_id": item["event_id"], "timestamp": item["timestamp"]})
        deleted["rte_audit_log"] = len(items5)
    except Exception as exc:
        logger.warning(f"Delete: RTEAuditLog error for {household_id}: {exc}")
        deleted["rte_audit_log"] = -1

    # ── 6. HouseholdMetrics ───────────────────────────────────────────────
    try:
        metrics_table = get_table("household_metrics")
        items6: list[dict] = []
        kwargs6: dict = {"KeyConditionExpression": DKey("household_id").eq(household_id), "ProjectionExpression": "household_id, #dt", "ExpressionAttributeNames": {"#dt": "date"}}
        while True:
            resp = metrics_table.query(**kwargs6)
            items6.extend(resp.get("Items", []))
            if not resp.get("LastEvaluatedKey"):
                break
            kwargs6["ExclusiveStartKey"] = resp["LastEvaluatedKey"]
        with metrics_table.batch_writer() as bw:
            for item in items6:
                bw.delete_item(Key={"household_id": item["household_id"], "date": item["date"]})
        deleted["household_metrics"] = len(items6)
    except Exception as exc:
        logger.warning(f"Delete: HouseholdMetrics error for {household_id}: {exc}")
        deleted["household_metrics"] = -1

    total_deleted = sum(v for v in deleted.values() if v >= 0)
    logger.info(f"Household deleted: {household_id} — {total_deleted} items removed across {len(deleted)} tables")

    return {
        "household_id": household_id,
        "status": "deleted",
        "items_deleted": deleted,
        "total": total_deleted,
    }


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
async def simulate_named_event(event_name: str, household_id: str | None = None):
    """Fire a named demo event through the full pipeline."""
    hid = household_id or HH_ID
    sim = EventSimulator(hid, run_full_pipeline)

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
async def get_metrics(household_id: str | None = None):
    """Return full DashboardMetrics snapshot."""
    hid = household_id or HH_ID
    from services.metrics_service import MetricsService
    m = MetricsService(hid).get_dashboard_metrics()
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
async def get_rules(household_id: str | None = None):
    """List all active rules in the registry."""
    hid = household_id or HH_ID
    # Since rule_engine is a singleton, it needs to load rules for this HH
    rule_engine._registry.load(hid)
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
async def reload_rules(household_id: str | None = None):
    """Force-refresh the rule registry from DynamoDB."""
    hid = household_id or HH_ID
    # Clear cache timestamp so load() fetches fresh data
    rule_engine._registry._last_load = 0.0
    rule_engine._registry.load(hid)
    return {"status": "ok", "rules_loaded": len(rule_engine._registry._raw_rules)}


# ── Patterns ─────────────────────────────────────────────────

@app.get("/patterns", tags=["Patterns"])
async def get_patterns(household_id: str | None = None):
    """Return all patterns with full fields for the intelligence layer."""
    hid = household_id or HH_ID
    patterns = graph_repo.get_patterns(hid)
    return {
        "count": len(patterns),
        "patterns": [
            {
                "pattern_id":       p.get("pattern_id"),
                "description":      p.get("description"),
                "confidence":       float(p.get("confidence", 0)),
                "confidence_band":  p.get("confidence_band"),
                "observation_days": int(p.get("observation_days", 0)),
                "member_id":        p.get("member_id"),
                "device_type":      p.get("device_type"),
                "time_window":      p.get("time_window"),
                "day_pattern":      p.get("day_pattern"),
                "total_observations": int(p.get("total_observations", 0)),
                "total_matches":    int(p.get("total_matches", 0)),
                "consecutive_misses": int(p.get("consecutive_misses", 0)),
                "first_observed":   p.get("first_observed"),
                "last_observed":    p.get("last_observed"),
                "promoted_rule_id": p.get("promoted_rule_id"),
                "promoted_at":      p.get("promoted_at"),
                "demoted_at":       p.get("demoted_at"),
            }
            for p in patterns
        ],
    }


@app.post("/patterns/promote", tags=["Patterns"])
async def run_promotion(household_id: str | None = None):
    """Scan all patterns and promote eligible ones."""
    hid = household_id or HH_ID
    newly_promoted = pattern_engine.promote_if_eligible(hid)
    return {"status": "ok", "newly_promoted": newly_promoted}


# ── Action History ────────────────────────────────────────────

@app.get("/actions/history", tags=["Actions"])
async def get_action_history(limit: int = 50, household_id: str | None = None):
    """
    Return recent actions from the ActionLog table, newest first.
    Used by the frontend RecentEvents component to replace static mocks.

    Notes:
    - NotificationService writes `created_at` as the range key.
    - DeviceCommandBus writes `timestamp` (no range key set, so created_at may be missing).
    - We query via household_id-index (GSI), sort by created_at descending.
    - Items that lack created_at fall through via a Scan fallback.
    """
    hid = household_id or HH_ID
    from boto3.dynamodb.conditions import Key as DKey
    from graph_repository import _decimal_to_native
    table = get_table("action_log")
    try:
        resp = table.query(
            IndexName="household_id-index",
            KeyConditionExpression=DKey("household_id").eq(hid),
            ScanIndexForward=False,   # newest first
            Limit=limit,
        )
        items = resp.get("Items", [])
        actions = [_decimal_to_native(item) for item in items]
        # Normalise: some rows use `timestamp`, some use `created_at`
        for a in actions:
            if "created_at" not in a and "timestamp" in a:
                a["created_at"] = a["timestamp"]
        # Sort by created_at descending (strings in ISO format sort correctly)
        actions.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return {"household_id": hid, "count": len(actions), "actions": actions}
    except Exception as e:
        logger.warning(f"ActionLog query failed: {e}")
        return {"household_id": HH_ID, "count": 0, "actions": [], "error": str(e)}


# ── RTE Audit ─────────────────────────────────────────────────

@app.get("/rte/audit", tags=["RTE"])
async def get_rte_audit(limit: int = 30):
    """
    Return recent RTE routing decisions from RTEAuditLog, newest first.
    Used by ReasoningFeed to show actual decision timeline.
    Queries using the household_id-index GSI.
    """
    from boto3.dynamodb.conditions import Key as DKey
    table = get_table("rte_audit_log")
    try:
        resp = table.query(
            IndexName="household_id-index",
            KeyConditionExpression=DKey("household_id").eq(HH_ID),
            ScanIndexForward=False,
            Limit=limit,
        )
        items = resp.get("Items", [])
        from graph_repository import _decimal_to_native
        decisions = [_decimal_to_native(item) for item in items]
        return {"household_id": HH_ID, "count": len(decisions), "decisions": decisions}
    except Exception as e:
        logger.warning(f"RTEAuditLog query failed: {e}")
        return {"household_id": HH_ID, "count": 0, "decisions": [], "error": str(e)}


# ── RTE Decision (single event, for backward compat with reasoning.service.ts) ──

@app.get("/rte/decision/{event_id}", tags=["RTE"])
async def get_rte_decision(event_id: str):
    """Look up a single RTE routing decision by event_id."""
    table = get_table("rte_audit_log")
    try:
        from boto3.dynamodb.conditions import Key as DKey
        resp = table.query(
            KeyConditionExpression=DKey("event_id").eq(event_id),
            Limit=1,
        )
        items = resp.get("Items", [])
        if not items:
            raise HTTPException(status_code=404, detail=f"Event {event_id} not found in audit log")
        from graph_repository import _decimal_to_native
        return _decimal_to_native(items[0])
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Full Graph ────────────────────────────────────────────────

@app.get("/graph/{household_id}/full", tags=["Graph"])
async def get_full_graph(household_id: str):
    """
    Return all graph nodes and edges for the household.
    Used by HouseholdGraph component to replace the hardcoded SVG mock.
    """
    try:
        g = graph_repo.load_graph(household_id)
        nodes = []
        _device_state_keys = (
            "state", "mode", "temperature_set_c", "temperature_c",
            "volume_percent", "door_open_seconds", "brightness_pct",
        )
        for node_id, attrs in g.nodes(data=True):
            if attrs.get("node_type"):   # only real typed nodes
                node_entry = {
                    "id": node_id,
                    "node_type": attrs.get("node_type"),
                    "name": attrs.get("name", node_id),
                    "role": attrs.get("role"),
                    "age": attrs.get("age"),
                    "room": attrs.get("room"),
                    "condition": attrs.get("condition"),
                    "severity": attrs.get("severity"),
                    "member_id": attrs.get("member_id"),
                    "description": attrs.get("description"),
                    "time_window": attrs.get("time_window"),
                    "device_type": attrs.get("device_type"),
                    "critical": attrs.get("critical"),
                    "schedule": attrs.get("schedule"),
                }
                if attrs.get("node_type") == "device":
                    for key in _device_state_keys:
                        if key in attrs and attrs[key] is not None:
                            node_entry[key] = attrs[key]
                nodes.append(node_entry)
        edges = []
        for from_node, to_node, edata in g.edges(data=True):
            edges.append({
                "from": from_node,
                "to": to_node,
                "type": edata.get("edge_type"),
                "reason": edata.get("reason"),
                "impact": edata.get("impact"),
                "severity": edata.get("severity"),
                "schedule": edata.get("schedule"),
            })
        return {
            "household_id": household_id,
            "family_name": g.graph.get("family_name", "Unknown"),
            "location": g.graph.get("location", "Unknown"),
            "node_count": len(nodes),
            "edge_count": len(edges),
            "nodes": nodes,
            "edges": edges,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────────────────────
# Entrypoint
# ─────────────────────────────────────────────────────────────
# AWS Lambda entrypoint
handler = Mangum(app, lifespan="on")

if __name__ == "__main__":
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
