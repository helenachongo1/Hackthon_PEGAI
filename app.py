import streamlit as st
from datetime import date, time, datetime
from zoneinfo import ZoneInfo

from scheduler import resolve_schedule, RULE_ORDER


# ============================================================
# PAGE CONFIG
# ============================================================

st.set_page_config(
    page_title="Schedule Conflict Resolver",
    page_icon="📅",
    layout="wide"
)


# ============================================================
# HEADER
# ============================================================

st.title("📅 Schedule Conflict Resolver")

st.caption(
    "Deterministic scheduling using priorities, mandatory events, "
    "dependencies, time zones, buffers, and constraint validation."
)


# ============================================================
# SIDEBAR — RULE ORDER
# ============================================================

with st.sidebar:

    st.header("Rule Order")

    for i, rule in enumerate(RULE_ORDER, 1):
        st.write(f"**{i}.** {rule}")

    st.divider()

    st.info(
        "Event times are fixed. The resolver does not move or resize "
        "events. Mandatory events are treated as hard constraints."
    )


# ============================================================
# EVENT INPUT
# ============================================================

st.header("Create Your Schedule")

schedule_date = st.date_input(
    "Schedule Date",
    value=date(2026, 10, 3)
)

st.divider()

col1, col2 = st.columns(2)


# ============================================================
# EVENT 1
# ============================================================

with col1:

    st.subheader("Event 1")

    event1_title = st.text_input(
        "Title",
        value="Project Meeting",
        key="e1_title"
    )

    e1_col1, e1_col2 = st.columns(2)

    with e1_col1:
        event1_start = st.time_input(
            "Start",
            value=time(10, 0),
            key="e1_start"
        )

    with e1_col2:
        event1_end = st.time_input(
            "End",
            value=time(11, 0),
            key="e1_end"
        )

    event1_priority = st.number_input(
        "Priority (1–5)",
        min_value=1,
        max_value=5,
        value=5,
        step=1,
        key="e1_priority"
    )

    event1_mandatory = st.checkbox(
        "Mandatory event",
        value=True,
        key="e1_mandatory"
    )

    event1_timezone = st.selectbox(
        "Time zone",
        [
            "Asia/Kolkata",
            "UTC",
            "Europe/London",
            "America/New_York"
        ],
        index=0,
        key="e1_timezone"
    )


# ============================================================
# EVENT 2
# ============================================================

with col2:

    st.subheader("Event 2")

    event2_title = st.text_input(
        "Title",
        value="Study Session",
        key="e2_title"
    )

    e2_col1, e2_col2 = st.columns(2)

    with e2_col1:
        event2_start = st.time_input(
            "Start",
            value=time(10, 30),
            key="e2_start"
        )

    with e2_col2:
        event2_end = st.time_input(
            "End",
            value=time(12, 0),
            key="e2_end"
        )

    event2_priority = st.number_input(
        "Priority (1–5)",
        min_value=1,
        max_value=5,
        value=2,
        step=1,
        key="e2_priority"
    )

    event2_mandatory = st.checkbox(
        "Mandatory event",
        value=False,
        key="e2_mandatory"
    )

    event2_timezone = st.selectbox(
        "Time zone",
        [
            "Asia/Kolkata",
            "UTC",
            "Europe/London",
            "America/New_York"
        ],
        index=0,
        key="e2_timezone"
    )


# ============================================================
# CONFIGURATION
# ============================================================

st.divider()

st.subheader("Scheduler Configuration")

buffer_minutes = st.number_input(
    "Buffer between events (minutes)",
    min_value=0,
    value=0,
    step=5
)


# ============================================================
# DATETIME CONVERSION
# ============================================================

def make_datetime_string(
    selected_date,
    selected_time,
    timezone_name
):
    """
    Create an ISO-8601 datetime with an explicit timezone offset.

    Example:
    2026-10-03T10:00:00+05:30
    """

    try:

        dt = datetime.combine(
            selected_date,
            selected_time
        ).replace(
            tzinfo=ZoneInfo(timezone_name)
        )

        return dt.isoformat()

    except Exception as e:

        raise ValueError(
            f"Invalid timezone '{timezone_name}': {e}"
        )


# ============================================================
# RESOLVE BUTTON
# ============================================================

st.divider()

if st.button(
    "Resolve Schedule",
    type="primary",
    use_container_width=True
):

    try:

        # ----------------------------------------------------
        # BUILD ISO-8601 DATETIMES
        # ----------------------------------------------------

        event1_start_iso = make_datetime_string(
            schedule_date,
            event1_start,
            event1_timezone
        )

        event1_end_iso = make_datetime_string(
            schedule_date,
            event1_end,
            event1_timezone
        )

        event2_start_iso = make_datetime_string(
            schedule_date,
            event2_start,
            event2_timezone
        )

        event2_end_iso = make_datetime_string(
            schedule_date,
            event2_end,
            event2_timezone
        )


        # ----------------------------------------------------
        # BUILD V5 EVENTS
        # ----------------------------------------------------

        events = [

            {
                "id": "E1",
                "title": event1_title,
                "start": event1_start_iso,
                "end": event1_end_iso,
                "timezone": event1_timezone,
                "priority": int(event1_priority),
                "mandatory": bool(event1_mandatory),
                "depends_on": []
            },

            {
                "id": "E2",
                "title": event2_title,
                "start": event2_start_iso,
                "end": event2_end_iso,
                "timezone": event2_timezone,
                "priority": int(event2_priority),
                "mandatory": bool(event2_mandatory),
                "depends_on": []
            }
        ]


        # ----------------------------------------------------
        # V5 INPUT OBJECT
        # ----------------------------------------------------

        input_data = {

            "events": events,

            "config": {
                "buffer_minutes": int(buffer_minutes)
            }
        }


        # ----------------------------------------------------
        # RUN V5 SCHEDULER
        # ----------------------------------------------------

        result = resolve_schedule(input_data)


        st.divider()


        # ====================================================
        # RESOLUTION RESULT
        # ====================================================

        st.subheader("Resolution Result")

        status = result.get(
            "status",
            "unknown"
        )


        if status == "complete":

            st.success(
                "COMPLETE — all input events were scheduled."
            )

        elif status == "partial":

            st.warning(
                "PARTIAL — a valid schedule was produced, "
                "but one or more events were not scheduled."
            )

        elif status == "infeasible":

            st.error(
                "INFEASIBLE — the required constraints "
                "cannot all be satisfied."
            )

        elif status == "invalid_input":

            st.error(
                "INVALID INPUT — the schedule could "
                "not be processed."
            )

        elif status == "validation_failed":

            st.error(
                "VALIDATION FAILED — an external validator "
                "reported a hard constraint violation."
            )

        else:

            st.warning(
                f"Status: {status}"
            )


        # ====================================================
        # SUMMARY METRICS
        # ====================================================

        c1, c2, c3 = st.columns(3)

        with c1:

            st.metric(
                "Status",
                status
            )

        with c2:

            st.metric(
                "Scheduled",
                len(result.get("schedule", []))
            )

        with c3:

            st.metric(
                "Dropped",
                len(result.get("dropped", []))
            )


        # ====================================================
        # ORIGINAL SCHEDULE
        # ====================================================

        st.subheader("Original Schedule")

        original_rows = []

        for event in events:

            original_rows.append({

                "ID": event["id"],

                "Event": event["title"],

                "Start": event["start"],

                "End": event["end"],

                "Priority": event["priority"],

                "Mandatory": event["mandatory"],

                "Time Zone": event["timezone"]

            })


        st.dataframe(
            original_rows,
            use_container_width=True,
            hide_index=True
        )


        # ====================================================
        # FINAL SCHEDULE
        # ====================================================

        st.subheader("Final Schedule")

        schedule = result.get(
            "schedule",
            []
        )


        if schedule:

            final_rows = []

            for event in schedule:

                final_rows.append({

                    "ID": event.get("id"),

                    "Event": event.get(
                        "title",
                        event.get("id")
                    ),

                    "Start (UTC)": event.get(
                        "start_utc"
                    ),

                    "End (UTC)": event.get(
                        "end_utc"
                    ),

                    "Priority": event.get(
                        "priority"
                    ),

                    "Mandatory": event.get(
                        "mandatory"
                    )

                })


            st.dataframe(
                final_rows,
                use_container_width=True,
                hide_index=True
            )

        else:

            st.info(
                "No events could be scheduled."
            )


        # ====================================================
        # DROPPED EVENTS
        # ====================================================

        dropped = result.get(
            "dropped",
            []
        )


        if dropped:

            st.subheader("Dropped Events")

            for item in dropped:

                event_id = item.get(
                    "id",
                    "Unknown"
                )

                reason = item.get(
                    "reason_code",
                    "UNKNOWN"
                )


                with st.expander(
                    f"{event_id} — {reason}"
                ):

                    st.write(
                        f"**Event:** "
                        f"{item.get('title', event_id)}"
                    )

                    st.write(
                        f"**Reason code:** `{reason}`"
                    )


                    if item.get("description"):

                        st.write(
                            f"**Description:** "
                            f"{item['description']}"
                        )


                    if item.get(
                        "conflict_details"
                    ):

                        st.write(
                            "**Conflict details:**"
                        )

                        st.json(
                            item["conflict_details"]
                        )


        # ====================================================
        # TRADE-OFFS
        # ====================================================

        trade_offs = result.get(
            "trade_offs",
            []
        )


        if trade_offs:

            st.subheader("Trade-offs")


            for tradeoff in trade_offs:

                st.write(
                    f"**Dropped:** "
                    f"{tradeoff.get('dropped_event')}"
                )

                st.write(
                    f"**Kept:** "
                    f"{tradeoff.get('kept_events', [])}"
                )

                st.write(
                    f"**Decisive rule:** "
                    f"{tradeoff.get('decisive_rule')}"
                )

                st.write(
                    f"**Comparison:** "
                    f"{tradeoff.get('comparison')}"
                )

                st.divider()


        # ====================================================
        # INFEASIBILITY
        # ====================================================

        infeasibility = result.get(
            "infeasibility"
        )


        if infeasibility:

            st.subheader(
                "Why the Schedule Is Infeasible"
            )

            st.json(
                infeasibility
            )


        # ====================================================
        # VERIFICATION
        # ====================================================

        st.subheader("Verification")

        verification = result.get(
            "verification",
            {}
        )


        v1, v2 = st.columns(2)


        with v1:

            st.metric(
                "Verification Source",
                verification.get(
                    "source",
                    "none"
                )
            )


        with v2:

            conflict_free = verification.get(
                "conflict_free"
            )


            if conflict_free is True:

                verification_display = "YES"

            elif conflict_free is False:

                verification_display = "NO"

            else:

                verification_display = "NOT VERIFIED"


            st.metric(
                "Conflict-Free",
                verification_display
            )


        # ====================================================
        # ASSUMPTIONS
        # ====================================================

        assumptions = result.get(
            "assumptions",
            []
        )


        if assumptions:

            with st.expander(
                "Assumptions"
            ):

                for assumption in assumptions:

                    st.write(
                        f"• {assumption}"
                    )


        # ====================================================
        # OPTIMALITY
        # ====================================================

        st.subheader("Optimality")

        st.info(
            result.get(
                "optimality",
                "not_claimed"
            )
        )


        # ====================================================
        # SUMMARY
        # ====================================================

        summary = result.get(
            "summary"
        )


        if summary:

            st.subheader("Summary")

            st.write(
                summary
            )


        # ====================================================
        # RAW V5 OUTPUT
        # ====================================================

        with st.expander(
            "View Raw V5 JSON"
        ):

            st.json(
                result
            )


    except Exception as e:

        st.error(
            f"Unable to resolve the schedule: {e}"
        )

        st.exception(e)
