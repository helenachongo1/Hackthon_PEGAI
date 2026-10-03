"""
scheduler.py

Deterministic Schedule Conflict Resolver
========================================

Implements the V5 scheduling contract.

Hard constraints:
    H1. Only valid events are scheduled.
    H2. No two scheduled events conflict, including buffer.
    H3. Every mandatory event is scheduled.
    H4. Every scheduled event has all prerequisites scheduled
        and completed before it starts.
    H5. Event times are never changed.

Soft preferences:
    S1. Keep higher-priority events over lower-priority events.
    S2. Keep more events after priority.

Rule order:
    R1. Validate input
    R2. Normalize times to UTC
    R3. Validate dependency graph
    R4. Build/check required set
    R5. Determine optional-event eligibility
    R6. Rank eligible optional events
    R7. Admit optional events using dependency bundles
    R8. Re-check hard constraints
    R9. Generate grounded explanations

No event is moved.
No event duration is changed.
No optimality claim is made.
"""

from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from typing import Any


# ============================================================
# CONSTANTS
# ============================================================

UTC = timezone.utc


RULE_ORDER = [
    "R1: Validate each event and configuration",
    "R2: Normalize all times to UTC",
    "R3: Check dependency graph and detect cycles",
    "R4: Build required set and check required-event feasibility",
    "R5: Determine optional-event eligibility",
    "R6: Rank eligible optional events",
    "R7: Admit eligible optional events using dependency bundles",
    "R8: Re-check H1-H5",
    "R9: Generate explanations from established facts",
]


# V5 reason codes.
INVALID_EVENT = "INVALID_EVENT"
DEPENDENCY_CYCLE = "DEPENDENCY_CYCLE"
MISSING_PREREQ_ID = "MISSING_PREREQ_ID"
PREREQ_ORDER_VIOLATION = "PREREQ_ORDER_VIOLATION"
PREREQ_DROPPED = "PREREQ_DROPPED"
CONFLICT_LOWER_RANK = "CONFLICT_LOWER_RANK"


# ============================================================
# BASIC HELPERS
# ============================================================

def _is_valid_priority(value: Any) -> bool:
    """
    V5 priority:
        integer 1-5
        higher number = more important
    """
    return (
        isinstance(value, int)
        and not isinstance(value, bool)
        and 1 <= value <= 5
    )


def _parse_datetime(value: Any) -> datetime:
    """
    Parse an ISO-8601 datetime.

    Naive datetimes are rejected because V5 requires timezone
    information when the timestamp itself has no UTC offset.
    """

    if not isinstance(value, str) or not value.strip():
        raise ValueError("INVALID_TIME")

    text = value.strip()

    # Support ISO-8601 Z notation.
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"

    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        raise ValueError("INVALID_TIME")

    if dt.tzinfo is None:
        raise ValueError("NAIVE_DATETIME")

    return dt


def _utc(dt: datetime) -> datetime:
    """Convert an aware datetime to UTC."""
    return dt.astimezone(UTC)


def _iso_utc(dt: datetime) -> str:
    """Return UTC ISO-8601 string."""
    return (
        dt.astimezone(UTC)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _valid_timezone(name: Any) -> bool:
    """
    Validate an IANA timezone name.
    """
    if not isinstance(name, str) or not name.strip():
        return False

    try:
        ZoneInfo(name)
        return True
    except ZoneInfoNotFoundError:
        return False


def _duration_minutes(
    start: datetime,
    end: datetime,
) -> float:
    return (
        end - start
    ).total_seconds() / 60.0


def _rank_key(event: dict) -> tuple:
    """
    V5 tie-breaking:

        1. priority, higher first
        2. start_utc, earlier first
        3. duration, shorter first
        4. id, ascending plain string
    """

    return (
        -event["priority"],
        event["start_utc"],
        event["duration_minutes"],
        event["id"],
    )


def _event_sort_key(event: dict) -> tuple:
    """
    Final schedule ordering:
        start_utc, then event ID.
    """

    return (
        event["start_utc"],
        event["id"],
    )


def _public_event(event: dict) -> dict:
    """
    Convert internal event representation to output representation.
    """

    output = dict(event)

    output["start_utc"] = _iso_utc(
        event["start_utc"]
    )

    output["end_utc"] = _iso_utc(
        event["end_utc"]
    )

    output.pop("duration_minutes", None)

    return output


# ============================================================
# CONFLICT HANDLING
# ============================================================

def events_conflict(
    event_a: dict,
    event_b: dict,
    buffer_minutes: int = 0,
) -> bool:
    """
    Determine whether two events conflict.

    Intervals are half-open:

        [start, end)

    Therefore:
        A ending exactly when B starts = no conflict.

    With buffer B:

        later.start < earlier.end + B
    """

    if event_a["start_utc"] <= event_b["start_utc"]:
        earlier = event_a
        later = event_b
    else:
        earlier = event_b
        later = event_a

    buffered_end = (
        earlier["end_utc"].timestamp()
        + buffer_minutes * 60
    )

    return (
        later["start_utc"].timestamp()
        < buffered_end
    )


def conflict_detail(
    event_a: dict,
    event_b: dict,
    buffer_minutes: int,
) -> dict:
    """
    Produce factual conflict information.

    Distinguishes:
        - true temporal overlap
        - buffer-only conflict

    A buffer-only conflict occurs when the events do not overlap,
    but the gap between them is smaller than the required buffer.
    """

    if event_a["start_utc"] <= event_b["start_utc"]:
        earlier = event_a
        later = event_b
    else:
        earlier = event_b
        later = event_a

    gap_minutes = (
        later["start_utc"]
        - earlier["end_utc"]
    ).total_seconds() / 60.0

    actual_overlap = (
        later["start_utc"]
        < earlier["end_utc"]
    )

    buffer_only = (
        not actual_overlap
        and gap_minutes < buffer_minutes
    )

    if buffer_only:
        description = (
            "buffer-only conflict: "
            f"gap is {gap_minutes:g} minutes, "
            f"required buffer is {buffer_minutes:g} minutes"
        )

    elif actual_overlap:
        description = (
            "time overlap: "
            f"{earlier['id']} overlaps {later['id']}"
        )

    else:
        description = "no conflict"

    return {
        "event_ids": [
            event_a["id"],
            event_b["id"],
        ],
        "earlier_event": earlier["id"],
        "later_event": later["id"],
        "gap_minutes": gap_minutes,
        "buffer_minutes": buffer_minutes,
        "overlap": actual_overlap,
        "buffer_only": buffer_only,
        "description": description,
    }


# ============================================================
# EVENT VALIDATION
# ============================================================

def validate_event(event: Any) -> list[dict]:
    """
    Validate a single event.

    Returns a list of validation errors.
    """

    errors = []

    if not isinstance(event, dict):
        return [
            {
                "code": INVALID_EVENT,
                "message": "Event must be an object.",
            }
        ]

    event_id = event.get("id")

    # --------------------------------------------------------
    # ID
    # --------------------------------------------------------

    if (
        not isinstance(event_id, str)
        or not event_id.strip()
    ):
        errors.append(
            {
                "code": "INVALID_FIELD_TYPE",
                "field": "id",
                "message": (
                    "id must be a non-empty string."
                ),
            }
        )

    # --------------------------------------------------------
    # Start/end
    # --------------------------------------------------------

    if "start" not in event:
        errors.append(
            {
                "code": "INVALID_TIME",
                "field": "start",
                "message": "start is required.",
            }
        )

    if "end" not in event:
        errors.append(
            {
                "code": "INVALID_TIME",
                "field": "end",
                "message": "end is required.",
            }
        )

    if "start" in event and "end" in event:

        try:
            start = _parse_datetime(
                event["start"]
            )

            end = _parse_datetime(
                event["end"]
            )

            if end <= start:
                errors.append(
                    {
                        "code": "INVALID_RANGE",
                        "field": "end",
                        "message": (
                            "end must be later than start."
                        ),
                    }
                )

        except ValueError as exc:

            if str(exc) == "NAIVE_DATETIME":
                errors.append(
                    {
                        "code": "INVALID_TIMEZONE",
                        "field": "start/end",
                        "message": (
                            "Naive timestamps require timezone "
                            "information."
                        ),
                    }
                )

            else:
                errors.append(
                    {
                        "code": "INVALID_TIME",
                        "field": "start/end",
                        "message": (
                            "Invalid ISO-8601 timestamp."
                        ),
                    }
                )

    # --------------------------------------------------------
    # Priority
    # --------------------------------------------------------

    if not _is_valid_priority(
        event.get("priority")
    ):
        errors.append(
            {
                "code": "INVALID_FIELD_TYPE",
                "field": "priority",
                "message": (
                    "priority must be an integer from 1 to 5."
                ),
            }
        )

    # --------------------------------------------------------
    # Timezone
    # --------------------------------------------------------

    if not _valid_timezone(
        event.get("timezone")
    ):
        errors.append(
            {
                "code": "INVALID_TIMEZONE",
                "field": "timezone",
                "message": (
                    "timezone must be a recognized "
                    "IANA timezone."
                ),
            }
        )

    # --------------------------------------------------------
    # mandatory
    # --------------------------------------------------------

    if "mandatory" in event:

        if not isinstance(
            event["mandatory"],
            bool,
        ):
            errors.append(
                {
                    "code": "INVALID_FIELD_TYPE",
                    "field": "mandatory",
                    "message": (
                        "mandatory must be boolean."
                    ),
                }
            )

    # --------------------------------------------------------
    # depends_on
    # --------------------------------------------------------

    if "depends_on" in event:

        if not isinstance(
            event["depends_on"],
            list,
        ):
            errors.append(
                {
                    "code": "INVALID_FIELD_TYPE",
                    "field": "depends_on",
                    "message": (
                        "depends_on must be an array."
                    ),
                }
            )

        else:

            for dependency in event["depends_on"]:

                if not isinstance(
                    dependency,
                    str,
                ):
                    errors.append(
                        {
                            "code": "INVALID_FIELD_TYPE",
                            "field": "depends_on",
                            "message": (
                                "Every dependency ID must "
                                "be a string."
                            ),
                        }
                    )
                    break

    return errors


# ============================================================
# NORMALIZATION
# ============================================================

def normalize_event(event: dict) -> dict:
    """
    Normalize an event to UTC.

    If explicit start_utc/end_utc are supplied, they are
    authoritative according to V5.
    """

    normalized = dict(event)

    normalized.setdefault(
        "mandatory",
        False,
    )

    normalized.setdefault(
        "depends_on",
        [],
    )

    normalized.setdefault(
        "title",
        "",
    )

    # --------------------------------------------------------
    # Explicit UTC values are authoritative.
    # --------------------------------------------------------

    if (
        "start_utc" in event
        and "end_utc" in event
    ):

        start_utc = _parse_datetime(
            event["start_utc"]
        )

        end_utc = _parse_datetime(
            event["end_utc"]
        )

        start_utc = _utc(start_utc)
        end_utc = _utc(end_utc)

    else:

        start = _parse_datetime(
            event["start"]
        )

        end = _parse_datetime(
            event["end"]
        )

        start_utc = _utc(start)
        end_utc = _utc(end)

    normalized["start_utc"] = start_utc
    normalized["end_utc"] = end_utc

    normalized["duration_minutes"] = (
        _duration_minutes(
            start_utc,
            end_utc,
        )
    )

    return normalized


# ============================================================
# DEPENDENCY GRAPH
# ============================================================

def find_dependency_cycles(
    events: dict[str, dict],
) -> set[str]:
    """
    Return every event ID belonging to a dependency cycle.
    """

    state: dict[str, int] = {}
    stack: list[str] = []
    cycle_nodes: set[str] = set()

    def dfs(node: str):

        state[node] = 1
        stack.append(node)

        for dependency in events[node].get(
            "depends_on",
            [],
        ):

            if dependency not in events:
                continue

            dependency_state = state.get(
                dependency,
                0,
            )

            if dependency_state == 0:

                dfs(dependency)

            elif dependency_state == 1:

                if dependency in stack:

                    index = stack.index(
                        dependency
                    )

                    cycle_nodes.update(
                        stack[index:]
                    )

        stack.pop()
        state[node] = 2

    for node in events:

        if state.get(node, 0) == 0:
            dfs(node)

    return cycle_nodes


def find_missing_dependencies(
    events: dict[str, dict],
) -> dict[str, list[str]]:
    """
    Return:

        {
            event_id: [missing dependency IDs]
        }
    """

    missing = {}

    for event_id, event in events.items():

        missing_ids = [
            dependency
            for dependency in event.get(
                "depends_on",
                [],
            )
            if dependency not in events
        ]

        if missing_ids:
            missing[event_id] = missing_ids

    return missing


def transitive_prerequisites(
    event_id: str,
    events: dict[str, dict],
) -> set[str]:
    """
    Return every transitive prerequisite.
    """

    result = set()
    visited = set()

    def visit(node: str):

        if node in visited:
            return

        visited.add(node)

        if node not in events:
            return

        for dependency in events[node].get(
            "depends_on",
            [],
        ):

            if dependency in events:

                result.add(dependency)

                visit(dependency)

    visit(event_id)

    return result


# ============================================================
# REQUIRED SET
# ============================================================

def build_required_set(
    events: dict[str, dict],
) -> set[str]:
    """
    Required set:

        every mandatory event
        +
        all transitive prerequisites
    """

    required = {
        event_id
        for event_id, event in events.items()
        if event.get("mandatory") is True
    }

    changed = True

    while changed:

        changed = False

        for event_id in list(required):

            if event_id not in events:
                continue

            for dependency in events[
                event_id
            ].get(
                "depends_on",
                [],
            ):

                if (
                    dependency in events
                    and dependency not in required
                ):

                    required.add(
                        dependency
                    )

                    changed = True

    return required


# ============================================================
# TOPOLOGICAL ORDER
# ============================================================

def dependency_order(
    event_ids: set[str],
    events: dict[str, dict],
) -> list[str]:
    """
    Return a deterministic prerequisite-first order.
    """

    result = []
    visited = set()
    visiting = set()

    def visit(event_id: str):

        if event_id in visited:
            return

        if event_id in visiting:
            return

        visiting.add(event_id)

        for dependency in sorted(
            events[event_id].get(
                "depends_on",
                [],
            )
        ):

            if dependency in event_ids:
                visit(dependency)

        visiting.remove(event_id)
        visited.add(event_id)
        result.append(event_id)

    for event_id in sorted(event_ids):
        visit(event_id)

    return result


# ============================================================
# RESULT CREATION
# ============================================================

def _empty_result(
    status: str = "partial",
) -> dict:

    return {
        "status": status,

        "mode": (
            "deterministic_scheduler"
        ),

        "input_errors": [],

        "schedule": [],

        "dropped": [],

        "trade_offs": [],

        "infeasibility": {},

        "verification": {
            "source": "none",
            "conflict_free": None,
            "hard_violations": [],
        },

        "optimality": (
            "not_claimed"
        ),

        "assumptions": [],

        "summary": "",
    }


# ============================================================
# EXTERNAL VALIDATOR MODE
# ============================================================

def _external_validator_mode(
    input_data: dict,
) -> dict:
    """
    V5 explain mode.

    If external scheduler and/or validator results are supplied,
    do not re-plan.

    Validator precedence:

        conflict_free == False
        OR
        hard_violations is non-empty

    causes:

        status = validation_failed
        schedule = []
        dropped = []
        trade_offs = []

    When the validator does not report a hard failure, the
    externally supplied scheduler result is preserved.
    """

    scheduler_result = input_data.get(
        "scheduler_result",
        {},
    )

    validator_report = input_data.get(
        "validator_report",
        {},
    )

    if not isinstance(
        scheduler_result,
        dict,
    ):
        scheduler_result = {}

    if not isinstance(
        validator_report,
        dict,
    ):
        validator_report = {}

    result = _empty_result()

    result["mode"] = (
        "explain_external_result"
    )

    # --------------------------------------------------------
    # Preserve validator evidence.
    # --------------------------------------------------------

    conflict_free = validator_report.get(
        "conflict_free",
        None,
    )

    hard_violations = validator_report.get(
        "hard_violations",
        [],
    )

    result["verification"] = {
        "source": "external_validator",
        "conflict_free": conflict_free,
        "hard_violations": hard_violations,
    }

    # --------------------------------------------------------
    # Validator failure takes precedence.
    # --------------------------------------------------------

    validator_failed = (
        conflict_free is False
        or bool(hard_violations)
    )

    if validator_failed:

        result["status"] = (
            "validation_failed"
        )

        result["schedule"] = []
        result["dropped"] = []
        result["trade_offs"] = []

        result["infeasibility"] = {}

        result["summary"] = (
            "The external validator reported "
            "a hard constraint violation. "
            "The externally supplied schedule "
            "was not accepted as conflict-free."
        )

        result["optimality"] = (
            "not_claimed"
        )

        result["assumptions"] = [
            (
                "The externally supplied scheduler result "
                "was not re-planned."
            ),
            (
                "The external validator report was treated "
                "as verification evidence."
            ),
            (
                "A validator-reported hard violation takes "
                "precedence over the supplied schedule."
            ),
        ]

        return result

    # --------------------------------------------------------
    # No validator failure.
    #
    # Preserve the external scheduler result.
    # --------------------------------------------------------

    result["status"] = (
        "partial"
    )

    result["schedule"] = scheduler_result.get(
        "schedule",
        [],
    )

    result["dropped"] = scheduler_result.get(
        "dropped",
        [],
    )

    result["trade_offs"] = scheduler_result.get(
        "trade_offs",
        [],
    )

    result["summary"] = (
        "The externally supplied schedule was inspected "
        "without re-planning. The external validator "
        "report was preserved as verification evidence."
    )

    result["optimality"] = (
        "not_claimed"
    )

    result["assumptions"] = [
        (
            "The externally supplied scheduler result "
            "was not re-planned."
        ),
        (
            "The external validator report was treated "
            "as verification evidence."
        ),
        (
            "No optimality claim is made."
        ),
    ]

    return result


# ============================================================
# MAIN RESOLVER
# ============================================================

def resolve_schedule(
    input_data: dict,
) -> dict:
    """
    Resolve a schedule using the V5 contract.
    """

    result = _empty_result()

    # ========================================================
    # R1: ROOT VALIDATION
    # ========================================================

    if not isinstance(
        input_data,
        dict,
    ):

        result["status"] = (
            "invalid_input"
        )

        result["input_errors"].append(
            {
                "code": "INVALID_ROOT",
                "message": (
                    "Input must be a JSON object."
                ),
            }
        )

        result["summary"] = (
            "The input root is invalid."
        )

        return result

    # --------------------------------------------------------
    # External validator / scheduler-result mode
    # --------------------------------------------------------

    if (
        "scheduler_result" in input_data
        or "validator_report" in input_data
    ):

        return _external_validator_mode(
            input_data
        )

    # ========================================================
    # EVENTS
    # ========================================================

    events_input = input_data.get(
        "events"
    )

    if not isinstance(
        events_input,
        list,
    ):

        result["status"] = (
            "invalid_input"
        )

        result["input_errors"].append(
            {
                "code": "INVALID_EVENTS",
                "message": (
                    "events must be an array."
                ),
            }
        )

        result["summary"] = (
            "The events field is invalid."
        )

        return result

    # ========================================================
    # CONFIG
    # ========================================================

    config = input_data.get(
        "config",
        {},
    )

    if not isinstance(
        config,
        dict,
    ):

        result["status"] = (
            "invalid_input"
        )

        result["input_errors"].append(
            {
                "code": "INVALID_CONFIG",
                "message": (
                    "config must be an object."
                ),
            }
        )

        return result

    buffer_minutes = config.get(
        "buffer_minutes",
        0,
    )

    if (
        not isinstance(
            buffer_minutes,
            int,
        )
        or isinstance(
            buffer_minutes,
            bool,
        )
        or buffer_minutes < 0
    ):

        result["status"] = (
            "invalid_input"
        )

        result["input_errors"].append(
            {
                "code": "INVALID_CONFIG",
                "field": "buffer_minutes",
                "message": (
                    "buffer_minutes must be "
                    "an integer >= 0."
                ),
            }
        )

        return result

    # ========================================================
    # DUPLICATE IDS
    # ========================================================

    raw_ids = []

    for event in events_input:

        if isinstance(event, dict):
            raw_ids.append(
                event.get("id")
            )

    if len(raw_ids) != len(set(raw_ids)):

        result["status"] = (
            "invalid_input"
        )

        result["input_errors"].append(
            {
                "code": "DUPLICATE_ID",
                "message": (
                    "Event IDs must be unique."
                ),
            }
        )

        return result

    # ========================================================
    # R1: VALIDATE EVENTS
    # ========================================================

    raw_event_map = {}
    valid_events = {}
    invalid_events = {}

    for event in events_input:

        if not isinstance(
            event,
            dict,
        ):

            result["input_errors"].append(
                {
                    "event_id": None,
                    "errors": [
                        {
                            "code": INVALID_EVENT,
                            "message": (
                                "Event must be an object."
                            ),
                        }
                    ],
                }
            )

            continue

        event_id = event.get("id")

        raw_event_map[event_id] = event

        errors = validate_event(
            event
        )

        if errors:

            invalid_events[event_id] = (
                errors
            )

            result["input_errors"].append(
                {
                    "event_id": event_id,
                    "errors": errors,
                }
            )

            continue

        try:

            normalized = normalize_event(
                event
            )

            valid_events[event_id] = (
                normalized
            )

        except ValueError as exc:

            invalid_events[event_id] = [
                {
                    "code": str(exc),
                    "message": (
                        "Could not normalize "
                        "event time."
                    ),
                }
            ]

            result["input_errors"].append(
                {
                    "event_id": event_id,
                    "errors": invalid_events[
                        event_id
                    ],
                }
            )

    # ========================================================
    # REQUIRED INVALID EVENT
    # ========================================================

    for event_id, event in raw_event_map.items():

        if (
            event.get("mandatory") is True
            and event_id in invalid_events
        ):

            result["status"] = (
                "infeasible"
            )

            result["infeasibility"] = {
                "code": (
                    "REQUIRED_EVENT_INVALID"
                ),
                "event_ids": [
                    event_id
                ],
                "message": (
                    f"Mandatory event {event_id} "
                    "is invalid and cannot be scheduled."
                ),
            }

            result["summary"] = (
                "Infeasible because a mandatory "
                "event is invalid."
            )

            return result

    # ========================================================
    # R3: MISSING DEPENDENCIES
    # ========================================================

    missing_dependencies = (
        find_missing_dependencies(
            valid_events
        )
    )

    for event_id, event in raw_event_map.items():

        if event.get("mandatory") is not True:
            continue

        for dependency in event.get(
            "depends_on",
            [],
        ):

            if dependency not in raw_event_map:

                result["status"] = (
                    "infeasible"
                )

                result["infeasibility"] = {
                    "code": (
                        "REQUIRED_DEPENDENCY_UNSATISFIABLE"
                    ),
                    "event_ids": [
                        event_id,
                        dependency,
                    ],
                    "message": (
                        f"Mandatory event {event_id} "
                        f"depends on missing event "
                        f"{dependency}."
                    ),
                }

                return result

    # ========================================================
    # R3: DEPENDENCY CYCLES
    # ========================================================

    cycle_nodes = (
        find_dependency_cycles(
            valid_events
        )
    )

    required = build_required_set(
        valid_events
    )

    required_cycle_nodes = (
        required.intersection(
            cycle_nodes
        )
    )

    if required_cycle_nodes:

        result["status"] = (
            "infeasible"
        )

        result["infeasibility"] = {
            "code": (
                "REQUIRED_DEPENDENCY_UNSATISFIABLE"
            ),
            "event_ids": sorted(
                required_cycle_nodes
            ),
            "message": (
                "A required event is part "
                "of a dependency cycle."
            ),
        }

        return result

    # ========================================================
    # REQUIRED DEPENDENCY INVALID
    # ========================================================

    for event_id in required:

        if event_id not in valid_events:

            result["status"] = (
                "infeasible"
            )

            result["infeasibility"] = {
                "code": (
                    "REQUIRED_DEPENDENCY_UNSATISFIABLE"
                ),
                "event_ids": [
                    event_id
                ],
                "message": (
                    "A required prerequisite "
                    "is invalid or unavailable."
                ),
            }

            return result

        for dependency in valid_events[
            event_id
        ].get(
            "depends_on",
            [],
        ):

            if dependency not in valid_events:

                result["status"] = (
                    "infeasible"
                )

                result["infeasibility"] = {
                    "code": (
                        "REQUIRED_DEPENDENCY_UNSATISFIABLE"
                    ),
                    "event_ids": [
                        event_id,
                        dependency,
                    ],
                    "message": (
                        "A required event has "
                        "an unavailable prerequisite."
                    ),
                }

                return result

    # ========================================================
    # R4: BUILD REQUIRED ORDER
    # ========================================================

    required_order = dependency_order(
        required,
        valid_events,
    )

    # ========================================================
    # R4: REQUIRED EVENT CONFLICTS
    #
    # Direct H2 conflicts among required events are classified
    # before dependency-order failures.
    # ========================================================

    for i in range(
        len(required_order)
    ):

        for j in range(
            i + 1,
            len(required_order),
        ):

            event_a = valid_events[
                required_order[i]
            ]

            event_b = valid_events[
                required_order[j]
            ]

            if events_conflict(
                event_a,
                event_b,
                buffer_minutes,
            ):

                detail = conflict_detail(
                    event_a,
                    event_b,
                    buffer_minutes,
                )

                result["status"] = (
                    "infeasible"
                )

                result["infeasibility"] = {
                    "code": (
                        "REQUIRED_EVENTS_OVERLAP"
                    ),
                    "event_ids": sorted(
                        [
                            event_a["id"],
                            event_b["id"],
                        ]
                    ),
                    "message": (
                        "Required events cannot "
                        "both be scheduled without "
                        "violating H2."
                    ),
                    "conflict": detail,
                }

                result["summary"] = (
                    "Infeasible because required "
                    "events conflict."
                )

                return result

    # ========================================================
    # R4: CHECK REQUIRED DEPENDENCY ORDER
    # ========================================================

    for event_id in required_order:

        event = valid_events[
            event_id
        ]

        for dependency in event.get(
            "depends_on",
            [],
        ):

            if dependency not in required:
                continue

            dependency_event = (
                valid_events[dependency]
            )

            if (
                dependency_event["end_utc"]
                > event["start_utc"]
            ):

                result["status"] = (
                    "infeasible"
                )

                result["infeasibility"] = {
                    "code": (
                        "REQUIRED_DEPENDENCY_UNSATISFIABLE"
                    ),
                    "event_ids": [
                        dependency,
                        event_id,
                    ],
                    "message": (
                        f"Prerequisite {dependency} "
                        f"does not finish before "
                        f"{event_id} starts."
                    ),
                }

                result["summary"] = (
                    "Infeasible because a required "
                    "dependency cannot be satisfied."
                )

                return result

    # ========================================================
    # SCHEDULE REQUIRED EVENTS
    # ========================================================

    scheduled = []
    scheduled_ids = set()

    for event_id in required_order:

        event = valid_events[
            event_id
        ]

        scheduled.append(
            event
        )

        scheduled_ids.add(
            event_id
        )

    # ========================================================
    # R5: OPTIONAL EVENT ELIGIBILITY
    # ========================================================

    ineligible = {}

    for event_id, event in valid_events.items():

        if event_id in required:
            continue

        # Cycle.
        if event_id in cycle_nodes:

            ineligible[event_id] = (
                DEPENDENCY_CYCLE
            )

            continue

        # Missing prerequisite.
        if event_id in missing_dependencies:

            ineligible[event_id] = (
                MISSING_PREREQ_ID
            )

            continue

        # Direct dependency validation.
        dependency_problem = False

        for dependency in event.get(
            "depends_on",
            [],
        ):

            if dependency not in valid_events:

                ineligible[event_id] = (
                    MISSING_PREREQ_ID
                )

                dependency_problem = True
                break

            dependency_event = (
                valid_events[
                    dependency
                ]
            )

            if (
                dependency_event["end_utc"]
                > event["start_utc"]
            ):

                ineligible[event_id] = (
                    PREREQ_ORDER_VIOLATION
                )

                dependency_problem = True
                break

        if dependency_problem:
            continue

        # Cascading dependency eligibility.
        prerequisites = (
            transitive_prerequisites(
                event_id,
                valid_events,
            )
        )

        for dependency in prerequisites:

            if dependency in ineligible:

                ineligible[event_id] = (
                    PREREQ_DROPPED
                )

                break

    # ========================================================
    # R6: RANK ELIGIBLE EVENTS
    # ========================================================

    eligible_events = [
        event
        for event_id, event
        in valid_events.items()
        if (
            event_id not in required
            and event_id not in ineligible
        )
    ]

    eligible_events.sort(
        key=_rank_key
    )

    # ========================================================
    # R7: ADMIT OPTIONAL EVENTS
    # ========================================================

    dropped = []
    trade_offs = []

    for event in eligible_events:

        event_id = event["id"]

        if event_id in scheduled_ids:
            continue

        # ----------------------------------------------------
        # Create dependency bundle.
        # ----------------------------------------------------

        bundle_ids = (
            transitive_prerequisites(
                event_id,
                valid_events,
            )
        )

        bundle_ids.add(
            event_id
        )

        bundle = [
            valid_events[
                dependency_id
            ]
            for dependency_id in bundle_ids
            if dependency_id
            not in scheduled_ids
        ]

        # ----------------------------------------------------
        # Check bundle eligibility.
        # ----------------------------------------------------

        bundle_blocked = False

        for member in bundle:

            if member["id"] in cycle_nodes:

                bundle_blocked = True
                break

            if member["id"] in ineligible:

                bundle_blocked = True
                break

        if bundle_blocked:

            dropped.append(
                {
                    "event_id": event_id,
                    "reason_code": (
                        PREREQ_DROPPED
                    ),
                    "reason": (
                        "A prerequisite required "
                        "by this event is not eligible."
                    ),
                    "conflicts_with": [],
                }
            )

            continue

        # ----------------------------------------------------
        # Check dependency order inside bundle.
        # ----------------------------------------------------

        dependency_order_invalid = False

        for member in bundle:

            for dependency in member.get(
                "depends_on",
                [],
            ):

                if dependency not in valid_events:

                    dependency_order_invalid = True
                    break

                dependency_event = (
                    valid_events[
                        dependency
                    ]
                )

                if (
                    dependency_event[
                        "end_utc"
                    ]
                    > member["start_utc"]
                ):

                    dependency_order_invalid = True
                    break

            if dependency_order_invalid:
                break

        if dependency_order_invalid:

            dropped.append(
                {
                    "event_id": event_id,
                    "reason_code": (
                        PREREQ_DROPPED
                    ),
                    "reason": (
                        "A prerequisite cannot "
                        "finish before its dependent "
                        "event starts."
                    ),
                    "conflicts_with": [],
                }
            )

            continue

        # ----------------------------------------------------
        # Check conflicts with scheduled events.
        # ----------------------------------------------------

        conflicts = []

        for member in bundle:

            for existing in scheduled:

                if events_conflict(
                    member,
                    existing,
                    buffer_minutes,
                ):

                    conflicts.append(
                        conflict_detail(
                            member,
                            existing,
                            buffer_minutes,
                        )
                    )

        # ----------------------------------------------------
        # Check conflicts inside bundle.
        # ----------------------------------------------------

        for i in range(
            len(bundle)
        ):

            for j in range(
                i + 1,
                len(bundle),
            ):

                member_a = bundle[i]
                member_b = bundle[j]

                if events_conflict(
                    member_a,
                    member_b,
                    buffer_minutes,
                ):

                    conflicts.append(
                        conflict_detail(
                            member_a,
                            member_b,
                            buffer_minutes,
                        )
                    )

        # ----------------------------------------------------
        # Bundle cannot be admitted.
        # ----------------------------------------------------

        if conflicts:

            conflict_ids = sorted(
                {
                    conflicting_id
                    for detail in conflicts
                    for conflicting_id in detail[
                        "event_ids"
                    ]
                    if conflicting_id != event_id
                }
            )

            primary_conflict = (
                conflicts[0]
                if conflicts
                else {}
            )

            dropped_item = {
                "event_id": event_id,
                "reason_code": (
                    CONFLICT_LOWER_RANK
                ),
                "reason": (
                    "The event or its dependency "
                    "bundle conflicts with an event "
                    "that was admitted earlier."
                ),
                "conflicts_with": conflict_ids,
                "detail": primary_conflict.get(
                    "description",
                    "conflict with an already scheduled event",
                ),
                "conflict_details": conflicts,
            }

            dropped.append(
                dropped_item
            )

            # ------------------------------------------------
            # Trade-off explanation.
            # ------------------------------------------------

            kept_events = sorted(
                scheduled_ids
            )

            conflicting_required = any(
                conflict_id in required
                for conflict_id in conflict_ids
            )

            if conflicting_required:

                decisive_rule = (
                    "mandatory/dependency"
                )

                comparison = (
                    f"Event {event_id} could not be "
                    "admitted because its bundle conflicts "
                    "with a required event."
                )

            else:

                decisive_rule = "priority"

                comparison = (
                    f"Event {event_id} has priority "
                    f"{event['priority']} and was considered "
                    "after previously admitted events under "
                    "the deterministic ranking order."
                )

            trade_offs.append(
                {
                    "dropped_event": event_id,
                    "kept_events": kept_events,
                    "decisive_rule": decisive_rule,
                    "comparison": comparison,
                }
            )

            continue

        # ----------------------------------------------------
        # Admit bundle.
        # ----------------------------------------------------

        bundle.sort(
            key=_event_sort_key
        )

        for member in bundle:

            if member["id"] not in scheduled_ids:

                scheduled.append(
                    member
                )

                scheduled_ids.add(
                    member["id"]
                )

    # ========================================================
    # ADD INELIGIBLE EVENTS TO DROPPED
    # ========================================================

    already_dropped = {
        item["event_id"]
        for item in dropped
    }

    for event_id, reason in ineligible.items():

        if event_id in already_dropped:
            continue

        if reason == DEPENDENCY_CYCLE:

            dropped.append(
                {
                    "event_id": event_id,
                    "reason_code": (
                        DEPENDENCY_CYCLE
                    ),
                    "reason": (
                        "The event is part of "
                        "a dependency cycle."
                    ),
                    "conflicts_with": [],
                }
            )

        elif reason == MISSING_PREREQ_ID:

            dropped.append(
                {
                    "event_id": event_id,
                    "reason_code": (
                        MISSING_PREREQ_ID
                    ),
                    "reason": (
                        "The event references "
                        "a missing prerequisite."
                    ),
                    "conflicts_with": [],
                }
            )

        elif reason == PREREQ_ORDER_VIOLATION:

            dropped.append(
                {
                    "event_id": event_id,
                    "reason_code": (
                        PREREQ_ORDER_VIOLATION
                    ),
                    "reason": (
                        "A prerequisite ends after "
                        "this event starts."
                    ),
                    "conflicts_with": [],
                }
            )

        elif reason == PREREQ_DROPPED:

            dropped.append(
                {
                    "event_id": event_id,
                    "reason_code": (
                        PREREQ_DROPPED
                    ),
                    "reason": (
                        "A prerequisite could "
                        "not be scheduled."
                    ),
                    "conflicts_with": [],
                }
            )

    # ========================================================
    # INVALID OPTIONAL EVENTS
    # ========================================================

    for event_id, errors in invalid_events.items():

        raw_event = raw_event_map.get(
            event_id,
            {},
        )

        if raw_event.get(
            "mandatory"
        ) is True:
            continue

        if event_id in scheduled_ids:
            continue

        dropped.append(
            {
                "event_id": event_id,
                "reason_code": (
                    INVALID_EVENT
                ),
                "reason": (
                    "The event is invalid "
                    "and cannot be scheduled."
                ),
                "conflicts_with": [],
                "validation_errors": errors,
            }
        )

    # ========================================================
    # R8: FINAL HARD-CONSTRAINT CHECK
    # ========================================================

    hard_violations = []

    # --------------------------------------------------------
    # H1: Only valid events.
    # --------------------------------------------------------

    for event in scheduled:

        if event["id"] in invalid_events:

            hard_violations.append(
                {
                    "constraint": "H1",
                    "event_id": event["id"],
                }
            )

    # --------------------------------------------------------
    # H2: No conflicts.
    # --------------------------------------------------------

    for i in range(
        len(scheduled)
    ):

        for j in range(
            i + 1,
            len(scheduled),
        ):

            event_a = scheduled[i]
            event_b = scheduled[j]

            if events_conflict(
                event_a,
                event_b,
                buffer_minutes,
            ):

                hard_violations.append(
                    {
                        "constraint": "H2",
                        "event_ids": [
                            event_a["id"],
                            event_b["id"],
                        ],
                    }
                )

    # --------------------------------------------------------
    # H3: All mandatory events scheduled.
    # --------------------------------------------------------

    for event_id in required:

        if event_id not in scheduled_ids:

            hard_violations.append(
                {
                    "constraint": "H3",
                    "event_id": event_id,
                }
            )

    # --------------------------------------------------------
    # H4: Dependencies satisfied.
    # --------------------------------------------------------

    for event in scheduled:

        for dependency in event.get(
            "depends_on",
            [],
        ):

            if dependency not in scheduled_ids:

                hard_violations.append(
                    {
                        "constraint": "H4",
                        "event_ids": [
                            dependency,
                            event["id"],
                        ],
                    }
                )

                continue

            dependency_event = (
                valid_events.get(
                    dependency
                )
            )

            if dependency_event is None:
                continue

            if (
                dependency_event[
                    "end_utc"
                ]
                > event["start_utc"]
            ):

                hard_violations.append(
                    {
                        "constraint": "H4",
                        "event_ids": [
                            dependency,
                            event["id"],
                        ],
                    }
                )

    # --------------------------------------------------------
    # H5: Times unchanged.
    # --------------------------------------------------------

    # The scheduler never modifies start/end,
    # so H5 is inherently satisfied for internally
    # normalized events.

    # ========================================================
    # HANDLE FINAL FAILURE
    # ========================================================

    if hard_violations:

        result["status"] = (
            "infeasible"
        )

        result["schedule"] = []
        result["dropped"] = []
        result["trade_offs"] = []

        affected_ids = sorted(
            {
                event_id
                for violation in hard_violations
                for event_id in (
                    violation.get(
                        "event_ids",
                        [
                            violation.get(
                                "event_id"
                            )
                        ],
                    )
                )
                if event_id is not None
            }
        )

        if any(
            violation[
                "constraint"
            ] == "H2"
            for violation in hard_violations
        ):

            code = (
                "REQUIRED_EVENTS_OVERLAP"
            )

        elif any(
            violation[
                "constraint"
            ] == "H4"
            for violation in hard_violations
        ):

            code = (
                "REQUIRED_DEPENDENCY_UNSATISFIABLE"
            )

        else:

            code = (
                "REQUIRED_DEPENDENCY_UNSATISFIABLE"
            )

        result["infeasibility"] = {
            "code": code,
            "event_ids": affected_ids,
            "hard_violations": hard_violations,
            "message": (
                "The final schedule violates "
                "one or more hard constraints."
            ),
        }

        result["summary"] = (
            "The schedule could not satisfy "
            "all hard constraints."
        )

        return result

    # ========================================================
    # FINAL OUTPUT SORTING
    # ========================================================

    scheduled.sort(
        key=_event_sort_key
    )

    dropped.sort(
        key=lambda item: item[
            "event_id"
        ]
    )

    trade_offs.sort(
        key=lambda item: item[
            "dropped_event"
        ]
    )

    # ========================================================
    # STATUS
    # ========================================================

    input_event_ids = {
        event.get("id")
        for event in events_input
        if isinstance(event, dict)
    }

    all_scheduled = (
        scheduled_ids
        == input_event_ids
        and not result["input_errors"]
    )

    if all_scheduled:

        result["status"] = (
            "complete"
        )

    else:

        result["status"] = (
            "partial"
        )

    # ========================================================
    # OUTPUT
    # ========================================================

    result["schedule"] = [
        _public_event(event)
        for event in scheduled
    ]

    result["dropped"] = dropped

    result["trade_offs"] = trade_offs

    result["verification"] = {
        "source": "none",
        "conflict_free": None,
        "hard_violations": [],
    }

    result["optimality"] = (
        "not_claimed"
    )

    result["assumptions"] = [
        "All event times are treated as fixed.",
        "Intervals use half-open semantics [start, end).",
        (
            f"A buffer of {buffer_minutes} minutes "
            "is applied to every scheduled-event pair."
        ),
        "Times are compared in UTC.",
        (
            "Optional events are ranked by "
            "priority, start time, duration, and ID."
        ),
        "No event is moved or resized.",
        "No optimality claim is made.",
        "No external validator was supplied.",
    ]

    result["summary"] = (
        f"Scheduled {len(scheduled)} of "
        f"{len(input_event_ids)} input events. "
        f"Mandatory events and their prerequisites "
        f"were treated as hard constraints. "
        f"Eligible optional events were considered "
        f"in deterministic priority order."
    )

    return result