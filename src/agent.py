"""Itinerary planning agent entry point."""

from agents import Agent, Runner

from itinerary import load_itinerary, load_memories, load_places
from tools import check_day, find_places, propose_memory, save_itinerary


USE_MEMORY = True

INSTRUCTIONS = """You are an itinerary planning assistant.
Plan day-by-day itineraries around the traveler's booked hotels, interests, and pace.
Interest tags may include history, nature, food, shopping, animals, culture,
nightlife, tech, home_decor, wellness, fruits, theme_park, family, and cafe.
Only suggest places returned by find_places. Never invent places, opening hours, or
distances. Give every stop a short reason that names the matching interest, distance
from that night's hotel, and opening time, such as "Cat cafe: you chose animals,
10 minutes from your Johor Bahru hotel, open until 8pm".
Use check_day before save_itinerary. Fix flagged stops when a better option exists;
if a flag cannot be fixed, keep it and explain why. Never change, move, or remove
locked stops. When re-planning, change only unlocked stops.
Treat hotel arrival and departure times as hard boundaries: do not schedule
activities before arrival on check-in day or after departure on check-out day.
When the user's edits or answers reveal a lasting preference, call propose_memory and
tell the user to approve or reject it. Never claim a memory is saved before approval.
Use approved preferences when relevant and mention them in reasons, for example
"(you prefer outdoor activities)".
End each turn with a short summary of what changed and any flagged stops.
"""

TOOLS = [find_places, check_day, save_itinerary, propose_memory]


def create_agent(model):
    """Instantiate the itinerary agent with its model, instructions, and tools."""
    return Agent(
        name="Itinerary planning assistant",
        model=model,
        instructions=INSTRUCTIONS,
        tools=TOOLS,
    )


def _context_text():
    itinerary = load_itinerary()
    places = load_places()
    lines = [
        "[Context]",
        "This is the latest itinerary context; the user may have edited it in the interface since the last turn.",
    ]
    if itinerary is None:
        lines.append("No trip has been created yet.")
    else:
        lines.extend([
            f"Pace: {itinerary.pace}; interests: {', '.join(itinerary.interests) or 'none'}",
            "Booked hotels:",
        ])
        for hotel in itinerary.hotels:
            lines.append(
                f"- {hotel.name} in {hotel.city}: "
                f"check-in {hotel.check_in.isoformat()}, "
                f"{hotel.arrival_time}; check-out {hotel.check_out.isoformat()}, "
                f"{hotel.departure_time}"
            )
        lines.extend([
            "Itinerary:",
        ])
        for day in sorted({stop.date for stop in itinerary.stops}):
            lines.append(f"{day.isoformat()}:")
            day_stops = sorted(
                (stop for stop in itinerary.stops if stop.date == day),
                key=lambda stop: stop.start,
            )
            for stop in day_stops:
                place_name = places.get(stop.place_id)
                name = place_name.name if place_name else stop.place_id
                lock = " LOCKED" if stop.locked else ""
                flags = f"; flags: {', '.join(stop.flags)}" if stop.flags else ""
                lines.append(f"- {stop.start} {name}{lock}: {stop.reason}{flags}")
        if not itinerary.stops:
            lines.append("- No stops planned.")
    if USE_MEMORY:
        approved = [memory for memory in load_memories()
                    if memory.get("status") == "approved"]
        lines.append("Approved preferences:")
        if approved:
            lines.extend(f"- {memory['preference']} (evidence: {memory['evidence']})"
                         for memory in approved)
        else:
            lines.append("- None")
    else:
        lines.append("Approved preferences: disabled for this evaluation.")
    return "\n".join(lines)


def prepare_input(history, user_input, _files):
    """Provide the latest itinerary and approved memories before the user request."""
    _ = _files
    context = {"role": "user", "content": _context_text()}
    return history + [context, {"role": "user", "content": user_input}]


def run_agent(agent, messages, run_config=None):
    """Run the model/tool loop once for the user's message and earlier history."""
    return Runner.run_sync(agent, messages, max_turns=12, run_config=run_config)


if __name__ == "__main__":
    from lab_support._runtime import main
    raise SystemExit(main(agent_factory=create_agent, runner=run_agent))
