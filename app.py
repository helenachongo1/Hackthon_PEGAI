import io
from datetime import date, datetime, time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import pandas as pd
import streamlit as st

from scheduler import resolve_schedule, RULE_ORDER


# PAGE CONFIG

st.set_page_config(
    page_title="Schedule Conflict Resolver",
    page_icon="📅",
    layout="wide",
)


# CONSTANTS

TIMEZONES = [
    "Asia/Kolkata",
    "UTC",
    "Europe/London",
    "America/New_York",
]

DEFAULT_DATE = date(2026, 10, 3)

TIME_OPTIONS = [
    f"{hour:02d}:{minute:02d} {ampm}"
    for ampm in ["AM", "PM"]
    for hour in range(1, 13)
    for minute in [0, 30]
]


# HEADER

st.title("📅 Schedule Conflict Resolver")

st.caption(
    "Resolve scheduling conflicts using mandatory events, dependencies, "
    "time zones, buffers, deterministic ranking, and constraint validation."
)


# SIDEBAR

with st.sidebar:

    st.header("Resolution Rules")

    for i, rule in enumerate(RULE_ORDER, 1):
        st.write(f"**{i}.** {rule}")

    st.divider()

    st.info(
        "Event times are fixed. The resolver does not move or resize events. "
        "Mandatory-event feasibility and dependencies are handled before "
        "optional events."
    )

    st.markdown(
        "**Optional-event tie-break:** longer duration first; "
        "if durations are equal, the event entered first is considered first."
    )

    st.caption(
        "Priority is retained as event metadata but does not override "
        "the duration-first ranking rule."
    )


# TIME HELPERS

def parse_12_hour_time(time_string):
    """
    Convert a display value such as '12:00 PM'
    into a Python time object.
    """

    try:
        return datetime.strptime(
            time_string,
            "%I:%M %p",
        ).time()

    except ValueError as exc:
        raise ValueError(
            f"Invalid time '{time_string}'. "
            "Expected format such as '10:30 AM' or '02:00 PM'."
        ) from exc


def make_datetime_string(
    selected_date,
    selected_time,
    timezone_name,
):
    """
    Convert local date + 12-hour time + IANA timezone
    into an ISO-8601 timezone-aware datetime.
    """

    try:
        parsed_time = parse_12_hour_time(selected_time)

        local_datetime = datetime.combine(
            selected_date,
            parsed_time,
        )

        local_datetime = local_datetime.replace(
            tzinfo=ZoneInfo(timezone_name)
        )

        return local_datetime.isoformat()

    except ZoneInfoNotFoundError as exc:
        raise ValueError(
            f"Invalid time zone '{timezone_name}'."
        ) from exc

    except ValueError as exc:
        raise ValueError(
            f"Could not create datetime for "
            f"{selected_date} {selected_time} "
            f"in {timezone_name}: {exc}"
        ) from exc


# EVENT CREATION

def new_event(event_number):

    default_start_hours = [
        9,
        10,
        11,
        13,
        14,
        15,
        16,
        17,
    ]

    start_hour = default_start_hours[
        (event_number - 1) % len(default_start_hours)
    ]

    def format_time(hour):
        if hour == 0:
            return "12:00 AM"

        if hour < 12:
            return f"{hour:02d}:00 AM"

        if hour == 12:
            return "12:00 PM"

        return f"{hour - 12:02d}:00 PM"

    end_hour = (start_hour + 1) % 24

    return {
        "id": f"E{event_number}",
        "title": f"Event {event_number}",

        "date": DEFAULT_DATE,
        "end_date": DEFAULT_DATE,

        "start_time": format_time(start_hour),
        "end_time": format_time(end_hour),

        "timezone": "Asia/Kolkata",

        "priority": 3,
        "mandatory": False,

        "depends_on_text": "",
    }


# INITIAL EVENTS

if "event_rows" not in st.session_state:

    first_event = new_event(1)

    first_event.update({
        "title": "Project Meeting",
        "start_time": "10:00 AM",
        "end_time": "11:00 AM",
        "priority": 5,
        "mandatory": True,
    })

    second_event = new_event(2)

    second_event.update({
        "title": "Study Session",
        "start_time": "10:30 AM",
        "end_time": "12:00 PM",
        "priority": 2,
    })

    st.session_state.event_rows = [
        first_event,
        second_event,
    ]


# MAIN DESCRIPTION

st.header("Create Your Schedule")

st.write(
    "Create events manually or upload a CSV schedule. "
    "Each event keeps its original date, time, and duration."
)


# CSV SECTION

with st.expander("📄 CSV upload / template", expanded=False):

    st.markdown(
        """
        Upload a CSV containing:

        `id`, `title`, `start`, `end`, `timezone`, `priority`, `mandatory`

        Optional:

        `depends_on`

        Start and end must be timezone-aware ISO-8601 timestamps, for example:

        `2026-10-03T10:00:00+05:30`
        """
    )

    template = pd.DataFrame([
        {
            "id": "E1",
            "title": "Project Meeting",
            "start": "2026-10-03T10:00:00+05:30",
            "end": "2026-10-03T11:00:00+05:30",
            "timezone": "Asia/Kolkata",
            "priority": 5,
            "mandatory": True,
            "depends_on": "",
        },
        {
            "id": "E2",
            "title": "Study Session",
            "start": "2026-10-03T10:30:00+05:30",
            "end": "2026-10-03T12:00:00+05:30",
            "timezone": "Asia/Kolkata",
            "priority": 2,
            "mandatory": False,
            "depends_on": "",
        },
    ])

    st.download_button(
        "Download CSV template",
        template.to_csv(index=False).encode("utf-8"),
        "schedule_template.csv",
        "text/csv",
    )

    uploaded_file = st.file_uploader(
        "Upload schedule CSV",
        type=["csv"],
        key="schedule_csv",
    )

    if uploaded_file is not None:

        try:

            uploaded_file.seek(0)

            csv_preview = pd.read_csv(
                uploaded_file,
                dtype={
                    "id": str,
                    "title": str,
                },
            )

            required_cols = {
                "id",
                "title",
                "start",
                "end",
            }

            missing_cols = (
                required_cols
                - set(csv_preview.columns)
            )

            if missing_cols:

                st.error(
                    "CSV is missing required columns: "
                    + ", ".join(sorted(missing_cols))
                )

            else:

                st.success(
                    f"CSV loaded: {len(csv_preview)} event row(s). "
                    "The uploaded CSV will be used when you resolve the schedule."
                )

                st.dataframe(
                    csv_preview,
                    use_container_width=True,
                    hide_index=True,
                )

        except Exception as exc:

            st.error(
                f"Could not read the CSV: {exc}"
            )


# READ CSV

uploaded_file = st.session_state.get(
    "schedule_csv"
)

csv_events = None

if uploaded_file is not None:

    try:

        uploaded_file.seek(0)

        csv_df = pd.read_csv(
            uploaded_file,
            dtype={
                "id": str,
                "title": str,
            },
        )

        required_cols = {
            "id",
            "title",
            "start",
            "end",
        }

        missing_cols = (
            required_cols
            - set(csv_df.columns)
        )

        if missing_cols:

            csv_events = None

        else:

            csv_events = []

            for _, row in csv_df.iterrows():

                timezone_value = row.get(
                    "timezone",
                    "UTC",
                )

                timezone_name = (
                    str(timezone_value).strip()
                    if pd.notna(timezone_value)
                    else "UTC"
                )

                priority_value = row.get(
                    "priority",
                    3,
                )

                priority = (
                    int(priority_value)
                    if pd.notna(priority_value)
                    else 3
                )

                mandatory_value = row.get(
                    "mandatory",
                    False,
                )

                mandatory = (
                    str(mandatory_value)
                    .strip()
                    .lower()
                    in {
                        "true",
                        "1",
                        "yes",
                        "y",
                    }
                )

                deps_value = row.get(
                    "depends_on",
                    "",
                )

                if pd.notna(deps_value):

                    deps = [
                        part.strip()
                        for part in str(
                            deps_value
                        ).split(";")
                        if part.strip()
                    ]

                else:

                    deps = []

                event = {
                    "id": str(
                        row["id"]
                    ).strip(),

                    "title": str(
                        row["title"]
                    ).strip(),

                    "start": str(
                        row["start"]
                    ).strip(),

                    "end": str(
                        row["end"]
                    ).strip(),

                    "timezone": timezone_name,

                    "priority": priority,

                    "mandatory": mandatory,

                    "depends_on": deps,
                }

                csv_events.append(event)

    except Exception:

        csv_events = None


# MANUAL EVENT BUILDER

if csv_events is None:

    st.subheader("Events")

    top1, top2, top3 = st.columns(
        [1, 1, 4]
    )

    with top1:

        if st.button(
            "＋ Add event",
            use_container_width=True,
        ):

            next_number = (
                len(
                    st.session_state.event_rows
                )
                + 1
            )

            st.session_state.event_rows.append(
                new_event(next_number)
            )

            st.rerun()

    with top2:

        if st.button(
            "Reset events",
            use_container_width=True,
        ):

            first_event = new_event(1)
            second_event = new_event(2)

            st.session_state.event_rows = [
                first_event,
                second_event,
            ]

            st.rerun()

    st.caption(
        "Events with equal durations are considered "
        "in the order they appear here."
    )

    remove_index = None

    # EVENT CARDS
    
    for idx, row in enumerate(
        st.session_state.event_rows
    ):

        event_title = (
            row["title"]
            if row["title"].strip()
            else "Untitled event"
        )

        with st.container(border=True):

            # EVENT HEADER
            
            header1, header2 = st.columns(
                [5, 1]
            )

            with header1:

                st.markdown(
                    f"### {row['id']} · {event_title}"
                )

            with header2:

                if (
                    len(
                        st.session_state.event_rows
                    )
                    > 1
                ):

                    if st.button(
                        "Remove",
                        key=f"remove_{idx}",
                        use_container_width=True,
                    ):

                        remove_index = idx

            # BASIC INFORMATION
            
            info1, info2, info3 = st.columns(
                [1.2, 3, 1]
            )

            with info1:

                row["id"] = st.text_input(
                    "Event ID",
                    value=row["id"],
                    key=f"id_{idx}",
                )

            with info2:

                row["title"] = st.text_input(
                    "Title",
                    value=row["title"],
                    key=f"title_{idx}",
                )

            with info3:

                row["priority"] = st.number_input(
                    "Priority",
                    min_value=1,
                    max_value=5,
                    value=int(row["priority"]),
                    step=1,
                    key=f"priority_{idx}",
                )

            st.markdown("**Schedule**")

            # START
            
            start1, start2, start3 = st.columns(
                [1.4, 1.1, 1.5]
            )

            with start1:

                row["date"] = st.date_input(
                    "Start date",
                    value=row["date"],
                    key=f"date_{idx}",
                )

            with start2:

                current_start = row.get(
                    "start_time",
                    "09:00 AM",
                )

                if current_start not in TIME_OPTIONS:
                    current_start = "09:00 AM"

                row["start_time"] = st.selectbox(
                    "Start time",
                    TIME_OPTIONS,
                    index=TIME_OPTIONS.index(
                        current_start
                    ),
                    key=f"start_time_{idx}",
                )

            with start3:

                timezone_index = (
                    TIMEZONES.index(
                        row["timezone"]
                    )
                    if row["timezone"]
                    in TIMEZONES
                    else 0
                )

                row["timezone"] = st.selectbox(
                    "Time zone",
                    TIMEZONES,
                    index=timezone_index,
                    key=f"tz_{idx}",
                )

            # END
            
            end1, end2, end3 = st.columns(
                [1.4, 1.1, 1.5]
            )

            with end1:

                row["end_date"] = st.date_input(
                    "End date",
                    value=row.get(
                        "end_date",
                        row["date"],
                    ),
                    key=f"end_date_{idx}",
                )

            with end2:

                current_end = row.get(
                    "end_time",
                    "10:00 AM",
                )

                if current_end not in TIME_OPTIONS:
                    current_end = "10:00 AM"

                row["end_time"] = st.selectbox(
                    "End time",
                    TIME_OPTIONS,
                    index=TIME_OPTIONS.index(
                        current_end
                    ),
                    key=f"end_time_{idx}",
                )

            with end3:

                st.markdown(
                    """
                    <div style="
                        padding-top: 32px;
                        color: #777;
                        font-size: 0.9rem;
                    ">
                        Same timezone is used for
                        start and end.
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

            # EVENT PREVIEW
            
            st.markdown(
                f"""
                <div style="
                    padding: 10px 14px;
                    margin: 4px 0 12px 0;
                    border-radius: 8px;
                    background-color: rgba(128,128,128,0.08);
                    font-size: 0.92rem;
                ">
                    🕐 <b>
                    {row['date'].strftime('%b %d, %Y')}
                    · {row['start_time']}
                    </b>
                    &nbsp;&nbsp;→&nbsp;&nbsp;
                    <b>
                    {row['end_date'].strftime('%b %d, %Y')}
                    · {row['end_time']}
                    </b>
                    <br>
                    🌐 {row['timezone']}
                </div>
                """,
                unsafe_allow_html=True,
            )

            # OPTIONS
            
            option1, option2 = st.columns(
                [1, 3]
            )

            with option1:

                row["mandatory"] = st.checkbox(
                    "Mandatory event",
                    value=bool(
                        row["mandatory"]
                    ),
                    key=f"mandatory_{idx}",
                )

            with option2:

                row["depends_on_text"] = st.text_input(
                    "Depends on IDs",
                    value=row[
                        "depends_on_text"
                    ],
                    key=f"deps_{idx}",
                    placeholder="Example: E1, E2",
                    help=(
                        "Enter prerequisite event IDs "
                        "separated by commas."
                    ),
                )

        st.write("")


    # REMOVE EVENT
    
    if remove_index is not None:

        st.session_state.event_rows.pop(
            remove_index
        )

        st.rerun()


# SCHEDULER CONFIGURATION

st.divider()

st.subheader("Scheduler Configuration")

buffer_minutes = st.number_input(
    "Buffer between events (minutes)",
    min_value=0,
    value=0,
    step=5,
    help=(
        "Minimum required gap between events. "
        "The resolver does not move events to create the buffer."
    ),
)


# BUILD MANUAL EVENTS

def build_manual_events():

    events = []

    for idx, row in enumerate(
        st.session_state.event_rows
    ):

        event_number = idx + 1

        event_id = row["id"].strip()

        title = row["title"].strip()

        if not event_id:

            raise ValueError(
                f"Event {event_number}: Event ID cannot be empty."
            )

        if not title:

            raise ValueError(
                f"Event {event_number}: Event title cannot be empty."
            )

        # Dependencies
        
        deps = [
            part.strip()
            for part in row[
                "depends_on_text"
            ].split(",")
            if part.strip()
        ]

        # Date validation
        
        start_date = row["date"]

        end_date = row.get(
            "end_date",
            start_date,
        )

        if end_date < start_date:

            raise ValueError(
                f"Event '{event_id}': "
                "End date cannot be before the start date."
            )

        # Datetime construction
        
        start = make_datetime_string(
            start_date,
            row["start_time"],
            row["timezone"],
        )

        end = make_datetime_string(
            end_date,
            row["end_time"],
            row["timezone"],
        )

        # Local chronological validation
        
        start_dt = datetime.fromisoformat(
            start
        )

        end_dt = datetime.fromisoformat(
            end
        )

        if end_dt <= start_dt:

            raise ValueError(
                f"Event '{event_id}': "
                "End must be after start. "
                f"You entered "
                f"{start_date.strftime('%b %d, %Y')} "
                f"{row['start_time']} → "
                f"{end_date.strftime('%b %d, %Y')} "
                f"{row['end_time']}."
            )

        events.append({
            "id": event_id,
            "title": title,

            "start": start,
            "end": end,

            "timezone": row["timezone"],

            "priority": int(
                row["priority"]
            ),

            "mandatory": bool(
                row["mandatory"]
            ),

            "depends_on": deps,
        })

    return events


# RESOLVE

st.divider()

if st.button(
    "Resolve Schedule",
    type="primary",
    use_container_width=True,
):

    try:

        if (
            uploaded_file is not None
            and csv_events is None
        ):

            raise ValueError(
                "The uploaded CSV could not be parsed. "
                "Check its columns and values, or remove "
                "the upload to use manual event entry."
            )

        if csv_events is not None:

            events = csv_events

        else:

            events = build_manual_events()

        if not events:

            raise ValueError(
                "Add at least one event or upload "
                "a non-empty CSV."
            )

        result = resolve_schedule(
            {
                "events": events,

                "config": {
                    "buffer_minutes": int(
                        buffer_minutes
                    )
                },
            }
        )

        st.session_state[
            "last_result"
        ] = result

        st.session_state[
            "last_events"
        ] = events

    except Exception as exc:

        st.error(
            f"Unable to resolve the schedule: {exc}"
        )

        with st.expander(
            "Technical details"
        ):

            st.exception(exc)


# RESULTS

result = st.session_state.get(
    "last_result"
)

if result:

    events = st.session_state.get(
        "last_events",
        [],
    )

    st.divider()

    st.subheader("Resolution Result")

    status = result.get(
        "status",
        "unknown",
    )

    messages = {

        "complete": (
            st.success,
            "COMPLETE — all input events were scheduled.",
        ),

        "partial": (
            st.warning,
            "PARTIAL — a schedule was produced, "
            "but some events were not scheduled.",
        ),

        "infeasible": (
            st.error,
            "INFEASIBLE — the required constraints "
            "cannot all be satisfied.",
        ),

        "invalid_input": (
            st.error,
            "INVALID INPUT — the schedule could "
            "not be processed.",
        ),

        "validation_failed": (
            st.error,
            "VALIDATION FAILED — a hard constraint "
            "violation was reported.",
        ),
    }

    if status in messages:

        fn, message = messages[status]

        fn(message)

    else:

        st.warning(
            f"Status: {status}"
        )

    # METRICS
    
    m1, m2, m3 = st.columns(3)

    m1.metric(
        "Status",
        status,
    )

    m2.metric(
        "Scheduled",
        len(
            result.get(
                "schedule",
                [],
            )
        ),
    )

    m3.metric(
        "Dropped",
        len(
            result.get(
                "dropped",
                [],
            )
        ),
    )

    # ORIGINAL SCHEDULE
    
    st.subheader("Original Schedule")

    original_rows = []

    for i, event in enumerate(events):

        original_rows.append({
            "Input order": i + 1,
            "ID": event.get("id"),
            "Event": event.get("title"),
            "Start": event.get("start"),
            "End": event.get("end"),
            "Priority": event.get("priority"),
            "Mandatory": event.get("mandatory"),
            "Time zone": event.get("timezone"),
            "Depends on": ", ".join(
                event.get(
                    "depends_on",
                    [],
                )
            ),
        })

    st.dataframe(
        original_rows,
        use_container_width=True,
        hide_index=True,
    )

    # FINAL SCHEDULE
    
    st.subheader("Final Schedule")

    schedule = result.get(
        "schedule",
        [],
    )

    if schedule:

        schedule_rows = []

        for event in schedule:

            schedule_rows.append({
                "ID": event.get("id"),

                "Event": event.get(
                    "title",
                    event.get("id"),
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
                ),
            })

        st.dataframe(
            schedule_rows,
            use_container_width=True,
            hide_index=True,
        )

    else:

        st.info(
            "No events could be scheduled."
        )

    # DROPPED EVENTS
    
    dropped = result.get(
        "dropped",
        [],
    )

    if dropped:

        st.subheader("Dropped Events")

        for item in dropped:

            event_id = item.get(
                "id",
                "Unknown",
            )

            reason = item.get(
                "reason_code",
                "UNKNOWN",
            )

            with st.expander(
                f"{event_id} — {reason}"
            ):

                st.write(
                    f"**Event:** "
                    f"{item.get('title', event_id)}"
                )

                st.write(
                    f"**Reason code:** "
                    f"`{reason}`"
                )

                if item.get(
                    "description"
                ):

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
                        item[
                            "conflict_details"
                        ]
                    )

    # TRADE-OFFS
    
    trade_offs = result.get(
        "trade_offs",
        [],
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

    # INFEASIBILITY
    
    if result.get(
        "infeasibility"
    ):

        st.subheader(
            "Why the Schedule Is Infeasible"
        )

        st.json(
            result[
                "infeasibility"
            ]
        )

    # INPUT ERRORS
    
    input_errors = result.get(
        "input_errors",
        [],
    )

    if input_errors:

        st.subheader(
            "Input Errors"
        )

        st.json(
            input_errors
        )

    # VERIFICATION
    
    st.subheader("Verification")

    verification = result.get(
        "verification",
        {},
    )

    v1, v2 = st.columns(2)

    v1.metric(
        "Verification Source",
        verification.get(
            "source",
            "none",
        ),
    )

    conflict_free = verification.get(
        "conflict_free"
    )

    v2.metric(
        "Conflict-Free",
        (
            "YES"
            if conflict_free is True
            else "NO"
            if conflict_free is False
            else "NOT VERIFIED"
        ),
    )

    # OPTIMALITY
    
    st.subheader("Optimality")

    st.info(
        result.get(
            "optimality",
            "not_claimed",
        )
    )

    # SUMMARY
    
    if result.get("summary"):

        st.subheader(
            "Summary"
        )

        st.write(
            result["summary"]
        )

    # ASSUMPTIONS
    
    if result.get(
        "assumptions"
    ):

        with st.expander(
            "Assumptions"
        ):

            for assumption in result[
                "assumptions"
            ]:

                st.write(
                    f"• {assumption}"
                )

    # RAW JSON
    
    with st.expander(
        "View Raw JSON"
    ):

        st.json(
            result
        )