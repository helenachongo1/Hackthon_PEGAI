from datetime import datetime
from zoneinfo import ZoneInfo


# TIME ZONE CONVERSION

TIMEZONE_MAP = {
    "IST": "Asia/Kolkata",
    "UAE": "Asia/Dubai",
    "UTC": "UTC",
    "EST": "America/New_York",
    "PST": "America/Los_Angeles"
}


def to_utc(event):
    """
    Convert event start/end from its timezone to UTC.
    Assumes the event occurs on 2026-10-03.
    """

    timezone_name = TIMEZONE_MAP.get(
        event.get("timezone", "IST"),
        "Asia/Kolkata"
    )

    tz = ZoneInfo(timezone_name)

    start = datetime.strptime(
        f"2026-10-03 {event['start']}",
        "%Y-%m-%d %H:%M"
    ).replace(tzinfo=tz)

    end = datetime.strptime(
        f"2026-10-03 {event['end']}",
        "%Y-%m-%d %H:%M"
    ).replace(tzinfo=tz)

    return start.astimezone(ZoneInfo("UTC")), \
           end.astimezone(ZoneInfo("UTC"))


# EVENT OVERLAP

def events_overlap(event1, event2):

    start1, end1 = to_utc(event1)
    start2, end2 = to_utc(event2)

    return start1 < end2 and start2 < end1


# CONFLICT DETECTION

def find_conflicts(events):

    conflicts = []

    for i in range(len(events)):

        for j in range(i + 1, len(events)):

            if events_overlap(events[i], events[j]):

                conflicts.append({
                    "event1": events[i]["name"],
                    "event2": events[j]["name"],
                    "event1_id": events[i]["id"],
                    "event2_id": events[j]["id"]
                })

    return conflicts


# DEPENDENCY CHECK

def check_dependencies(events):

    event_map = {
        event["id"]: event
        for event in events
    }

    violations = []

    for event in events:

        for dependency_id in event.get("depends_on", []):

            if dependency_id not in event_map:
                violations.append({
                    "event": event["name"],
                    "reason": f"Missing dependency {dependency_id}"
                })
                continue

            dependency = event_map[dependency_id]

            _, dependency_end = to_utc(dependency)
            event_start, _ = to_utc(event)

            if event_start < dependency_end:

                violations.append({
                    "event": event["name"],
                    "dependency": dependency["name"],
                    "reason": "Event starts before dependency finishes"
                })

    return violations


# FIXED EVENT CHECK

def check_fixed_events(original, final):

    original_map = {
        event["id"]: event
        for event in original
    }

    violations = []

    for event in final:

        if event["id"] not in original_map:
            continue

        original_event = original_map[event["id"]]

        if original_event.get("fixed", False):

            if (
                original_event["start"] != event["start"]
                or original_event["end"] != event["end"]
            ):

                violations.append({
                    "event": event["name"],
                    "reason": "Fixed event was moved"
                })

    return violations


# FINAL VALIDATION

def validate_schedule(original, final):

    conflicts = find_conflicts(final)

    dependency_violations = check_dependencies(final)

    fixed_violations = check_fixed_events(
        original,
        final
    )

    valid = (
        len(conflicts) == 0
        and len(dependency_violations) == 0
        and len(fixed_violations) == 0
    )

    return {
        "valid": valid,
        "zero_conflicts": len(conflicts) == 0,
        "conflict_count": len(conflicts),
        "conflicts": conflicts,
        "dependency_violations": dependency_violations,
        "fixed_event_violations": fixed_violations
    }