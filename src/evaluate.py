"""Live evaluation runner for the itinerary planning agent."""

import argparse
import csv
from datetime import date
import json
from pathlib import Path
import shutil

import agent as agent_module
from file_access import files
from itinerary import (
    Hotel,
    Stop,
    check_itinerary,
    day_duration_minutes,
    day_plan,
    haversine_km,
    load_itinerary,
    load_places,
    load_known_hotels,
    create_trip,
    save_itinerary_data,
    trip_dates,
)
from lab_support import open_lab


ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
EVAL_ROOT = ROOT / "runtime" / "eval"
RUNS_ROOT = EVAL_ROOT / "runs"
ITINERARIES_ROOT = EVAL_ROOT / "itineraries"


def _read_trips():
    return json.loads((DATA / "eval_trips.json").read_text(encoding="utf-8"))


def _hotels(trip):
    known = {hotel.id: hotel for hotel in load_known_hotels()}
    return [
        Hotel(
            name=known[item["id"]].name,
            city=known[item["id"]].city,
            lat=known[item["id"]].lat,
            lng=known[item["id"]].lng,
            check_in=date.fromisoformat(item["check_in"]),
            check_out=date.fromisoformat(item["check_out"]),
        )
        for item in trip["hotels"]
    ]


def _copy_workspace(lab, name):
    root = lab.root / "runtime" / "eval-workspaces" / name
    if root.exists():
        shutil.rmtree(root)
    shutil.copytree(lab.root / "data", root / "data")
    return root


def _save_result(result, trip_name, condition, step, number):
    RUNS_ROOT.mkdir(parents=True, exist_ok=True)
    path = RUNS_ROOT / f"{trip_name}-{condition}-{number:02d}-{step}.json"
    path.write_text(json.dumps(result.to_dict(), indent=2) + "\n", encoding="utf-8")


def _save_itinerary_record(trip_name, condition, initial, final, results):
    ITINERARIES_ROOT.mkdir(parents=True, exist_ok=True)
    path = ITINERARIES_ROOT / f"{trip_name}-{condition}.json"
    path.write_text(json.dumps({
        "initial": initial,
        "final": final,
        "run_statuses": [result.status for result in results],
    }, indent=2) + "\n", encoding="utf-8")


def _itinerary_snapshot(itinerary, places):
    return {
        "hotels": [hotel.model_dump(mode="json") for hotel in itinerary.hotels],
        "pace": itinerary.pace,
        "interests": itinerary.interests,
        "stops": [
            {
                **stop.model_dump(mode="json"),
                "name": places[stop.place_id].name if stop.place_id in places else stop.place_id,
            }
            for stop in itinerary.stops
        ],
        "day_flags": itinerary.day_flags,
    }


def _run_turn(session, trip_name, condition, step, text, number):
    result = session.run(text)
    _save_result(result, trip_name, condition, step, number)
    return result


def _day_prompt(plan, pace):
    if plan["day_type"] == "full":
        target = "Target 4-6h of visits and travel." if pace == "relaxed" else "Target 7-9h of visits and travel."
    else:
        target = "Plan within the available hotel check-in, transfer, or check-out window; do not target a minimum number of stops."
    windows = ", ".join(window["start"] + "-" + window["end"] for window in plan["windows"])
    return (
        f"Plan {plan['date'].isoformat()} ({plan['weekday']}); Keep locked stops. "
        f"{target} Available hotel windows: {windows}. "
        "Plan only this date, use the date parameter when saving, and call check_day before saving."
    )


def _plant_problems(itinerary, places):
    plans = day_plan(itinerary)
    full_day = next(plan for plan in plans if plan["day_type"] == "full")
    weekday = full_day["date"].weekday()
    closed = next(
        place for place in places.values()
        if place.hours[("mon", "tue", "wed", "thu", "fri", "sat", "sun")[weekday]] is None
    )
    hotel = full_day["hotel"]
    far = next(
        place for place in places.values()
        if haversine_km(place.lat, place.lng, hotel.lat, hotel.lng) > 15
    )
    additions = [
        Stop(place_id=closed.id, date=full_day["date"], start="10:00", reason="Planted closed-day problem"),
        Stop(place_id=far.id, date=full_day["date"], start="12:00", reason="Planted distance problem"),
    ]
    checked = check_itinerary(itinerary.model_copy(update={"stops": itinerary.stops + additions}), places)
    return sum(bool(stop.flags) for stop in checked.stops[-2:]), checked


def _pace_metrics(itinerary, places):
    plans = day_plan(itinerary)
    full = [plan for plan in plans if plan["day_type"] == "full"]
    within = 0
    for plan in full:
        minutes = day_duration_minutes(
            [stop for stop in itinerary.stops if stop.date == plan["date"]], places, plan
        )
        target = {"relaxed": (240, 360), "packed": (420, 540)}[itinerary.pace]
        within += target[0] <= minutes <= target[1]
    return len(plans), (within / len(full) * 100 if full else 100)


def _evaluate_trial(lab, trip_name, trip, condition, memory_enabled):
    workspace = _copy_workspace(lab, f"{trip_name}-{condition}")
    session = lab.session(root=workspace)
    agent_module.USE_MEMORY = memory_enabled
    places = load_places()
    hotels = _hotels(trip)
    with files.use(session.files):
        itinerary = create_trip(hotels, trip["interests"], trip["pace"])
        if memory_enabled:
            memory_path = workspace / "runtime" / "memories.json"
            memory_path.parent.mkdir(parents=True, exist_ok=True)
            memory_path.write_text(json.dumps([{
                "id": "eval-memory",
                "preference": "Avoid high-altitude attractions (cable cars, skywalks)",
                "evidence": "Approved evaluation preference",
                "status": "approved",
            }], indent=2) + "\n", encoding="utf-8")
        results = []
        number = 0
        for plan in day_plan(itinerary):
            number += 1
            results.append(_run_turn(
                session, trip_name, condition, "plan", _day_prompt(plan, itinerary.pace), number
            ))
        planned = load_itinerary()
        if planned is None:
            raise RuntimeError("Planning produced no itinerary.")
        itinerary_snapshot = _itinerary_snapshot(planned, places)
        full = next(
            plan for plan in day_plan(planned)
            if plan["day_type"] == "full"
            and sum(stop.date == plan["date"] for stop in planned.stops) >= 2
        )
        full_stops = [stop for stop in planned.stops if stop.date == full["date"]]
        locked = full_stops[:2]
        locked_keys = {(stop.place_id, stop.start) for stop in locked}
        locked_itinerary = planned.model_copy(update={
            "stops": [
                stop.model_copy(update={"locked": (stop.place_id, stop.start) in locked_keys})
                for stop in planned.stops
            ]
        })
        save_itinerary_data(locked_itinerary)
        lock_result = _run_turn(
            session, trip_name, condition, "lock",
            f"Re-plan only the unlocked stops on {full['date'].isoformat()}", number + 1
        )
        after_lock = load_itinerary()
        kept = sum(
            any(stop.place_id == old.place_id and stop.start == old.start and stop.locked
                for stop in after_lock.stops)
            for old in locked
        )
        refusals = sum(
            event.get("type") == "tool_failed"
            and event.get("tool") == "save_itinerary"
            and "Locked stop" in str(event.get("result", {}))
            for event in lock_result.events
        )
        planted_count, planted = _plant_problems(after_lock, places)
        chat_plan = next(
            plan for plan in day_plan(after_lock)
            if plan["day_type"] == "full"
            and any(
                stop.date == plan["date"] and not stop.locked
                for stop in after_lock.stops
            )
        )
        chat_date = chat_plan["date"].isoformat()
        chat_before = _itinerary_snapshot(after_lock, places)
        chat_place = next(
            stop for stop in after_lock.stops
            if stop.date == chat_plan["date"] and not stop.locked
        )
        chat_place_name = places[chat_place.place_id].name
        chat_result = _run_turn(
            session, trip_name, condition, "chat",
            f"on {chat_date} skip {chat_place_name}, plan something else", number + 2
        )
        after_chat = load_itinerary()
        changed_dates = {
            day for day in trip_dates(after_lock.hotels, after_lock.stops)
            if [s.model_dump() for s in after_lock.stops if s.date == day]
            != [s.model_dump() for s in after_chat.stops if s.date == day]
        }
        chat_ok = changed_dates <= {chat_plan["date"]} and all(
            stop.place_id != chat_place.place_id
            for stop in after_chat.stops if stop.date == chat_plan["date"]
        )
        locked_chat_place = locked[0]
        locked_chat_date = locked_chat_place.date.isoformat()
        locked_chat_name = places[locked_chat_place.place_id].name
        locked_chat_result = _run_turn(
            session, trip_name, condition, "chat-locked",
            f"on {locked_chat_date} skip {locked_chat_name}, plan something else", number + 3
        )
        chat_locked_refused = any(
            event.get("type") == "tool_failed"
            and event.get("tool") == "save_itinerary"
            and "Locked stop" in str(event.get("result", {}))
            for event in locked_chat_result.events
        ) or (
            "locked" in locked_chat_result.answer.casefold()
            and any(word in locked_chat_result.answer.casefold()
                    for word in ("can't", "cannot", "unable", "unlock"))
        )
        all_results = results + [lock_result, chat_result, locked_chat_result]
        failures = sum(result.status != "completed" for result in all_results)
        tool_errors = sum(
            event.get("type") == "tool_failed"
            for result in all_results for event in result.events
        )
        cost = sum(
            result.usage.get("cost_usd") or 0
            for result in all_results
        )
        final = check_itinerary(after_chat, places)
        _save_itinerary_record(
            trip_name,
            condition,
            itinerary_snapshot,
            _itinerary_snapshot(final, places),
            all_results,
        )
        days, pace_percent = _pace_metrics(final, places)
        no_flags = sum(not stop.flags for stop in final.stops)
        memory_violations = sum(
            "skyway" in places[stop.place_id].name.casefold()
            or "cable car" in places[stop.place_id].name.casefold()
            for stop in planned.stops
        ) if memory_enabled else 0
        return {
            "trip": trip_name,
            "condition": condition,
            "days_planned": days if failures == 0 else days - sum(
                result.status != "completed" for result in results
            ),
            "stops_no_flags_percent": round(no_flags / len(final.stops) * 100, 1) if final.stops else 100.0,
            "days_within_pace_percent": round(pace_percent, 1),
            "locked_stops_kept_percent": round(kept / len(locked) * 100, 1),
            "lock_refusals": refusals,
            "planted_problems_flagged": f"{planted_count}/2",
            "chat_date_correct": "yes" if chat_ok else "no",
            "chat_locked_refused": "yes" if chat_locked_refused else "no",
            "memory_violations": memory_violations,
            "failed_runs": failures,
            "tool_errors": tool_errors,
            "cost_usd": round(cost, 6),
            "itinerary": itinerary_snapshot,
            "planted_check": _itinerary_snapshot(planted, places),
            "chat_status": chat_result.status,
            "chat_answer": chat_result.answer,
            "chat_before": chat_before,
        }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--trip", choices=sorted(_read_trips()), help="Run one trip only.")
    args = parser.parse_args()
    trips = _read_trips()
    selected = [args.trip] if args.trip else list(trips)
    EVAL_ROOT.mkdir(parents=True, exist_ok=True)
    rows = []
    with open_lab() as lab:
        for name in selected:
            conditions = [("memory-off", False), ("memory-on", True)] if name == "december" else [("baseline", True)]
            for condition, memory_enabled in conditions:
                rows.append(_evaluate_trial(lab, name, trips[name], condition, memory_enabled))
    fields = [
        "trip", "condition", "days_planned", "stops_no_flags_percent",
        "days_within_pace_percent", "locked_stops_kept_percent", "lock_refusals",
        "planted_problems_flagged", "chat_date_correct", "chat_locked_refused",
        "memory_violations",
        "failed_runs", "tool_errors", "cost_usd",
    ]
    with (EVAL_ROOT / "results.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows({field: row[field] for field in fields} for row in rows)
    print("\n".join([
        "trip condition days stops_no_flags% pace_days% locked% refusals planted chat chat_locked memory failed tools cost",
        *[
            f"{row['trip']} {row['condition']} {row['days_planned']} "
            f"{row['stops_no_flags_percent']} {row['days_within_pace_percent']} "
            f"{row['locked_stops_kept_percent']} {row['lock_refusals']} "
            f"{row['planted_problems_flagged']} {row['chat_date_correct']} "
            f"{row['chat_locked_refused']} "
            f"{row['memory_violations']} {row['failed_runs']} {row['tool_errors']} "
            f"{row['cost_usd']}"
            for row in rows
        ]
    ]))


if __name__ == "__main__":
    main()
