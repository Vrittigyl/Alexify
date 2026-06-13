"""
tests/test_knowledge_graph.py
Tests all 4 KnowledgeGraph queries against the live Sharma family data in DynamoDB.
Run: pytest tests/test_knowledge_graph.py -v
"""

import pytest
from graph_repository import GraphRepository
from knowledge_graph import KnowledgeGraph

HH_ID = "hh_xk92p_sharma"


@pytest.fixture(scope="module")
def kg():
    """Single repo + graph instance shared across all tests (avoids re-fetching DynamoDB)."""
    repo = GraphRepository()
    return KnowledgeGraph(repo)


# ─────────────────────────────────────────────────────────────
# Graph load sanity checks
# ─────────────────────────────────────────────────────────────

def test_graph_loads(kg):
    g = kg._graph(HH_ID)
    assert g is not None
    assert g.number_of_nodes() > 0
    assert g.number_of_edges() > 0


def test_graph_version_readable():
    repo = GraphRepository()
    version = repo.get_graph_version(HH_ID)
    assert isinstance(version, int)
    assert version >= 1


def test_dadaji_node_exists(kg):
    g = kg._graph(HH_ID)
    assert "mbr_dadaji_001" in g
    attrs = g.nodes["mbr_dadaji_001"]
    assert attrs.get("name") == "Dadaji"
    assert attrs.get("node_type") == "member"


def test_all_6_members_loaded(kg):
    g = kg._graph(HH_ID)
    members = [n for n, d in g.nodes(data=True) if d.get("node_type") == "member"]
    assert len(members) == 6


def test_all_6_devices_loaded(kg):
    g = kg._graph(HH_ID)
    devices = [n for n, d in g.nodes(data=True) if d.get("node_type") == "device"]
    assert len(devices) == 6


def test_dadaji_has_condition_edge(kg):
    """Dadaji --HAS_CONDITION--> cond_hypertension"""
    g = kg._graph(HH_ID)
    edge_data = g.get_edge_data("mbr_dadaji_001", "cond_hypertension")
    assert edge_data is not None
    assert edge_data.get("edge_type") == "HAS_CONDITION"


def test_dadaji_takes_medication_edge(kg):
    """Dadaji --TAKES--> med_amlodipine"""
    g = kg._graph(HH_ID)
    edge_data = g.get_edge_data("mbr_dadaji_001", "med_amlodipine")
    assert edge_data is not None
    assert edge_data.get("edge_type") == "TAKES"


# ─────────────────────────────────────────────────────────────
# Q1: get_affected_members_with_constraints()
# ─────────────────────────────────────────────────────────────

def test_q1_rohan_boards_affects_members(kg):
    """Rohan's board exam life event should affect Rohan, Sunita (mama), Rajesh (papa)."""
    results = kg.get_affected_members_with_constraints(
        household_id=HH_ID,
        life_event_ids=["le_rohan_boards"],
    )
    assert len(results) >= 3
    affected_ids = {r["member_id"] for r in results}
    assert "mbr_rohan_005" in affected_ids
    assert "mbr_mama_004" in affected_ids
    assert "mbr_papa_003" in affected_ids


def test_q1_constraints_present(kg):
    """Constraints from the life event node should be in the results."""
    results = kg.get_affected_members_with_constraints(
        household_id=HH_ID,
        life_event_ids=["le_rohan_boards"],
    )
    for r in results:
        assert "constraints" in r
        assert isinstance(r["constraints"], list)


def test_q1_empty_for_unknown_event(kg):
    results = kg.get_affected_members_with_constraints(
        household_id=HH_ID,
        life_event_ids=["le_nonexistent"],
    )
    assert results == []


# ─────────────────────────────────────────────────────────────
# Q2: get_routine_conflicts_in_window()
# ─────────────────────────────────────────────────────────────

def test_q2_evening_conflicts(kg):
    """During study hours (18:00-21:00), Rohan's study routine conflicts with TV."""
    conflicts = kg.get_routine_conflicts_in_window(
        household_id=HH_ID,
        time_window="18:00-21:00",
    )
    assert len(conflicts) >= 1
    conflict_ids = {c["routine_id"] for c in conflicts}
    assert "rtn_rohan_study" in conflict_ids


def test_q2_conflict_target_is_tv(kg):
    conflicts = kg.get_routine_conflicts_in_window(
        household_id=HH_ID,
        time_window="18:00-21:00",
    )
    study_conflicts = [c for c in conflicts if c["routine_id"] == "rtn_rohan_study"]
    assert len(study_conflicts) >= 1
    assert study_conflicts[0]["conflicts_with"] == "dev_tv_001"


def test_q2_member_filter(kg):
    """When filtering to only Rohan's routines, only Rohan's conflicts appear."""
    conflicts = kg.get_routine_conflicts_in_window(
        household_id=HH_ID,
        time_window="18:00-21:00",
        member_ids=["mbr_rohan_005"],
    )
    for c in conflicts:
        assert c["member_id"] == "mbr_rohan_005"


def test_q2_no_conflict_morning(kg):
    """Early morning window should have no routine conflicts."""
    conflicts = kg.get_routine_conflicts_in_window(
        household_id=HH_ID,
        time_window="05:00-06:00",
    )
    assert conflicts == []


# ─────────────────────────────────────────────────────────────
# Q3: get_medications_due()
# ─────────────────────────────────────────────────────────────

def test_q3_dadaji_morning_meds(kg):
    """Dadaji has Amlodipine (08:00) and Metformin (08:30) due in morning window."""
    due = kg.get_medications_due(
        household_id=HH_ID,
        member_ids=["mbr_dadaji_001"],
        window_start="07:50",
        window_end="08:35",
    )
    assert len(due) >= 2
    names = {m["medication_name"] for m in due}
    assert any("Amlodipine" in n for n in names)
    assert any("Metformin" in n for n in names)


def test_q3_critical_medication_flagged(kg):
    due = kg.get_medications_due(
        household_id=HH_ID,
        member_ids=["mbr_dadaji_001"],
        window_start="07:50",
        window_end="08:35",
    )
    for med in due:
        assert med["critical"] is True  # Both morning meds are critical


def test_q3_evening_med(kg):
    """Dadaji's Telmisartan is due at 20:30."""
    due = kg.get_medications_due(
        household_id=HH_ID,
        member_ids=["mbr_dadaji_001"],
        window_start="20:00",
        window_end="21:00",
    )
    assert len(due) >= 1
    assert any("Telmisartan" in m["medication_name"] for m in due)


def test_q3_no_meds_outside_window(kg):
    due = kg.get_medications_due(
        household_id=HH_ID,
        member_ids=["mbr_dadaji_001"],
        window_start="14:00",
        window_end="15:00",
    )
    # No meds scheduled at this time for Dadaji
    assert len(due) == 0


# ─────────────────────────────────────────────────────────────
# Q4: get_device_impact()
# ─────────────────────────────────────────────────────────────

def test_q4_water_motor_primary_user(kg):
    result = kg.get_device_impact(HH_ID, "dev_water_motor_001")
    assert result["found"] is True
    assert result["primary_user"] is not None
    assert result["primary_user"]["member_id"] == "mbr_papa_003"


def test_q4_water_motor_room(kg):
    result = kg.get_device_impact(HH_ID, "dev_water_motor_001")
    assert result["room"] == "terrace"


def test_q4_ac_has_conflict(kg):
    """AC has a CONFLICTS_WITH edge from cond_arthritis (Dadaji's condition)."""
    result = kg.get_device_impact(HH_ID, "dev_ac_001")
    assert result["found"] is True
    conflict_sources = {c["from_node"] for c in result["conflicts"]}
    assert "cond_arthritis" in conflict_sources


def test_q4_tv_has_routine_conflict(kg):
    """TV is in CONFLICTS_WITH edge from rtn_rohan_study."""
    result = kg.get_device_impact(HH_ID, "dev_tv_001")
    assert result["found"] is True
    routine_conflicts = {r["routine_id"] for r in result["routine_conflicts"]}
    assert "rtn_rohan_study" in routine_conflicts


def test_q4_unknown_device(kg):
    result = kg.get_device_impact(HH_ID, "dev_does_not_exist")
    assert result["found"] is False


# ─────────────────────────────────────────────────────────────
# Graph integrity regression tests
# ─────────────────────────────────────────────────────────────

def test_primary_user_edge_bidirectional(kg):
    """
    Q4 validates dev_water_motor_001 → papa as PRIMARY_USER_OF.
    This verifies the edge is stored correctly in the graph (papa → motor).
    Catches construction bugs where in_edges and out_edges disagree.
    """
    g = kg._graph(HH_ID)
    edge = g.get_edge_data("mbr_papa_003", "dev_water_motor_001")
    assert edge is not None
    assert edge["edge_type"] == "PRIMARY_USER_OF"


def test_no_orphan_members(kg):
    """
    Every member must have at least one edge.
    Dadiji became orphaned once (fixed by adding rtn_dadiji_evening_bhajan).
    This test prevents that regression from going undetected.
    """
    g = kg._graph(HH_ID)
    members = [n for n, d in g.nodes(data=True) if d.get("node_type") == "member"]
    for member in members:
        assert g.degree(member) > 0, f"Orphan member detected: {member}"


def test_promoted_pattern_rule_link_exists():
    """
    Every PROMOTED pattern must have a promoted_rule_id set.
    This protects the pattern → rule pipeline from silent failures.
    """
    repo = GraphRepository()
    patterns = repo.get_patterns(HH_ID)
    promoted = [p for p in patterns if p.get("confidence_band") == "PROMOTED"]
    assert len(promoted) >= 1, "No PROMOTED patterns found — learning pipeline broken"
    for p in promoted:
        assert p.get("promoted_rule_id"), (
            f"Pattern {p['pattern_id']} is PROMOTED but has no promoted_rule_id"
        )

