# SAATHI — Scaling Limits & Known Architectural Debt

This document tracks the known limits of the current architecture and the work
required to scale beyond a single-household demo to a multi-tenant production
platform. It exists so these limits are **known and tracked**, not hidden.

Status legend: 🔴 blocker for multi-tenant production · 🟠 correctness risk at scale · 🟡 efficiency / hygiene

---

## Summary

The system currently assumes, in several places, that **one backend process serves
effectively one household** (the seeded `hh_xk92p_sharma` demo). Per-household state
lives in module-level singletons inside the pod. This is fine for a demo and for the
happy-path pipeline, but it must be addressed before running many households across
multiple pods.

The event pipeline itself (ingest → RTE → Rule Engine / Bedrock → Action Planner →
dispatch) is correct and already async. Distributed concerns that *have* been solved:
idempotency, rate limiting, presence, and WebSocket fanout all run through Redis.

---

## Known Limits

### 🔴 1. Per-household metrics are a global singleton
**Where:** `backend/main.py` → `metrics = MetricsService(HH_ID)`; `GET /metrics`.

`MetricsService` is instantiated once at module load, keyed to the single default
`HH_ID`. Counters are process-local and not keyed per household. `GET /metrics`
therefore reports the pod's aggregate counters, not the requested household's, and
counts are lost on restart and not shared across pods.

**Impact:** Metrics are incorrect the moment more than one household (or more than one
pod) is active.

**Fix direction:** Key metrics by `household_id` and back them with a shared store
(DynamoDB counters or Redis). Make `/metrics` read the requested household's record.
This is a real change — do it deliberately with tests, not as a rushed patch.

---

### 🟠 2. RuleRegistry cache is keyed/loaded for one household
**Where:** `backend/engines/rule_engine.py`; loaded at startup via `rule_engine._registry.load(HH_ID)`.

The rule registry is loaded once for the default household and shared across all
requests on the pod. With multiple households, rules for one household could be served
to another, or reloads could race.

**Fix direction:** Make the registry a per-household cache (keyed map) with explicit
load/invalidate per `household_id`, or load rules per request from a shared cache.

---

### 🟡 3. GraphRepository in-memory cache is unbounded and per-pod
**Where:** `backend/graph_repository.py` → `_cache`.

The graph cache grows without eviction and is local to each pod, so different pods can
hold divergent (stale) views of the same household graph after writes.

**Fix direction:** Add an LRU bound + TTL, and/or invalidate via a Redis pub/sub signal
on graph writes so all pods drop stale entries.

---

### 🟡 4. EventBatcher is in-memory per-pod
**Where:** `backend/services/event_batcher.py`; `batcher = EventBatcher()` in `main.py`.

Unlike idempotency / rate-limit / presence (which are distributed via Redis), event
batching is held in process memory. If an event for a household lands on pod A and the
next on pod B, they will not batch together, and a pod restart drops the in-flight batch.

**Fix direction:** Move batch state into Redis keyed by `household_id`, mirroring the
existing distributed-state pattern.

---

### 🟡 5. No durable ingestion buffer (SQS disabled)
**Where:** `POST /events/ingest` runs the full pipeline synchronously; `sqs_enabled=False`.

A burst of events, or a slow Bedrock call, applies backpressure directly to the HTTP
request. There is no durable queue absorbing spikes or retrying failed processing.

**Fix direction:** Put SQS in front of ingestion. The endpoint enqueues and returns
quickly; a worker drains the queue through the pipeline. Gives durability, retries,
and spike absorption.

---

## What is already solid

- **Async pipeline.** `run_full_pipeline` is fully async; the synchronous Bedrock call
  is offloaded via `async_execute` so it no longer blocks the event loop.
- **Distributed idempotency, rate limiting, presence, and WebSocket fanout** all run
  through Redis with graceful local-only fallback when Redis is unavailable.
- **DynamoDB access** goes through a single retry-configured client with thread-pool
  offloading (`async_execute`).
- **Graceful degradation:** `/health` returns 503 when DynamoDB is down (so ECS/ALB
  stops routing), and 200 (degraded) when only Redis is down.

---

## Recommended order of work (toward multi-tenant production)

1. **Per-household metrics** (🔴 #1) — correctness blocker for any multi-household view.
2. **RuleRegistry per-household keying** (🟠 #2) — correctness at scale.
3. **GraphRepository cache bound + cross-pod invalidation** (🟡 #3).
4. **Distributed EventBatcher** (🟡 #4).
5. **SQS ingestion buffer** (🟡 #5) — durability and spike absorption.

Items 1–2 are correctness; 3–5 are durability/efficiency. None of these block the
current single-household demo, which is why they are deferred — but they are the
gating work for "100,000 households."
