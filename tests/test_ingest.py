from app.ingest import _coerce_multiline, _length_meters


def test_coerce_linestring_to_multilinestring():
    geometry = {
        "type": "LineString",
        "coordinates": [[-83.5, 35.6], [-83.4, 35.7]],
    }

    assert _coerce_multiline(geometry) == {
        "type": "MultiLineString",
        "coordinates": [[[-83.5, 35.6], [-83.4, 35.7]]],
    }


def test_accept_multilinestring():
    geometry = {
        "type": "MultiLineString",
        "coordinates": [[[-83.5, 35.6], [-83.4, 35.7]]],
    }

    assert _coerce_multiline(geometry) == geometry


def test_reject_non_line_geometry():
    assert _coerce_multiline({"type": "Point", "coordinates": [-83.5, 35.6]}) is None


def test_length_meters_converts_common_units():
    assert _length_meters({"miles": "2"}) == 3218.688
    assert _length_meters({"length_km": "3.5"}) == 3500
