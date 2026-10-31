"""Tools exposed to the itinerary planning agent."""

import uuid
from datetime import date as date_type

from agents import function_tool
from file_access import ToolError, text_arg
from pydantic import ValidationError
from itinerary import (
    Itinerary,
    Stop,
    check_itinerary,
    haversine_km,
    load_itinerary,
    load_memories,
    load_places,
    save_itinerary_data,
    save_memories,
)


def _current_itinerary() -> Itinerary:
    itinerary = load_itinerary()
    if itinerary is None:
        raise ToolError("Create a trip before planning stops.")
    return itinerary


@function_tool
def find_places(city: str, tags: list[str], near_hotel: str) -> list[dict]:
    """Find curated places matching interests, ordered by distance from a hotel."""
    text_arg(city, "city", 40)
    if not isinstance(tags, list) or not all(isinstance(tag, str) for tag in tags):
        raise ToolError("tags must be a list of strings.")
    text_arg(near_hotel, "near_hotel", 120)
    itinerary = _current_itinerary()
    hotel = next((hotel for hotel in itinerary.hotels
                  if hotel.name.casefold() == near_hotel.casefold() and hotel.city == city), None)
    if hotel is None:
        raise ToolError(f"Hotel {near_hotel} in {city} is not in the current trip.")
    wanted = {tag.casefold() for tag in tags}
    results = []
    for place in load_places().values():
        if place.city != city or wanted.isdisjoint(tag.casefold() for tag in place.tags):
            continue
        distance = haversine_km(hotel.lat, hotel.lng, place.lat, place.lng)
        results.append({
            "id": place.id, "name": place.name, "area": place.area, "tags": place.tags,
            "distance_km": round(distance, 1), "hours": {
                day: hours.model_dump() if hours else None for day, hours in place.hours.items()
            }, "visit_minutes": place.visit_minutes, "description": place.description,
        })
    return sorted(results, key=lambda item: item["distance_km"])[:10]


@function_tool
def check_day(stops: list[Stop]) -> list[dict]:
    """Check proposed stops using the saved trip's hotels and pace."""
    itinerary = _current_itinerary()
    try:
        proposed = itinerary.model_copy(update={"stops": stops})
        checked = check_itinerary(proposed, load_places())
    except (TypeError, ValueError):
        raise ToolError("Each stop must include a valid place_id, date, start, and reason.") from None
    return [stop.model_dump(mode="json") for stop in checked.stops]


@function_tool
def save_itinerary(stops: list[Stop], revision_note: str, date: str | None = None) -> dict:
    """Save a checked itinerary while preserving every locked stop."""
    text_arg(revision_note, "revision_note", 600)
    itinerary = _current_itinerary()
    places = load_places()
    target_date = None
    if date is not None:
        text_arg(date, "date", 10)
        try:
            target_date = date_type.fromisoformat(date)
        except ValueError:
            raise ToolError("date must be an ISO date in YYYY-MM-DD format.") from None
    try:
        proposed = [stop if isinstance(stop, Stop) else Stop.model_validate(stop) for stop in stops]
    except ValidationError:
        raise ToolError("Every stop must have a valid date, start time, reason, and lock state.") from None
    for stop in proposed:
        if stop.place_id not in places:
            raise ToolError(f"Place {stop.place_id} is not in the curated dataset.")
        if not stop.reason.strip():
            raise ToolError("Every stop needs a non-empty reason.")
    if target_date is not None:
        target_stops = [stop for stop in proposed if stop.date == target_date]
        current_locked = [stop for stop in itinerary.stops if stop.date == target_date and stop.locked]
        for locked in current_locked:
            changed = next((
                stop for stop in target_stops
                if stop.place_id == locked.place_id and stop.date == locked.date
                and stop.start != locked.start
            ), None)
            if changed is not None:
                name = places.get(locked.place_id)
                label = name.name if name else locked.place_id
                raise ToolError(f"Locked stop {label} on {locked.date} was changed or removed. Keep locked stops exactly as they are.")
        proposed = [
            stop for stop in itinerary.stops
            if stop.date != target_date and stop not in target_stops
        ] + [
            stop for stop in current_locked
        ] + [
            stop for stop in target_stops
            if not any(
                stop.place_id == locked.place_id
                and stop.date == locked.date
                and stop.start == locked.start
                for locked in current_locked
            )
        ]
    for locked in (stop for stop in itinerary.stops if stop.locked):
        matching = next((stop for stop in proposed
                         if stop.place_id == locked.place_id and stop.date == locked.date
                         and stop.start == locked.start), None)
        if matching is None:
            name = places.get(locked.place_id)
            label = name.name if name else locked.place_id
            raise ToolError(f"Locked stop {label} on {locked.date} was changed or removed. Keep locked stops exactly as they are.")
        matching.locked = True
    checked = check_itinerary(itinerary.model_copy(update={
        "stops": proposed, "approved": False, "revision_note": revision_note,
    }), places)
    result = save_itinerary_data(checked)
    minimum = 3 if itinerary.pace == "relaxed" else 5
    maximum = 4 if itinerary.pace == "relaxed" else 6
    warnings = []
    for day, flags in checked.day_flags.items():
        if target_date is not None and day != target_date.isoformat():
            continue
        if flags and flags[0].startswith("Light day"):
            count = sum(stop.date.isoformat() == day for stop in checked.stops)
            warnings.append(
                f"{day} has {count} stop{'s' if count != 1 else ''}; "
                f"{itinerary.pace} pace expects {minimum}-{maximum}"
            )
    return {
        **result,
        "stops": [stop.model_dump(mode="json") for stop in checked.stops],
        "flagged_stops": sum(bool(stop.flags) for stop in checked.stops),
        "warning": warnings[0] if warnings else None,
        "warnings": warnings,
    }


@function_tool
def propose_memory(preference: str, evidence: str) -> str:
    """Propose a preference for user approval; this tool cannot approve it."""
    text_arg(preference, "preference", 240)
    text_arg(evidence, "evidence", 500)
    memories = load_memories()
    memories.append({"id": uuid.uuid4().hex, "preference": preference.strip(),
                     "evidence": evidence.strip(), "status": "pending"})
    save_memories(memories)
    return "Proposed. The user will approve or reject it in the interface. Do not treat it as saved."
