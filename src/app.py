"""Streamlit interface for the itinerary planning agent."""

from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
import json
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
        h3 {
            text-shadow: 1px 1px 3px rgba(37, 79, 135, 0.2);
        }
        [data-testid="stVerticalBlockBorderWrapper"] {
            background: #FDF4CB;
            border-color: #9bb9df;
            border-radius: 14px;
            box-shadow: 0 2px 8px rgba(37, 79, 135, 0.08);
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
            z-index: 999;
        }
        div[data-testid="stPopover"] > button {
            border: 2px solid #9b7bd3;
            border-radius: 999px;
            background: #f1eaff;
            color: #254f87;
            box-shadow: 0 4px 14px rgba(37, 79, 135, 0.2);
            font-weight: 600;
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


def _run_turn(prompt, ui_edits=None):
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
        _show_agent_answer(result.answer)
    return result


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
            "hotel_form_arrival_time",
            "hotel_form_departure_time",
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
                arrival_time = st.selectbox(
                    "Arrival time", HOTEL_TIMES, index=HOTEL_TIMES.index("15:00"),
                    key="hotel_form_arrival_time",
                )
            check_out_column, departure_column = st.columns(2)
            with check_out_column:
                check_out = st.date_input("Check-out", key="hotel_form_check_out")
            with departure_column:
                departure_time = st.selectbox(
                    "Departure time", HOTEL_TIMES, index=HOTEL_TIMES.index("11:00"),
                    key="hotel_form_departure_time",
                )

            if st.button("Add hotel"):
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
                        "arrival_time": arrival_time, "departure_time": departure_time,
                        "hotel_id": selected_hotel,
                    }
                    for existing in hotels:
                        if check_in < existing["check_out"] and existing["check_in"] < check_out:
                            raise ValueError(
                                f"These dates overlap with {existing['name']} "
                                f"({existing['check_in']} to {existing['check_out']})."
                            )
                    hotels.append(new_hotel)
                    save_saved_hotels([Hotel(**hotel) for hotel in hotels])
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
                        f"{hotel['check_in']} {hotel.get('arrival_time', '15:00')} to "
                        f"{hotel['check_out']} {hotel.get('departure_time', '11:00')}"
                    )
                    if right.button("Remove", key=f"remove_hotel_{index}"):
                        hotels.pop(index)
                        save_saved_hotels([Hotel(**hotel) for hotel in hotels])
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
    if st.button("Create trip", type="primary"):
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
            parsed = [Hotel(
                name=draft["name"],
                city=draft["city"],
                lat=draft["lat"],
                lng=draft["lng"],
                check_in=draft["check_in"],
                check_out=draft["check_out"],
                arrival_time=draft.get("arrival_time", "15:00"),
                departure_time=draft.get("departure_time", "11:00"),
            ) for draft in hotels]
            itinerary = create_trip(parsed, list(interests), pace)
            save_saved_hotels(parsed)
            st.session_state.interests = list(interests)
            st.session_state.pace = pace
            st.success(f"Created a {len(itinerary.hotels)}-hotel trip. Planning it now...")
            result = _run_turn(
                "Plan my whole trip now. Use find_places for each hotel and date range, "
                "check the proposed days, and save the planned stops with save_itinerary. "
                "Do not ask me to repeat the hotel or trip details; they are already in the context.",
                {"action": "create_trip", "interests": list(interests), "pace": pace},
            )
            st.session_state.trip_ready_for_next = result.status != "failed"
        except (ValueError, TypeError) as exc:
            st.error(f"Trip details are invalid: {exc}")
    has_saved_trip = load_itinerary() is not None
    if hotels and (st.session_state.get("trip_ready_for_next") or has_saved_trip):
        st.success("Your saved trip is ready to review.")
        if st.button("Next: Review itinerary", type="primary"):
            _go_to_step(2)


def _editor():
    itinerary = load_itinerary()
    if itinerary is None:
        st.info("Create a trip to edit its itinerary.")
        return
    st.header("Step 2 → Review your itinerary")
    if itinerary.approved:
        st.success("Approved itinerary — all stops are locked. Select “Unlock itinerary” below if you need to make changes.")
    places = load_places()
    names = {place.name: place_id for place_id, place in places.items()}
    days = sorted({stop.date for stop in itinerary.stops})
    if not days:
        st.info("The trip has been created, but no activities have been saved yet.")
        if st.button("Plan itinerary now", type="primary"):
            _run_turn(
                "Plan my whole trip now. Use find_places for each hotel and date range, "
                "check the proposed days, and save the planned stops with save_itinerary. "
                "Do not ask me to repeat the hotel or trip details; they are already in the context.",
                {"action": "plan_itinerary"},
            )
            st.rerun()
        return
    day_tabs = st.tabs([day.isoformat() for day in days])
    for day, day_tab in zip(days, day_tabs):
        day_stops = sorted((stop for stop in itinerary.stops if stop.date == day), key=lambda stop: stop.start)
        with day_tab:
            rows = [{
                "Time": stop.start,
                "Place": places[stop.place_id].name if stop.place_id in places else stop.place_id,
                "Reason": stop.reason,
                "Flags": "WARNING: " + "; ".join(stop.flags) if stop.flags else "",
                "Locked": itinerary.approved or stop.locked,
                "Remove": False,
            } for stop in day_stops]
            edited = st.data_editor(
                rows, key=f"day_editor_{day.isoformat()}", hide_index=True, num_rows="fixed",
                column_config={
                    "Time": st.column_config.TextColumn("Time (HH:MM)"),
                    "Place": st.column_config.SelectboxColumn("Place", options=sorted(names), required=True),
                    "Flags": st.column_config.TextColumn("Flags (warning)", disabled=True),
                    "Locked": st.column_config.CheckboxColumn("Locked", disabled=True),
                    "Remove": st.column_config.CheckboxColumn("Remove", disabled=itinerary.approved),
                },
                disabled=itinerary.approved,
            )
            if any(row["Flags"] for row in rows):
                st.warning("This day has flagged stops. Review the warning text before saving.")
            st.session_state[f"edited_{day.isoformat()}"] = (
                edited if isinstance(edited, list) else edited.to_dict("records")
            )

    save_column, unlock_column = st.columns(2)
    if save_column.button("Save my edits", disabled=itinerary.approved):
        try:
            updated = []
            ui_edits = {}
            for day in sorted({stop.date for stop in itinerary.stops}):
                original = [stop for stop in itinerary.stops if stop.date == day]
                records = st.session_state.get(f"edited_{day.isoformat()}", [])
                ui_edits[day.isoformat()] = records
                for old, row in zip(original, records):
                    if row.get("Remove"):
                        if old.locked:
                            raise ValueError(f"Locked stop at {old.start} cannot be removed.")
                        continue
                    if old.locked and (row["Place"] != places[old.place_id].name or row["Time"] != old.start):
                        raise ValueError(f"Locked stop at {old.start} cannot be moved.")
                    updated.append(Stop(
                        place_id=names.get(row["Place"], row["Place"]), date=day,
                        start=str(row["Time"]), reason=str(row["Reason"]),
                        locked=old.locked,
                    ))
            checked = check_itinerary(itinerary.model_copy(update={
                "stops": updated, "approved": False, "revision_note": "Saved UI edits.",
            }), places)
            save_itinerary_data(checked)
            st.success("Edits saved and checked without a model call.")
            st.rerun()
        except (ValueError, TypeError, KeyError) as exc:
            st.error(f"Could not save edits: {exc}")
    if unlock_column.button("Unlock itinerary", disabled=not itinerary.approved):
        unlocked_stops = [stop.model_copy(update={"locked": False}) for stop in itinerary.stops]
        save_itinerary_data(itinerary.model_copy(update={"approved": False, "stops": unlocked_stops}))
        st.success("Itinerary unlocked. You can now edit or remove stops.")
        st.rerun()

    st.subheader("Optional re-planning request")
    st.caption("Use this to change unlocked activities, for example: “add more cafés” or “make the evenings quieter.”")
    extra = st.text_input("What would you like to change?", key="replan_wishes",
                          disabled=itinerary.approved)
    if st.button("Re-plan unlocked stops", disabled=itinerary.approved):
        prompt = "I edited the itinerary. Re-plan only the unlocked stops."
        if extra.strip():
            prompt += f" Extra wishes: {extra.strip()}"
        _run_turn(prompt, {"action": "replan_unlocked", "extra_wishes": extra})
        st.rerun()
    _step_navigation(previous_step=1, next_step=3, next_label="Next: Chat with your agent →")


def _chat():
    with st.popover("💬 Chat with your itinerary agent"):
        st.caption("Choose what you want help with, then tell the agent what you need.")
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
        prompt = st.text_input(
            "Message",
            placeholder=prompts.get(chat_mode, "Choose an option above to start chatting"),
            key="chat_prompt",
        )
        if st.button("Send", type="primary", disabled=not chat_mode or not prompt.strip()):
            if chat_mode == "Request itinerary changes":
                prompt = f"Please update my itinerary as follows: {prompt}"
            elif chat_mode == "Add a preference":
                prompt = f"Please consider this lasting preference and propose it for memory approval: {prompt}"
            with st.chat_message("user"):
                st.write(prompt)
            with st.chat_message("assistant"):
                _run_turn(prompt, {"action": "chat", "prompt": prompt})
            st.rerun()


def _memories():
    memories = load_memories()
    pending = [memory for memory in memories if memory["status"] == "pending"]
    approved = [memory for memory in memories if memory["status"] == "approved"]
    if not pending and not approved:
        return
    st.header("Memory approvals")
    st.caption("The agent may suggest remembering a lasting preference. Approve only preferences you want used in future planning.")
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
        if right.button("Delete", key=f"delete_{memory['id']}"):
            save_memories([item for item in memories if item["id"] != memory["id"]])
            st.rerun()


def _approve_export():
    st.header("Approve and export")
    itinerary = load_itinerary()
    if itinerary is None:
        st.info("Create a trip first.")
        return
    if st.button("Approve itinerary", disabled=itinerary.approved):
        locked_stops = [stop.model_copy(update={"locked": True}) for stop in itinerary.stops]
        save_itinerary_data(itinerary.model_copy(update={"approved": True, "stops": locked_stops}))
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
        st.subheader("Itinerary planning has never been this easy.")
    _profile_selector(profile_column)
    _session()
    current_step = st.session_state.get("current_step", 1)
    if current_step == 1:
        _trip_setup()
    elif current_step == 2:
        _editor()
    elif current_step == 3:
        st.header("Step 3 → Chat with your itinerary agent")
        st.caption("Ask questions, request itinerary changes, or add a lasting preference.")
        _chat()
        _step_navigation(previous_step=2, next_step=4, next_label="Next: Memory approvals →")
    elif current_step == 4:
        st.header("Step 4 → Memory approvals")
        _memories()
        _step_navigation(previous_step=3, next_step=5, next_label="Next: Approve and export →")
    else:
        st.header("Step 5 → Approve and export")
        _approve_export()
        _step_navigation(previous_step=4)


if __name__ == "__main__":
    main()
