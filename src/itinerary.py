"""Itinerary data models, persistence, verification, and calendar export."""

from datetime import date, datetime, timedelta
import json
import math
from pathlib import Path
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from file_access import ToolError, files
from lab_support.events import emit_event


CITY_NAMES = Literal["Johor Bahru", "Genting Highlands", "Kuala Lumpur"]
WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
TIME_PATTERN = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")


class OpeningHours(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    open: str
    close: str

    @field_validator("open", "close")
    @classmethod
    def valid_time(cls, value: str) -> str:
        if not isinstance(value, str) or not TIME_PATTERN.fullmatch(value):
            raise ValueError("time must use HH:MM")
        return value


class Place(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    id: str
    name: str
    city: CITY_NAMES
    area: str
    lat: float
    lng: float
    tags: list[str]
    hours: dict[str, OpeningHours | None]
    visit_minutes: int
    description: str

    @field_validator("hours")
    @classmethod
    def valid_hours(cls, value: dict[str, OpeningHours | None]) -> dict[str, OpeningHours | None]:
        if set(value) != set(WEEKDAYS):
            raise ValueError("hours must contain mon through sun")
        return value

    @field_validator("visit_minutes")
    @classmethod
    def positive_visit(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("visit_minutes must be positive")
        return value


class Hotel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    name: str
    city: CITY_NAMES
    lat: float
    lng: float
    check_in: date
    check_out: date

    @field_validator("check_out")
    @classmethod
    def after_check_in(cls, value: date, info) -> date:
        check_in = info.data.get("check_in")
        if check_in and value <= check_in:
            raise ValueError("check_out must be after check_in")
        return value


class Stop(BaseModel):
    model_config = ConfigDict(extra="forbid")
    place_id: str
    date: date
    start: str
    reason: str = Field(min_length=1, max_length=200)
    locked: bool = False
    flags: list[str] = Field(default_factory=list)

    @field_validator("start")
    @classmethod
    def valid_start(cls, value: str) -> str:
        if not TIME_PATTERN.fullmatch(value):
            raise ValueError("start must use HH:MM")
        return value


class Itinerary(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    hotels: list[Hotel]
    interests: list[str]
    pace: Literal["relaxed", "packed"]
    stops: list[Stop]
    approved: bool = False
    revision_note: str


def workspace_root() -> Path:
    """Return the active workspace root, including temporary test workspaces."""
    return files._workspace.root


def _json_path(name: str) -> Path:
    return workspace_root() / "runtime" / name


def _validate(model_type, data, message):
    try:
        return model_type.model_validate(data)
    except ValidationError:
        raise ToolError(message) from None


def load_places() -> dict[str, Place]:
    """Load and validate the curated place dataset."""
    path = workspace_root() / "data" / "places.json"
    if not path.is_file():
        raise ToolError("The curated data/places.json dataset is missing.")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, list):
            raise ValueError
        places = [_validate(Place, item, "A place in data/places.json is invalid.") for item in raw]
    except (OSError, ValueError, UnicodeError):
        raise ToolError("Could not read the curated places dataset.") from None
    result = {place.id: place for place in places}
    if len(result) != len(places):
        raise ToolError("Place IDs in data/places.json must be unique.")
    return result


def load_itinerary() -> Itinerary | None:
    """Load the saved itinerary, validating all persisted data."""
    path = _json_path("itinerary.json")
    if not path.exists():
        return None
    try:
        return Itinerary.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError, ValidationError):
        raise ToolError("Saved itinerary data is invalid.") from None


def _place_name(place_id: str, places: dict[str, Place]) -> str:
    return places[place_id].name if place_id in places else place_id


def itinerary_markdown(itinerary: Itinerary, places: dict[str, Place] | None = None) -> str:
    places = places or {}
    lines = ["# Itinerary", "", f"Pace: {itinerary.pace}", f"Approved: {itinerary.approved}",
             f"Revision: {itinerary.revision_note}", ""]
    for day in sorted({stop.date for stop in itinerary.stops}):
        lines.extend([f"## {day.isoformat()}", ""])
        for stop in sorted((s for s in itinerary.stops if s.date == day), key=lambda s: s.start):
            labels = []
            if stop.locked:
                labels.append("[LOCKED]")
            labels.extend(f"[{flag}]" for flag in stop.flags)
            suffix = " " + " ".join(labels) if labels else ""
            lines.append(f"- {stop.start} {_place_name(stop.place_id, places)}{suffix}: {stop.reason}")
        lines.append("")
    return "\n".join(lines)


def save_itinerary_data(itinerary: Itinerary) -> dict:
    """Validate and save JSON plus a readable Markdown view."""
    itinerary = _validate(Itinerary, itinerary.model_dump() if isinstance(itinerary, Itinerary) else itinerary,
                          "Itinerary data is invalid.")
    path = _json_path("itinerary.json")
    markdown_path = _json_path("itinerary.md")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(itinerary.model_dump(mode="json"), indent=2) + "\n", encoding="utf-8")
    markdown_path.write_text(itinerary_markdown(itinerary, load_places()), encoding="utf-8")
    emit_event("itinerary_changed", itinerary=itinerary.model_dump(mode="json"))
    return {"path": "runtime/itinerary.json", "markdown_path": "runtime/itinerary.md",
            "itinerary": itinerary.model_dump(mode="json")}


def load_memories() -> list[dict]:
    """Load memory proposals and decisions, returning an empty list if absent."""
    path = _json_path("memories.json")
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError):
        raise ToolError("Saved memories data is invalid.") from None
    if not isinstance(data, list):
        raise ToolError("Saved memories data is invalid.")
    for item in data:
        if not isinstance(item, dict) or not {"id", "preference", "evidence", "status"} <= item.keys():
            raise ToolError("Saved memories data is invalid.")
        if item["status"] not in {"pending", "approved", "rejected"}:
            raise ToolError("Saved memories data is invalid.")
    return data


def save_memories(memories: list[dict]) -> None:
    """Persist memory proposals and user decisions."""
    path = _json_path("memories.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(memories, indent=2) + "\n", encoding="utf-8")


def create_trip(hotels: list[Hotel], interests: list[str], pace: str) -> Itinerary:
    """Create and persist an empty trip before the agent plans stops."""
    itinerary = _validate(Itinerary, {
        "hotels": [hotel.model_dump() if isinstance(hotel, Hotel) else hotel for hotel in hotels],
        "interests": interests, "pace": pace, "stops": [], "approved": False,
        "revision_note": "Trip created; no stops planned yet.",
    }, "Trip details are invalid.")
    save_itinerary_data(itinerary)
    return itinerary


def _minutes(value: str) -> int:
    hours, minutes = value.split(":")
    return int(hours) * 60 + int(minutes)


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    radius = 6371.0
    lat_delta = math.radians(lat2 - lat1)
    lng_delta = math.radians(lng2 - lng1)
    a = (math.sin(lat_delta / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(lng_delta / 2) ** 2)
    return radius * 2 * math.asin(math.sqrt(a))


def _hotel_for(hotels: list[Hotel], day: date) -> Hotel | None:
    return next((hotel for hotel in hotels if hotel.check_in <= day < hotel.check_out), None)


def check_itinerary(itinerary: Itinerary, places: dict[str, Place]) -> Itinerary:
    """Return a copy with deterministic opening, distance, overlap, and pace flags."""
    stops = [stop.model_copy(update={"flags": []}) for stop in itinerary.stops]
    by_day: dict[date, list[Stop]] = {}
    for stop in stops:
        by_day.setdefault(stop.date, []).append(stop)
        place = places.get(stop.place_id)
        if place is None:
            stop.flags.append("Not in dataset")
            continue
        hotel = _hotel_for(itinerary.hotels, stop.date)
        if hotel is not None:
            distance = haversine_km(place.lat, place.lng, hotel.lat, hotel.lng)
            if distance > 15:
                stop.flags.append(f"Far from hotel ({distance:.1f} km)")
        hours = place.hours[WEEKDAYS[stop.date.weekday()]]
        end = _minutes(stop.start) + place.visit_minutes
        if hours is None:
            stop.flags.append(f"Closed on {stop.date.strftime('%A')}")
        elif _minutes(stop.start) < _minutes(hours.open) or end > _minutes(hours.close):
            stop.flags.append(f"Outside opening hours (opens {hours.open}, closes {hours.close})")
    for day_stops in by_day.values():
        ordered = sorted(day_stops, key=lambda stop: stop.start)
        total = 0
        previous = None
        for stop in ordered:
            place = places.get(stop.place_id)
            visit = place.visit_minutes if place else 0
            if previous is not None:
                prior_place = places.get(previous.place_id)
                if prior_place and place:
                    travel = round(haversine_km(prior_place.lat, prior_place.lng, place.lat, place.lng) / 25 * 60)
                    if _minutes(stop.start) < _minutes(previous.start) + prior_place.visit_minutes + travel:
                        stop.flags.append("Overlaps previous stop")
                    total += travel
            total += visit
            previous = stop
        threshold = 360 if itinerary.pace == "relaxed" else 600
        if total > threshold:
            for stop in day_stops:
                if "Day too packed" not in stop.flags:
                    stop.flags.append("Day too packed")
    return itinerary.model_copy(update={"stops": stops, "approved": False})


def export_ics(itinerary: Itinerary, places: dict[str, Place]) -> str:
    """Build a calendar file in Asia/Kuala_Lumpur local time."""
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Itinerary Planning Agent//EN"]
    for index, stop in enumerate(itinerary.stops, 1):
        place = places.get(stop.place_id)
        if place is None:
            continue
        start = datetime.combine(stop.date, datetime.strptime(stop.start, "%H:%M").time())
        end = start + timedelta(minutes=place.visit_minutes)
        lines.extend(["BEGIN:VEVENT", f"UID:{stop.date.isoformat()}-{index}@itinerary-agent",
                      f"DTSTART;TZID=Asia/Kuala_Lumpur:{start:%Y%m%dT%H%M%S}",
                      f"DTEND;TZID=Asia/Kuala_Lumpur:{end:%Y%m%dT%H%M%S}",
                      f"SUMMARY:{place.name}", f"DESCRIPTION:{stop.reason}",
                      f"LOCATION:{place.area}, {place.city}", "END:VEVENT"])
    lines.extend(["END:VCALENDAR", ""])
    return "\r\n".join(lines)
