"""
pattern_engine.py — Phase 9.7
==============================
Manages the lifecycle of behavioral patterns detected in the household.

Confidence bands (from PatternRecord.compute_band):
  OBSERVING   confidence >= 0.40
  LEARNING    confidence >= 0.60
  PROMOTED    confidence >= 0.90 AND observation_days >= 30
  RETIRED     confidence < 0.40 (or manually demoted)

Operations:
  promote_if_eligible()  — promote LEARNING → PROMOTED and write to DynamoDB
  demote_if_necessary()  — move PROMOTED → LEARNING on consecutive misses
  record_miss()          — increment consecutive_misses, demote if threshold exceeded
  record_override()      — increment consecutive_overrides, log for review
"""

import logging
import time
from datetime import datetime, timezone
from decimal import Decimal

from config import settings
from db.dynamo_client import get_table
from graph_repository import GraphRepository
from schemas.enums import ConfidenceBand
from schemas.intelligence import PatternRecord

logger = logging.getLogger(__name__)

# How many consecutive misses trigger demotion
_DEMOTE_MISS_THRESHOLD = 3
# How many consecutive overrides mark a pattern for review
_OVERRIDE_REVIEW_THRESHOLD = 5


class PatternEngine:
    """
    Loads patterns from DynamoDB, manages confidence band transitions,
    and persists updates back to HouseholdPatterns.
    """

    def __init__(self, graph_repo: GraphRepository | None = None):
        self._graph = graph_repo or GraphRepository()

    # ── Load ─────────────────────────────────────────────────

    def load(self, household_id: str) -> list[PatternRecord]:
        """Load all patterns for a household from DynamoDB."""
        return [
            PatternRecord(**p)
            for p in self._graph.get_patterns(household_id)
        ]

    def load_promoted(self, household_id: str) -> list[PatternRecord]:
        return [
            PatternRecord(**p)
            for p in self._graph.get_patterns(household_id, band="PROMOTED")
        ]

    # ── Promote ──────────────────────────────────────────────

    def promote_if_eligible(self, household_id: str) -> list[str]:
        """
        Scan all patterns and promote any that meet the PROMOTED threshold.
        Returns list of newly promoted pattern_ids.
        """
        patterns = self.load(household_id)
        promoted_ids = []

        for p in patterns:
            if p.confidence_band == ConfidenceBand.PROMOTED:
                continue  # already promoted

            new_band = PatternRecord.compute_band(p.confidence, p.observation_days)
            if new_band == ConfidenceBand.PROMOTED:
                p.confidence_band = ConfidenceBand.PROMOTED
                p.promoted_at = datetime.now(tz=timezone.utc)
                self._persist(household_id, p)
                promoted_ids.append(p.pattern_id)
                logger.info(
                    f"PatternEngine: promoted {p.pattern_id} "
                    f"(conf={p.confidence:.2f}, days={p.observation_days})"
                )

        return promoted_ids

    # ── Demote ───────────────────────────────────────────────

    def demote_if_necessary(self, household_id: str, pattern_id: str) -> bool:
        """
        Demote a PROMOTED pattern back to LEARNING.
        Returns True if demotion happened.
        """
        patterns = self.load(household_id)
        target = next((p for p in patterns if p.pattern_id == pattern_id), None)
        if not target or target.confidence_band != ConfidenceBand.PROMOTED:
            return False

        target.confidence_band = ConfidenceBand.LEARNING
        target.demoted_at = datetime.now(tz=timezone.utc)
        target.consecutive_misses = 0
        self._persist(household_id, target)
        logger.info(f"PatternEngine: demoted {pattern_id} → LEARNING")
        return True

    # ── Miss / Override recording ─────────────────────────────

    def record_miss(self, household_id: str, pattern_id: str) -> PatternRecord | None:
        """
        Increment consecutive_misses. If threshold exceeded and pattern is PROMOTED,
        auto-demote.
        """
        patterns = self.load(household_id)
        target = next((p for p in patterns if p.pattern_id == pattern_id), None)
        if not target:
            return None

        target.consecutive_misses += 1
        target.last_miss = datetime.now(tz=timezone.utc)
        logger.debug(f"PatternEngine: miss #{target.consecutive_misses} for {pattern_id}")

        if (
            target.consecutive_misses >= _DEMOTE_MISS_THRESHOLD
            and target.confidence_band == ConfidenceBand.PROMOTED
        ):
            target.confidence_band = ConfidenceBand.LEARNING
            target.demoted_at = datetime.now(tz=timezone.utc)
            logger.info(
                f"PatternEngine: auto-demoted {pattern_id} after "
                f"{target.consecutive_misses} consecutive misses"
            )

        self._persist(household_id, target)
        return target

    def record_override(self, household_id: str, pattern_id: str) -> PatternRecord | None:
        """
        Increment consecutive_overrides. Flag for human review if threshold hit.
        """
        patterns = self.load(household_id)
        target = next((p for p in patterns if p.pattern_id == pattern_id), None)
        if not target:
            return None

        target.consecutive_overrides += 1
        logger.debug(f"PatternEngine: override #{target.consecutive_overrides} for {pattern_id}")

        if target.consecutive_overrides >= _OVERRIDE_REVIEW_THRESHOLD:
            logger.warning(
                f"PatternEngine: {pattern_id} flagged for review — "
                f"{target.consecutive_overrides} consecutive overrides"
            )

        self._persist(household_id, target)
        return target

    # ── Ingest Bedrock suggestions ───────────────────────────

    def ingest_suggestions(
        self,
        household_id: str,
        suggestions: list[dict],
    ) -> list[str]:
        """
        Add or update patterns suggested by Bedrock response.
        New patterns start at confidence=0.0, band=OBSERVING.
        Returns list of pattern_ids upserted.
        """
        upserted = []
        for s in suggestions:
            pattern_id = s.get("pattern_id")
            if not pattern_id:
                continue

            record = PatternRecord(
                household_id=household_id,
                pattern_id=pattern_id,
                description=s.get("description"),
                confidence=s.get("confidence", 0.0),
                confidence_band=ConfidenceBand.OBSERVING,
                observation_days=0,
                event_type=s.get("event_type"),
                device_type=s.get("device_type"),
                member_id=s.get("member_id"),
            )
            self._persist(household_id, record)
            upserted.append(pattern_id)
            logger.info(f"PatternEngine: ingested suggestion {pattern_id}")

        return upserted

    # ── Persist ──────────────────────────────────────────────

    def _persist(self, household_id: str, pattern: PatternRecord) -> None:
        """Write PatternRecord back to HouseholdPatterns DynamoDB table."""
        try:
            table = get_table("household_patterns")
            item = pattern.model_dump(mode="json")
            item["household_id"] = household_id

            # Convert float → Decimal for DynamoDB
            for k, v in list(item.items()):
                if isinstance(v, float):
                    item[k] = Decimal(str(v))
                if v is None:
                    del item[k]

            table.put_item(Item=item)
        except Exception as e:
            logger.warning(f"PatternEngine: persist failed for {pattern.pattern_id}: {e}")
