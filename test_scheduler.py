from scheduler import resolve_schedule
from test_cases import TEST_CASES


# HELPERS

def get_scheduled_ids(result):
    return sorted(
        event.get("id")
        for event in result.get("schedule", [])
    )


def get_dropped_ids(result):
    return sorted(
        event.get("event_id")
        for event in result.get("dropped", [])
    )


def get_drop_reasons(result):
    reasons = {}

    for item in result.get("dropped", []):
        event_id = item.get("event_id")
        reason = item.get("reason_code")

        if event_id:
            reasons[event_id] = reason

    return reasons


def get_infeasibility_code(result):
    infeasibility = result.get("infeasibility")

    if isinstance(infeasibility, dict):
        return (
            infeasibility.get("code")
            or infeasibility.get("reason_code")
        )

    return None


def check_buffer_only(result):
    """
    T17 requires the explanation to explicitly identify
    the conflict as buffer-only and not as an overlap.
    """

    for item in result.get("dropped", []):

        detail = str(item.get("detail", "")).lower()

        if "buffer-only" in detail:
            if "overlap" in detail:
                return False

            return True

    return False


# TEST ONE CASE

def run_test(test_id, test_case):

    input_data = test_case["input"]
    expected = test_case["expected"]

    result = resolve_schedule(input_data)

    failures = []

    # STATUS
    
    if "status" in expected:

        actual_status = result.get("status")

        if actual_status != expected["status"]:
            failures.append(
                f"status: expected {expected['status']!r}, "
                f"got {actual_status!r}"
            )

    # SCHEDULED IDS
    
    expected_scheduled = sorted(
        expected.get("scheduled_ids", [])
    )

    actual_scheduled = get_scheduled_ids(result)

    if actual_scheduled != expected_scheduled:
        failures.append(
            "scheduled_ids: "
            f"expected {expected_scheduled}, "
            f"got {actual_scheduled}"
        )

    # DROPPED IDS
    
    expected_dropped = sorted(
        expected.get("dropped_ids", [])
    )

    actual_dropped = get_dropped_ids(result)

    if actual_dropped != expected_dropped:
        failures.append(
            "dropped_ids: "
            f"expected {expected_dropped}, "
            f"got {actual_dropped}"
        )

    # DROP REASONS
    
    if "drop_reasons" in expected:

        expected_reasons = expected["drop_reasons"]
        actual_reasons = get_drop_reasons(result)

        for event_id, expected_reason in expected_reasons.items():

            actual_reason = actual_reasons.get(event_id)

            if actual_reason != expected_reason:
                failures.append(
                    f"drop reason for {event_id}: "
                    f"expected {expected_reason!r}, "
                    f"got {actual_reason!r}"
                )

    # INFEASIBILITY CODE
    
    if "infeasibility_code" in expected:

        expected_code = expected["infeasibility_code"]
        actual_code = get_infeasibility_code(result)

        if actual_code != expected_code:
            failures.append(
                "infeasibility_code: "
                f"expected {expected_code!r}, "
                f"got {actual_code!r}"
            )

    # T17 — BUFFER-ONLY CONFLICT
    
    if expected.get("requires_buffer_only"):

        if not check_buffer_only(result):
            failures.append(
                "buffer-only requirement was not satisfied"
            )

    # RETURN
    
    return result, failures


# MAIN TEST RUNNER

def main():

    print("=" * 72)
    print("SCHEDULE CONFLICT RESOLVER — V5")
    print("T01–T20 AUTOMATED TEST SUITE")
    print("=" * 72)

    print(
        f"\nLoaded {len(TEST_CASES)} test cases."
    )

    passed = 0
    failed = 0

    failures_by_test = {}

    # RUN ALL TESTS
    
    for test_id, test_case in TEST_CASES.items():

        try:

            result, failures = run_test(
                test_id,
                test_case,
            )

        except Exception as exc:

            failed += 1

            failures_by_test[test_id] = [
                f"EXCEPTION: {type(exc).__name__}: {exc}"
            ]

            print(
                f"\n{test_id}  ❌ FAIL"
            )

            print(
                f"  Exception: {type(exc).__name__}: {exc}"
            )

            continue

        if failures:

            failed += 1

            failures_by_test[test_id] = failures

            print(
                f"\n{test_id}  ❌ FAIL"
            )

            print(
                f"  Name: {test_case.get('name', '')}"
            )

            for failure in failures:
                print(
                    f"  - {failure}"
                )

        else:

            passed += 1

            print(
                f"{test_id}  ✅ PASS"
            )

    # SUMMARY
    
    total = passed + failed

    print("\n" + "=" * 72)
    print("TEST SUMMARY")
    print("=" * 72)

    print(
        f"\nPassed : {passed}/{total}"
    )

    print(
        f"Failed : {failed}/{total}"
    )

    if total:
        percentage = (passed / total) * 100

        print(
            f"Score  : {percentage:.1f}%"
        )

    # FAILURE DETAILS
    
    if failures_by_test:

        print("\n" + "=" * 72)
        print("FAILURE DETAILS")
        print("=" * 72)

        for test_id, failures in failures_by_test.items():

            print(
                f"\n{test_id} — "
                f"{TEST_CASES[test_id].get('name', '')}"
            )

            for failure in failures:
                print(
                    f"  • {failure}"
                )

    # FINAL RESULT
    
    print("\n" + "=" * 72)

    if failed == 0:

        print(
            "ALL T01–T20 TESTS PASSED"
        )

    else:

        print(
            f"{failed} TEST(S) NEED ATTENTION"
        )

    print("=" * 72)


if __name__ == "__main__":
    main()

