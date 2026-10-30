from datetime import date

from itinerary import Hotel, Itinerary, OpeningHours, Place, Stop, check_itinerary, parse_coordinates


MONDAY = date(2026, 10, 19)


def opening_hours(open_time="09:00", close_time="18:00"):
    return {
        weekday: OpeningHours(open=open_time, close=close_time)
        for weekday in ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
    }


def make_place(place_id, *, lat=1.0, lng=103.0, visit_minutes=60, hours=None):
    return Place(
        id=place_id,
        name=place_id.title(),
        city="Johor Bahru",
        area="Test area",
        lat=lat,
        lng=lng,
        tags=["nature"],
        hours=hours or opening_hours(),
        visit_minutes=visit_minutes,
        description="Test place.",
    )


def make_itinerary(stops, *, pace="relaxed"):
    return Itinerary(
        hotels=[Hotel(
            name="Test hotel",
            city="Johor Bahru",
            lat=1.0,
            lng=103.0,
            check_in=date(2026, 10, 18),
            check_out=date(2026, 10, 21),
        )],
        interests=["nature"],
        pace=pace,
        stops=stops,
        revision_note="Test",
    )


def flags_for(result, place_id):
    return next(stop for stop in result.stops if stop.place_id == place_id).flags


def test_flags_far_closed_outside_hours_and_unknown_place():
    closed_hours = opening_hours()
    closed_hours["mon"] = None
    places = {
        "far": make_place("far", lat=1.2, visit_minutes=60),
        "closed": make_place("closed", hours=closed_hours),
        "late": make_place("late", visit_minutes=120),
    }
    itinerary = make_itinerary([
        Stop(place_id="far", date=MONDAY, start="10:00", reason="Far stop"),
        Stop(place_id="closed", date=MONDAY, start="12:00", reason="Closed stop"),
        Stop(place_id="late", date=MONDAY, start="17:00", reason="Late stop"),
        Stop(place_id="missing", date=MONDAY, start="14:00", reason="Unknown stop"),
    ])

    checked = check_itinerary(itinerary, places)

    assert any(flag.startswith("Far from hotel (") for flag in flags_for(checked, "far"))
    assert flags_for(checked, "closed") == ["Closed on Monday"]
    assert flags_for(checked, "late") == [
        "Outside opening hours (opens 09:00, closes 18:00)",
    ]
    assert flags_for(checked, "missing") == ["Not in dataset"]


def test_flags_overlap_using_visit_and_travel_time():
    places = {
        "first": make_place("first", visit_minutes=120),
        "second": make_place("second", lat=1.01, visit_minutes=60),
    }
    itinerary = make_itinerary([
        Stop(place_id="first", date=MONDAY, start="09:00", reason="First stop"),
        Stop(place_id="second", date=MONDAY, start="10:00", reason="Second stop"),
    ])

    checked = check_itinerary(itinerary, places)

    assert "Overlaps previous stop" in flags_for(checked, "second")


def test_flags_every_stop_when_relaxed_day_is_too_packed():
    places = {
        "first": make_place("first", visit_minutes=200),
        "second": make_place("second", visit_minutes=200),
    }
    itinerary = make_itinerary([
        Stop(place_id="first", date=MONDAY, start="09:00", reason="First stop"),
        Stop(place_id="second", date=MONDAY, start="14:00", reason="Second stop"),
    ])

    checked = check_itinerary(itinerary, places)

    assert "Day too packed" in flags_for(checked, "first")
    assert "Day too packed" in flags_for(checked, "second")


def test_check_returns_copy_and_clears_stale_flags():
    place = make_place("park")
    itinerary = make_itinerary([
        Stop(
            place_id="park",
            date=MONDAY,
            start="10:00",
            reason="Park stop",
            flags=["old flag"],
        ),
    ])

    checked = check_itinerary(itinerary, {"park": place})

    assert checked is not itinerary
    assert itinerary.stops[0].flags == ["old flag"]
    assert checked.stops[0].flags == []


def test_parse_coordinates_accepts_google_maps_format():
    assert parse_coordinates(" 1.4655,   103.7578 ") == (1.4655, 103.7578)
    assert parse_coordinates("1.4655,103.7578") == (1.4655, 103.7578)


def test_parse_coordinates_rejects_invalid_values():
    for text in ("1.4655", "north, 103.7578", "91, 103.7578", "1.4655, 181"):
        try:
            parse_coordinates(text)
        except ValueError:
            pass
        else:
            raise AssertionError(f"Expected invalid coordinates: {text}")


def test_hotel_times_default_to_standard_check_in_and_check_out():
    hotel = Hotel(
        name="Test hotel",
        city="Johor Bahru",
        lat=1.0,
        lng=103.0,
        check_in=date(2026, 10, 18),
        check_out=date(2026, 10, 19),
    )

    assert hotel.arrival_time == "15:00"
    assert hotel.departure_time == "11:00"


def test_hotel_times_use_half_hour_increments():
    try:
        Hotel(
            name="Test hotel",
            city="Johor Bahru",
            lat=1.0,
            lng=103.0,
            check_in=date(2026, 10, 18),
            check_out=date(2026, 10, 19),
            arrival_time="15:15",
        )
    except ValueError:
        pass
    else:
        raise AssertionError("Expected hotel arrival time to use a 30-minute increment")


def test_overnight_hours_allow_late_evening_visit():
    hours = opening_hours()
    hours["fri"] = OpeningHours(open="17:00", close="03:00")
    place = make_place("night-market", hours=hours)
    itinerary = make_itinerary([
        Stop(place_id="night-market", date=date(2026, 10, 23), start="23:00", reason="Night visit"),
    ])

    assert flags_for(check_itinerary(itinerary, {"night-market": place}), "night-market") == []


def test_overnight_hours_allow_previous_day_after_midnight_visit():
    hours = opening_hours()
    hours["fri"] = OpeningHours(open="10:00", close="01:00")
    hours["sat"] = None
    place = make_place("late-place", hours=hours)
    itinerary = make_itinerary([
        Stop(place_id="late-place", date=date(2026, 10, 24), start="01:30", reason="Late visit"),
    ])

    assert flags_for(check_itinerary(itinerary, {"late-place": place}), "late-place") == []


def test_overnight_hours_flag_visit_after_close():
    hours = opening_hours()
    hours["fri"] = OpeningHours(open="17:00", close="03:00")
    place = make_place("night-market", hours=hours)
    itinerary = make_itinerary([
        Stop(place_id="night-market", date=date(2026, 10, 23), start="04:00", reason="Too late"),
    ])

    assert flags_for(check_itinerary(itinerary, {"night-market": place}), "night-market") == [
        "Outside opening hours (opens 17:00, closes 03:00)",
    ]


def test_normal_daytime_hours_still_work():
    place = make_place("day-place")
    itinerary = make_itinerary([
        Stop(place_id="day-place", date=MONDAY, start="10:00", reason="Day visit"),
    ])

    assert flags_for(check_itinerary(itinerary, {"day-place": place}), "day-place") == []
