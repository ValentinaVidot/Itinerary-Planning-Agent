"""Streamlit interface for the itinerary planning agent."""

from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
import json
import re
from queue import Empty, Queue
import time

import streamlit as st

from itinerary import (
    Hotel,
    Stop,
    check_itinerary,
    create_trip,
    export_ics,
    load_itinerary,
    load_known_hotels,
    load_memories,
    load_places,
    load_saved_hotels,
    load_user_profiles,
    parse_coordinates,
    day_plan,
    save_saved_hotels,
    save_itinerary_data,
    save_memories,
    set_active_user,
    workspace_root,
)
from lab_support import open_lab


INTERESTS = [
    "history", "nature", "food", "shopping", "animals", "culture", "nightlife",
    "tech", "home_decor", "wellness", "fruits", "theme_park", "family", "cafe",
]
INTEREST_LABELS = {
    "history": "History",
    "nature": "Nature",
    "food": "Food",
    "shopping": "Shopping",
    "animals": "Animals",
    "culture": "Culture",
    "nightlife": "Nightlife",
    "tech": "Tech",
    "home_decor": "Home decor",
    "wellness": "Wellness & massage",
    "fruits": "Fruits",
    "theme_park": "Theme parks",
    "family": "Family",
    "cafe": "Cafes",
}
CITIES = ["Johor Bahru", "Genting Highlands", "Kuala Lumpur"]
HOTEL_TIMES = [f"{hour:02d}:{minute:02d}" for hour in range(24) for minute in (0, 30)]


@st.cache_resource
def _lab_resource():
    manager = open_lab()
    return manager, manager.__enter__()


def _session():
    if "agent_session" not in st.session_state:
        _, lab = _lab_resource()
        st.session_state.agent_session = lab.session(
            on_event=lambda _event: None
        )
    return st.session_state.agent_session


def _apply_theme():
    st.markdown(
        """
        <style>
        [data-testid="stMainBlockContainer"] {
            background: linear-gradient(135deg, #FFF9FF 0%, #bfe3f5 38%, #d8c4f0 72%, #DFE9F5 100%);
            border-radius: 18px;
            padding: 1.5rem;
        }
        h1, h2, h3 {
            font-size: 1.5rem;
        }
        h1 {
            color: #173b70;
            text-shadow: 2px 2px 4px rgba(23, 59, 112, 0.25);
        }
        h2, h3 {
            color: #254f87;
        }
        .hero-subheading {
            color: #254f87;
            font-size: 1.1rem;
            font-weight: 600;
            margin: 0.25rem 0 1rem;
        }
        h3 {
            text-shadow: 1px 1px 3px rgba(37, 79, 135, 0.2);
        }
        [data-testid="stVerticalBlockBorderWrapper"] {
            background: #FDF4CB;
            border: 2px solid #7fa4d1;
            border-radius: 14px;
            box-shadow:
                0 3px 6px rgba(255, 255, 255, 0.95) inset,
                0 -2px 0 rgba(124, 157, 199, 0.25) inset,
                0 7px 0 rgba(115, 151, 199, 0.55),
                0 14px 26px rgba(37, 79, 135, 0.32);
            transform: translateY(-2px);
            transition: box-shadow 0.2s ease, transform 0.2s ease;
        }
        [data-testid="stVerticalBlockBorderWrapper"]:hover {
            box-shadow:
                0 3px 6px rgba(255, 255, 255, 1) inset,
                0 -2px 0 rgba(124, 157, 199, 0.3) inset,
                0 8px 0 rgba(115, 151, 199, 0.65),
                0 18px 32px rgba(37, 79, 135, 0.4);
            transform: translateY(-5px);
        }
        .memory-card {
            background: #f1eaff;
            border: 2px solid #9b7bd3;
            border-radius: 16px;
            padding: 1rem 1.2rem;
            margin: 0.5rem 0 1rem;
        }
        div[data-testid="stPopover"] {
            position: fixed;
            right: 1.5rem;
            bottom: 1.5rem;
            width: fit-content;
            margin-left: auto;
            z-index: 999;
        }
        [data-testid="stButton"] > button,
        [data-testid="stDownloadButton"] > button,
        div[data-testid="stPopover"] > button {
            border: 2px solid #051650;
            border-radius: 999px;
            background: #051650;
            color: #ffffff;
            box-shadow: 0 4px 12px rgba(5, 22, 80, 0.3);
            font-weight: 600;
            padding: 0.65rem 1.1rem;
            white-space: nowrap;
        }
        [data-testid="stButton"] > button:hover,
        [data-testid="stDownloadButton"] > button:hover,
        div[data-testid="stPopover"] > button:hover {
            background: #0a266d;
            border-color: #051650;
            color: #ffffff;
            box-shadow: 0 6px 16px rgba(5, 22, 80, 0.4);
        }
        [data-testid="stButton"]:has(button[kind="primary"]) > button {
            border-color: #176b3a;
            background: linear-gradient(135deg, #2e9f5b 0%, #176b3a 100%);
            box-shadow: 0 4px 12px rgba(23, 107, 58, 0.35);
        }
        [class*="st-key-add_hotel"] button,
        [class*="st-key-create_trip"] button,
        [class*="st-key-next_review"] button,
        [class*="st-key-save_my_edits"] button,
        [class*="st-key-previous_step_1"] button {
            border-color: #176b3a;
            background: linear-gradient(135deg, #2e9f5b 0%, #176b3a 100%);
            box-shadow: 0 4px 12px rgba(23, 107, 58, 0.35);
        }
        [data-testid="stButton"]:has(button[kind="primary"]) > button:hover {
            background: linear-gradient(135deg, #3fba70 0%, #20824a 100%);
            border-color: #12552e;
            box-shadow: 0 6px 16px rgba(23, 107, 58, 0.45);
        }
        [class*="st-key-chat_send"] button {
            border-color: #051650;
            background: #051650;
        }
        [class*="st-key-chat_send"] button:hover {
            background: #0a266d;
            border-color: #051650;
        }
        [class*="st-key-add_hotel"] button:hover,
        [class*="st-key-create_trip"] button:hover,
        [class*="st-key-next_review"] button:hover,
        [class*="st-key-save_my_edits"] button:hover,
        [class*="st-key-previous_step_1"] button:hover {
            background: linear-gradient(135deg, #3fba70 0%, #20824a 100%);
            border-color: #12552e;
            box-shadow: 0 6px 16px rgba(23, 107, 58, 0.45);
        }
        [class*="st-key-remove_hotel_"] button,
        [class*="st-key-remove_memory_"] button {
            border: 1px solid #d66b72;
            border-radius: 4px;
            background: #f7c7ca;
            color: #7d1f2a;
            box-shadow: none;
        }
        [class*="st-key-remove_hotel_"] button:hover,
        [class*="st-key-remove_memory_"] button:hover {
            border-color: #b94b55;
            background: #f2aeb3;
            color: #64151e;
            box-shadow: none;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _snapshot(itinerary):
    return itinerary.model_dump(mode="json") if itinerary else None


def _show_agent_answer(answer):
    marker = "**Changes & flags:**"
    if marker not in answer:
        st.markdown(answer)
        return
    main_text, changes = answer.split(marker, 1)
    if main_text.strip():
        st.markdown(main_text)
    st.warning(f"{marker}{changes.strip()}")


def _profile_selector(container=None):
    profiles = load_user_profiles()
    profile_by_id = {profile.id: profile for profile in profiles}
    previous_id = st.session_state.get("loaded_user_id", profiles[0].id)
    profile_column = container
    if profile_column is None:
        _, profile_column = st.columns([8, 2])
    with profile_column:
        selected_id = st.selectbox(
            "User profile",
            [profile.id for profile in profiles],
            index=[profile.id for profile in profiles].index(previous_id),
            format_func=lambda user_id: profile_by_id[user_id].name,
            key="active_user_selector",
            label_visibility="collapsed",
        )
    set_active_user(selected_id)
    if selected_id != previous_id:
        st.session_state.loaded_user_id = selected_id
        st.session_state.hotel_drafts = [
            hotel.model_dump() for hotel in load_saved_hotels()
        ]
        st.session_state.interests = []
        st.session_state.pace = "relaxed"
        st.session_state.pop("agent_session", None)
        st.session_state.current_step = 1
        st.session_state.pop("trip_ready_for_next", None)
        st.rerun()
    st.session_state.loaded_user_id = selected_id


def _go_to_step(step: int) -> None:
    st.session_state.current_step = step
    st.rerun()


def _step_navigation(previous_step: int | None = None, next_step: int | None = None,
                 next_label: str = "Next") -> None:
    left, right = st.columns(2)
    if previous_step is not None and left.button("← Previous", key=f"previous_step_{previous_step}"):
        _go_to_step(previous_step)
    if next_step is not None and right.button(next_label, key=f"next_step_{next_step}"):
        _go_to_step(next_step)


def _log_turn(result, before, after, ui_edits):
    timestamp = datetime.now().astimezone()
    path = workspace_root() / "runtime" / "logs" / f"{timestamp:%Y%m%dT%H%M%S%f%z}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "timestamp": timestamp.isoformat(),
        "result": result.to_dict(),
        "itinerary_before": _snapshot(before),
        "itinerary_after": _snapshot(after),
        "ui_edits": ui_edits,
    }, indent=2) + "\n", encoding="utf-8")


def _run_turn(prompt, ui_edits=None, show_answer=True):
    session = _session()
    before = load_itinerary()
    events = Queue()
    def observe(event):
        events.put(event)

    session.on_event = observe
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(session.run, prompt)
        status = st.empty()
        while not future.done():
            shown = []
            try:
                while True:
                    event = events.get_nowait()
                    if event.get("type") in {"tool_started", "tool_completed", "tool_failed"}:
                        shown.append(event)
            except Empty:
                pass
            if shown:
                status.caption(" | ".join(
                    {
                        "tool_started": "Working on your request",
                        "tool_completed": "Finished a planning step",
                        "tool_failed": "A planning step needs attention",
                    }.get(event["type"], "Updating your itinerary")
                    for event in shown
                ))
            time.sleep(0.1)
        result = future.result()
    after = load_itinerary()
    _log_turn(result, before, after, ui_edits or {"prompt": prompt})
    if result.status == "failed":
        st.error(result.error or "The agent turn failed.")
    else:
        message = {
            "prompt": prompt,
            "answer": result.answer,
        }
        st.session_state.setdefault("chat_messages", []).append(message)
        st.session_state["chat_history"] = st.session_state["chat_messages"]
        if show_answer:
            _show_agent_answer(result.answer)
    return result


def _plan_window_text(plan):
    windows = plan["windows"]
    if plan["day_type"] in {"transfer", "check-in-and-out"}:
        return (
            f"Transfer day: before {windows[0]['end']} near {windows[0]['hotel'].name}, "
            f"after {windows[1]['start']} near {windows[1]['hotel'].name}."
        )
    window = windows[0]
    if plan["day_type"] == "check-in":
        return f"Check-in day: plan from {window['start']} near {window['hotel'].name}."
    if plan["day_type"] == "check-out":
        return f"Check-out day: plan before {window['end']} near {window['hotel'].name}."
    return f"Full day near {window['hotel'].name}."


def _chat_target_date(prompt: str, itinerary):
    plans = day_plan(itinerary)
    if not plans:
        return None
    lowered = prompt.lower()
    iso_match = re.search(r"\b\d{4}[-/]\d{1,2}[-/]\d{1,2}\b", lowered)
    if iso_match:
        try:
            target = datetime.strptime(iso_match.group(0).replace("/", "-"), "%Y-%m-%d").date()
        except ValueError:
            target = None
        if target is not None:
            return next((plan for plan in plans if plan["date"] == target), None)

    month_names = (
        "january|february|march|april|may|june|july|august|"
        "september|october|november|december"
    )
    named_date = re.search(
        rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+({month_names})"
        rf"(?:\s+(\d{{4}}))?\b|"
        rf"\b({month_names})\s+(\d{{1,2}})(?:st|nd|rd|th)?"
        rf"(?:\s+(\d{{4}}))?\b",
        lowered,
    )
    if named_date:
        groups = named_date.groups()
        if groups[0]:
            day_number, month_name, year = int(groups[0]), groups[1], groups[2]
        else:
            month_name, day_number, year = groups[3], int(groups[4]), groups[5]
        month_number = datetime.strptime(month_name, "%B").month
        matching = [
            plan for plan in plans
            if plan["date"].month == month_number and plan["date"].day == day_number
            and (year is None or plan["date"].year == int(year))
        ]
        if matching:
            return matching[0]

    for plan in plans:
        if plan["weekday"].lower() in lowered:
            return plan
    day_match = re.search(r"\bday\s+(\d+)\b", lowered)
    if day_match:
        index = int(day_match.group(1)) - 1
        if 0 <= index < len(plans):
            return plans[index]
    for day_type, labels in {
        "check-in": ("check-in day", "check in day", "arrival day"),
        "transfer": ("transfer day", "travel day"),
        "check-out": ("check-out day", "check out day", "departure day"),
    }.items():
        if any(label in lowered for label in labels):
            return next((plan for plan in plans if plan["day_type"] == day_type), None)
    return None


def _plan_day(plan):
    itinerary = load_itinerary()
    if itinerary is None:
        return None
    minimum, maximum = ((1, 2) if plan["day_type"] != "full" else
                        (3, 4) if itinerary.pace == "relaxed" else (5, 6))
    window_prompt = _plan_window_text(plan)
    prompt = (
        f"Plan {plan['date'].isoformat()} ({plan['weekday']}); "
        f"Keep locked stops. Target {minimum}-{maximum} stops. "
        f"{window_prompt} "
        "Plan only this date, use the date parameter when saving, and call check_day before saving."
    )
    result = _run_turn(prompt, {
        "action": "plan_day", "date": plan["date"].isoformat(),
        "target": f"{minimum}-{maximum}", "day_type": plan["day_type"],
    }, show_answer=False)
    return result


@st.dialog("Planning your trip")
def _plan_trip_days():
    itinerary = load_itinerary()
    if itinerary is None:
        st.error("Create a trip before planning.")
        return
    plans = day_plan(itinerary)
    progress = st.progress(0)
    failures = []
    notes = []
    status = st.empty()
    for index, plan in enumerate(plans, 1):
        status.write(
            f"Planning day {index} of {len(plans)}: "
            f"{plan['date'].strftime('%d %b')} ({plan['day_type']})"
        )
        result = _plan_day(plan)
        progress.progress(index / len(plans))
        if result is None or result.status == "failed":
            failures.append(plan["date"].isoformat())
            st.warning(f"⚠️ {plan['date'].strftime('%d %b')}: failed")
            if st.button("Retry this day", key=f"dialog_retry_{plan['date']}"):
                retry = _plan_day(plan)
                if retry is not None and retry.status != "failed":
                    failures.remove(plan["date"].isoformat())
                    st.rerun()
        else:
            saved = load_itinerary()
            day_stops = [stop for stop in saved.stops if stop.date == plan["date"]]
            flagged = sum(bool(stop.flags) for stop in day_stops)
            st.write(
                f"✅ {plan['date'].strftime('%d %b')}: "
                f"{len(day_stops)} stops, {flagged} flagged"
            )
            notes.append(f"### {plan['date'].strftime('%d %b')}\n\n{result.answer}")
    st.session_state.planning_failures = failures
    if notes:
        with st.expander("Agent notes"):
            for note in notes:
                st.markdown(note)
    st.success(f"Done: {len(plans)} days planned")
    if st.button("View itinerary", type="primary"):
        st.rerun()


def _trip_setup():
    st.header("Step 1 → Enter your booked hotel stays")
    st.caption("Add the hotels you have already booked, then choose your interests so the agent can plan around them.")
    if "hotel_drafts" not in st.session_state:
        st.session_state.hotel_drafts = [
            hotel.model_dump() for hotel in load_saved_hotels()
        ]
    hotels = st.session_state.hotel_drafts
    if hotels == [{}]:
        hotels.clear()
    if st.session_state.pop("reset_hotel_form", False):
        for key in (
            "hotel_form_city",
            "hotel_form_choice",
            "hotel_form_name",
            "hotel_form_coordinates",
            "hotel_form_check_in",
            "hotel_form_check_out",
            "hotel_form_check_in_time",
            "hotel_form_check_out_time",
        ):
            st.session_state.pop(key, None)
    known_hotels = load_known_hotels()
    form_column, summary_column = st.columns(2)
    with form_column:
        with st.container(border=True):
            st.subheader("Add a hotel")
            city_column, hotel_column = st.columns(2)
            with city_column:
                form_city = st.selectbox("City", CITIES, key="hotel_form_city")
            city_hotels = [hotel for hotel in known_hotels if hotel.city == form_city]
            hotel_by_id = {hotel.id: hotel for hotel in city_hotels}
            hotel_options = [hotel.id for hotel in city_hotels] + ["other"]
            if st.session_state.get("hotel_form_choice") not in hotel_options:
                st.session_state.hotel_form_choice = hotel_options[0]
            with hotel_column:
                selected_hotel = st.selectbox(
                    "Hotel",
                    hotel_options,
                    format_func=lambda hotel_id: hotel_by_id[hotel_id].name
                    if hotel_id in hotel_by_id else "Other hotel",
                    key="hotel_form_choice",
                )
            if selected_hotel == "other":
                other_name_column, coordinates_column = st.columns(2)
                with other_name_column:
                    hotel_name = st.text_input("Hotel name", key="hotel_form_name")
                with coordinates_column:
                    coordinates = st.text_input(
                        "Coordinates (right-click the hotel in Google Maps and click the numbers to copy them)",
                        placeholder="1.4655, 103.7578",
                        key="hotel_form_coordinates",
                    )
            else:
                known_hotel = hotel_by_id[selected_hotel]
                hotel_name = known_hotel.name
                coordinates = ""

            check_in_column, arrival_column = st.columns(2)
            with check_in_column:
                if "hotel_form_check_in" not in st.session_state:
                    st.session_state.hotel_form_check_in = date.today()
                check_in = st.date_input("Check-in", key="hotel_form_check_in")
                default_check_out = check_in + timedelta(days=1)
                if ("hotel_form_check_out" not in st.session_state
                        or st.session_state.hotel_form_check_out <= check_in):
                    st.session_state.hotel_form_check_out = default_check_out
            with arrival_column:
                check_in_time = st.selectbox(
                    "Check-in time", HOTEL_TIMES, index=HOTEL_TIMES.index("15:00"),
                    key="hotel_form_check_in_time",
                )
            check_out_column, departure_column = st.columns(2)
            with check_out_column:
                check_out = st.date_input("Check-out", key="hotel_form_check_out")
            with departure_column:
                check_out_time = st.selectbox(
                    "Check-out time", HOTEL_TIMES, index=HOTEL_TIMES.index("11:00"),
                    key="hotel_form_check_out_time",
                )

            if st.button("Add hotel", key="add_hotel"):
                try:
                    if not hotel_name.strip():
                        raise ValueError("Enter a hotel name.")
                    if selected_hotel == "other":
                        lat, lng = parse_coordinates(coordinates)
                    else:
                        lat, lng = known_hotel.lat, known_hotel.lng
                    if check_out <= check_in:
                        raise ValueError("Check-out must be after check-in.")
                    new_hotel = {
                        "name": hotel_name.strip(), "city": form_city, "lat": lat, "lng": lng,
                        "check_in": check_in, "check_out": check_out,
                        "check_in_time": check_in_time, "check_out_time": check_out_time,
                    }
                    for existing in hotels:
                        if check_in < existing["check_out"] and existing["check_in"] < check_out:
                            raise ValueError(
                                f"These dates overlap with {existing['name']} "
                                f"({existing['check_in']} to {existing['check_out']})."
                            )
                    hotels.append(new_hotel)
                    save_saved_hotels(hotels)
                    st.session_state.reset_hotel_form = True
                    st.rerun()
                except (ValueError, TypeError) as exc:
                    st.error(str(exc))

    with summary_column:
        with st.container(border=True):
            st.subheader("Added hotels")
            if hotels:
                for index, hotel in enumerate(hotels):
                    left, right = st.columns([5, 1])
                    left.write(
                        f"**{hotel['name']}** ({hotel['city']}) — "
                        f"{hotel['check_in']} {hotel.get('check_in_time', hotel.get('arrival_time', '15:00'))} to "
                        f"{hotel['check_out']} {hotel.get('check_out_time', hotel.get('departure_time', '11:00'))}"
                    )
                    if right.button("Remove", key=f"remove_hotel_{index}"):
                        hotels.pop(index)
                        save_saved_hotels(hotels)
                        st.rerun()
            else:
                st.info("Add at least one hotel before creating the trip.")
            interests = st.pills(
                "Interests", INTERESTS, format_func=lambda value: INTEREST_LABELS[value],
                selection_mode="multi", default=st.session_state.get("interests", []),
            )
            pace = st.radio(
                "Pace", ["relaxed", "packed"], horizontal=True,
                index=["relaxed", "packed"].index(st.session_state.get("pace", "relaxed")),
            )
    create_column, next_column = st.columns(2)
    with create_column:
        if st.button("Create trip", type="primary", key="create_trip"):
            try:
                if not hotels:
                    st.error("Add at least one hotel before creating the trip.")
                    return
                for index, draft in enumerate(hotels):
                    if draft.get("check_out") <= draft.get("check_in"):
                        st.error(f"Hotel {index + 1}: check-out must be after check-in.")
                        return
                ordered_stays = sorted(hotels, key=lambda draft: draft["check_in"])
                for previous, current in zip(ordered_stays, ordered_stays[1:]):
                    if current["check_in"] < previous["check_out"]:
                        st.error(
                            f"Hotel stays overlap: {previous['name']} ends on "
                            f"{previous['check_out']} but {current['name']} starts on "
                            f"{current['check_in']}."
                        )
                        return
                    if current["check_in"] > previous["check_out"]:
                        st.error(
                            f"Hotel stays have a gap: {previous['name']} ends on "
                            f"{previous['check_out']} but {current['name']} starts on "
                            f"{current['check_in']}."
                        )
                        return
                parsed = [Hotel(
                    name=draft["name"],
                    city=draft["city"],
                    lat=draft["lat"],
                    lng=draft["lng"],
                    check_in=draft["check_in"],
                    check_out=draft["check_out"],
                    check_in_time=draft.get("check_in_time", draft.get("arrival_time", "15:00")),
                    check_out_time=draft.get("check_out_time", draft.get("departure_time", "11:00")),
                ) for draft in hotels]
                itinerary = create_trip(parsed, list(interests), pace)
                save_saved_hotels(parsed)
                st.session_state.interests = list(interests)
                st.session_state.pace = pace
                st.success(f"Created a {len(itinerary.hotels)}-hotel trip.")
                _plan_trip_days()
                st.session_state.trip_ready_for_next = load_itinerary() is not None
            except (ValueError, TypeError) as exc:
                st.error(f"Trip details are invalid: {exc}")
    has_saved_trip = load_itinerary() is not None
    with next_column:
        if hotels and (st.session_state.get("trip_ready_for_next") or has_saved_trip):
            ready_message, ready_button = st.columns([3, 2], vertical_alignment="center")
            ready_message.success("Your saved trip is ready to review.")
            if ready_button.button("Next: Review itinerary", type="primary", key="next_review"):
                _go_to_step(2)


def _editor():
    itinerary = load_itinerary()
    if itinerary is None:
        st.info("Create a trip to edit its itinerary.")
        return
    st.header("Step 2 → Itinerary editor")
    if itinerary.approved:
        st.success("✅ Approved. Export your calendar below.")
    places = load_places()
    names = {place.name: place_id for place_id, place in places.items()}
    plans = day_plan(itinerary)
    days = [plan["date"] for plan in plans]
    overview_column, editor_column = st.columns([1, 2], gap="medium")
    with overview_column:
        with st.container(border=True):
            overview_rows = []
            icons = {
                "check-in": "🛬",
                "full": "🗓️",
                "transfer": "🧳",
                "check-out": "🛫",
                "check-in-and-out": "🧳",
            }
            for plan in plans:
                hotel = plan["hotel"]
                overview_rows.append({
                    "Date": plan["date"].isoformat(),
                    "Day": plan["weekday"],
                    "Type": f"{icons[plan['day_type']]} {plan['day_type']}",
                    "Hotel": hotel.name if hotel else "—",
                    "Plan window": _plan_window_text(plan),
                })
            st.caption("Trip overview")
            st.table(overview_rows)
            with st.container(border=True):
                _approve_export()
    with editor_column:
        with st.container(border=True):
            total_flags = sum(bool(stop.flags) for stop in itinerary.stops)
            st.caption(f"{total_flags} flagged stop(s)")
            flagged_only = st.checkbox("Show only flagged stops", key="show_flagged_stops")
            day_tabs = st.tabs([
                f"{icons[plan['day_type']]} {plan['date'].isoformat()} "
                f"({plan['day_type']})"
                for plan in plans
            ])
            for plan, day_tab in zip(plans, day_tabs):
                day = plan["date"]
                day_stops = sorted((stop for stop in itinerary.stops if stop.date == day), key=lambda stop: stop.start)
                with day_tab:
                    st.caption(
                        f"{plan['day_type'].replace('-', ' ').title()} day · "
                        f"{_plan_window_text(plan)}"
                    )
                    for flag in itinerary.day_flags.get(day.isoformat(), []):
                        st.warning(flag)
                    visible_stops = [stop for stop in day_stops if not flagged_only or stop.flags]
                    for stop in visible_stops:
                        with st.container(border=True):
                            left, right = st.columns([1, 3])
                            left.markdown(f"### {stop.start}")
                            if stop.locked:
                                left.caption("🔒 Locked")
                            if not itinerary.approved and left.button(
                                "Unlock" if stop.locked else "Lock",
                                key=f"toggle_lock_{day}_{stop.start}_{stop.place_id}",
                            ):
                                updated = [
                                    item.model_copy(update={"locked": not item.locked})
                                    if item is stop else item
                                    for item in itinerary.stops
                                ]
                                save_itinerary_data(check_itinerary(
                                    itinerary.model_copy(update={"stops": updated}), places
                                ))
                                st.toast("Saved: stop lock updated")
                                st.rerun()
                            if left.button(
                                "Remove", key=f"card_remove_{day}_{stop.start}_{stop.place_id}",
                                disabled=itinerary.approved or stop.locked,
                            ):
                                updated = [item for item in itinerary.stops if item is not stop]
                                save_itinerary_data(check_itinerary(
                                    itinerary.model_copy(update={"stops": updated}), places
                                ))
                                st.toast("Saved: stop removed")
                                st.rerun()
                            place = places.get(stop.place_id)
                            with right:
                                st.markdown(f"**{place.name if place else stop.place_id}**")
                                st.markdown(stop.reason)
                                badges = [
                                    f"⚠️ {flag}" for flag in stop.flags
                                ] or ["✅ Open at this time"]
                                st.caption(" · ".join(badges))
                    with st.expander("Edit times and places as a table"):
                        table = st.data_editor(
                            [{
                                "Time": stop.start,
                                "Place": places[stop.place_id].name if stop.place_id in places else stop.place_id,
                                "Reason": stop.reason,
                            } for stop in day_stops],
                            key=f"editor_{day}",
                            disabled=itinerary.approved,
                            hide_index=True,
                        )
                        if st.button("Save table edits", key=f"save_table_{day}", disabled=itinerary.approved):
                            try:
                                changed = []
                                for old, row in zip(day_stops, table.to_dict("records") if hasattr(table, "to_dict") else table):
                                    if old.locked and (
                                        str(row["Time"]) != old.start
                                        or names.get(str(row["Place"]), str(row["Place"])) != old.place_id
                                    ):
                                        raise ValueError(f"Locked stop at {old.start} cannot be moved.")
                                    changed.append(old.model_copy(update={
                                        "start": str(row["Time"]),
                                        "place_id": names.get(str(row["Place"]), str(row["Place"])),
                                    }))
                                replacement = [
                                    stop for stop in itinerary.stops if stop.date != day
                                ] + changed
                                save_itinerary_data(check_itinerary(
                                    itinerary.model_copy(update={
                                        "stops": replacement,
                                        "approved": False,
                                        "revision_note": "Saved table edits.",
                                    }), places
                                ))
                                st.toast("Saved: table edits checked")
                                st.rerun()
                            except (KeyError, TypeError, ValueError) as exc:
                                st.error(f"Could not save table edits: {exc}")
                    if plan["day_type"] == "full" and itinerary.day_flags.get(day.isoformat()):
                        if st.button("Fill this day", key=f"fill_day_{day}"):
                            _run_turn(
                                f"Add stops to {day.isoformat()} to reach the pace target. Keep existing stops.",
                                {"action": "fill_day", "date": day.isoformat()},
                            )
                            st.rerun()
                    if st.button("Re-plan this day", key=f"replan_day_{day}", disabled=itinerary.approved):
                        _run_turn(
                            f"Re-plan only {day.isoformat()}. Keep locked stops and use save_itinerary with date={day.isoformat()}.",
                            {"action": "replan_day", "date": day.isoformat()},
                        )
                        st.rerun()

def _chat():
    with st.popover("💬 Chat with your itinerary agent"):
        st.caption("Ask questions, request itinerary changes, or add a lasting preference.")
        chat_mode = st.pills(
            "What would you like to do?",
            ["Ask a question", "Request itinerary changes", "Add a preference"],
            key="chat_mode",
        )
        prompts = {
            "Ask a question": "Ask your itinerary agent anything",
            "Request itinerary changes": "Describe the itinerary changes you want",
            "Add a preference": "Tell the agent a preference to remember",
        }
        for message in st.session_state.get("chat_messages", st.session_state.get("chat_history", []))[-5:]:
            with st.chat_message("user"):
                st.write(message["prompt"])
            with st.chat_message("assistant"):
                _show_agent_answer(message["answer"])
        prompt = st.chat_input(
            prompts.get(chat_mode, "Choose an option above to start chatting"),
            key="chat_prompt",
        )
        if prompt:
            if chat_mode == "Request itinerary changes":
                prompt = (
                    "Please update my itinerary as follows. After completing the change, "
                    "if the request expresses a lasting preference, call propose_memory and "
                    "ask whether I want to save that preference to memory; do not save it "
                    "without my approval. "
                    f"Request: {prompt}"
                )
            elif chat_mode == "Add a preference":
                prompt = f"Please consider this lasting preference and propose it for memory approval: {prompt}"
            itinerary = load_itinerary()
            if itinerary is not None and chat_mode == "Request itinerary changes":
                target = _chat_target_date(prompt, itinerary)
                if target is not None:
                    prompt = (
                        f"Target exactly {target['date'].isoformat()} ({target['day_type']} day). "
                        f"{prompt} Keep all other dates unchanged."
                    )
                elif not any(token in prompt.lower() for token in ("trip", "all days", "whole")):
                    st.warning("Please specify a date, weekday, or day number for this change.")
                    return
            with st.spinner("The agent is thinking..."):
                _run_turn(prompt, {"action": "chat", "prompt": prompt})
            st.rerun()


def _memories():
    memories = load_memories()
    pending = [memory for memory in memories if memory["status"] == "pending"]
    approved = [memory for memory in memories if memory["status"] == "approved"]
    st.header("Memory approvals")
    st.caption("The agent may suggest remembering a lasting preference. Approve only preferences you want used in future planning.")
    if not pending and not approved:
        st.info("No memory suggestions yet.")
        return
    for memory in pending:
        st.markdown(
            f'<div class="memory-card"><strong>🧠 The agent noticed a preference</strong><br>'
            f'<b>{memory["preference"]}</b><br><small>Evidence: {memory["evidence"]}</small></div>',
            unsafe_allow_html=True,
        )
        left, right = st.columns(2)
        if left.button("Approve", key=f"approve_{memory['id']}"):
            memory["status"] = "approved"
            save_memories(memories)
            st.rerun()
        if right.button("Reject", key=f"reject_{memory['id']}"):
            memory["status"] = "rejected"
            save_memories(memories)
            st.rerun()
    st.subheader("Approved memories")
    for memory in approved:
        left, right = st.columns([4, 1])
        left.write(f"🧠 {memory['preference']} — {memory['evidence']}")
        if right.button("Remove", key=f"remove_memory_{memory['id']}"):
            save_memories([item for item in memories if item["id"] != memory["id"]])
            st.rerun()


def _approve_export():
    st.header("Approve and export")
    itinerary = load_itinerary()
    if itinerary is None:
        st.info("Create a trip first.")
        return
    if st.button("Approve itinerary", disabled=itinerary.approved):
        save_itinerary_data(itinerary.model_copy(update={"approved": True}))
        st.success("Itinerary approved.")
        st.rerun()
    if itinerary.approved:
        ics = export_ics(itinerary, load_places())
        st.download_button("Download calendar (.ics)", ics, "itinerary.ics", "text/calendar")
    else:
        st.caption("Approve the itinerary to enable calendar export.")


def main():
    st.set_page_config(page_title="Holi Holiday!", layout="wide")
    _apply_theme()
    st.markdown("<div style='height: 2rem;'></div>", unsafe_allow_html=True)
    title_column, profile_column = st.columns([8, 2], vertical_alignment="center")
    with title_column:
        st.title("🌴 Holi Holiday!")
        st.markdown(
            '<div class="hero-subheading">Itinerary planning has never been this easy.</div>',
            unsafe_allow_html=True,
        )
    _profile_selector(profile_column)
    _session()
    current_step = st.session_state.get("current_step", 1)
    if current_step == 1:
        _trip_setup()
    else:
        _editor()
        _chat()
        with st.sidebar:
            _memories()
        if st.button("← Previous", key="previous_step_1"):
            _go_to_step(1)


if __name__ == "__main__":
    main()
