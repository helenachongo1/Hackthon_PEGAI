from scheduler import resolve_schedule, RULE_ORDER


# ============================================================
# TEST INPUT
# ============================================================

events = [
    {
        "id": "E1",
        "title": "Project Meeting",
        "start": "2026-10-03T10:00:00+05:30",
        "end": "2026-10-03T11:00:00+05:30",
        "timezone": "Asia/Kolkata",
        "priority": 5,
        "mandatory": True,
        "depends_on": []
    },
    {
        "id": "E2",
        "title": "Study Session",
        "start": "2026-10-03T10:30:00+05:30",
        "end": "2026-10-03T12:00:00+05:30",
        "timezone": "Asia/Kolkata",
        "priority": 2,
        "mandatory": False,
        "depends_on": []
    }
]


# ============================================================
# HEADER
# ============================================================

print("=" * 60)
print("SCHEDULE CONFLICT RESOLVER — V5")
print("=" * 60)


# ============================================================
# RULE ORDER
# ============================================================

print("\nRULE ORDER:")

for i, rule in enumerate(RULE_ORDER, 1):
    print(f"{i}. {rule}")


# ============================================================
# ORIGINAL EVENTS
# ============================================================

print("\nORIGINAL EVENTS:")

for event in events:
    print(
        f"{event['id']} | "
        f"{event['title']} | "
        f"{event['start']} → {event['end']} | "
        f"Priority: {event['priority']} | "
        f"Mandatory: {event['mandatory']}"
    )


# ============================================================
# V5 INPUT
# ============================================================

input_data = {
    "events": events
}


# ============================================================
# RUN SCHEDULER
# ============================================================

result = resolve_schedule(input_data)


# ============================================================
# RESULT
# ============================================================

print("\n" + "=" * 60)
print("RESULT")
print("=" * 60)

print("Status:", result["status"])
print("Mode:", result["mode"])


# ============================================================
# INPUT ERRORS
# ============================================================

if result["input_errors"]:
    print("\nINPUT ERRORS:")

    for error in result["input_errors"]:
        print(error)


# ============================================================
# FINAL SCHEDULE
# ============================================================

print("\nFINAL SCHEDULE:")

if result["schedule"]:

    for event in result["schedule"]:
        print(
            f"{event['id']} | "
            f"{event.get('title', '')} | "
            f"{event['start_utc']} → {event['end_utc']}"
        )

else:
    print("No events scheduled.")


# ============================================================
# DROPPED EVENTS
# ============================================================

print("\nDROPPED EVENTS:")

if result["dropped"]:

    for event in result["dropped"]:

        print(
            f"{event['event_id']} | "
            f"{event.get('reason_code', 'NO_REASON')}"
        )

        if event.get("detail"):
            print(
                f"  Reason: {event['detail']}"
            )

else:
    print("None")


# ============================================================
# TRADE-OFFS
# ============================================================

print("\nTRADE-OFFS:")

if result["trade_offs"]:

    for tradeoff in result["trade_offs"]:

        print(
            f"Dropped: {tradeoff['dropped_event']}"
        )

        print(
            f"Kept: {tradeoff['kept_events']}"
        )

        print(
            f"Decisive rule: "
            f"{tradeoff['decisive_rule']}"
        )

        print(
            f"Comparison: "
            f"{tradeoff['comparison']}"
        )

else:
    print("None")


# ============================================================
# INFEASIBILITY
# ============================================================

if result["infeasibility"]:

    print("\nINFEASIBILITY:")

    print(result["infeasibility"])


# ============================================================
# VERIFICATION
# ============================================================

print("\nVERIFICATION:")

verification = result["verification"]

print(
    "Source:",
    verification.get("source")
)

print(
    "Conflict-free:",
    verification.get("conflict_free")
)


if verification.get("hard_violations"):
    print(
        "Hard violations:",
        verification["hard_violations"]
    )


# ============================================================
# OPTIMALITY
# ============================================================

print("\nOPTIMALITY:")

print(result["optimality"])


# ============================================================
# ASSUMPTIONS
# ============================================================

print("\nASSUMPTIONS:")

if result["assumptions"]:

    for assumption in result["assumptions"]:
        print("-", assumption)

else:
    print("None")


# ============================================================
# SUMMARY
# ============================================================

print("\nSUMMARY:")

print(result["summary"])


# ============================================================
# END
# ============================================================

print("\n" + "=" * 60)
print("TEST COMPLETE")
print("=" * 60)
