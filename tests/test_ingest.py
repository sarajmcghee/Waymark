from app.ingest import _coerce_multiline, _insert_feature, _length_meters


class RecordingConnection:
    def __init__(self):
        self.sql = ""
        self.params = {}

    def execute(self, sql, params):
        self.sql = sql
        self.params = params


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


def test_insert_feature_computes_missing_length_from_geometry():
    conn = RecordingConnection()

    assert _insert_feature(
        conn,
        source="test",
        source_url=None,
        feature={
            "type": "Feature",
            "id": "123",
            "geometry": {
                "type": "LineString",
                "coordinates": [[-86.8, 36.1], [-86.7, 36.2]],
            },
            "properties": {},
        },
    )

    assert "ST_Length" in conn.sql
    assert conn.params["length_meters"] is None


def test_insert_feature_records_route_grouping_fields():
    conn = RecordingConnection()

    _insert_feature(
        conn,
        source="test",
        source_url=None,
        feature={
            "type": "Feature",
            "id": "456",
            "geometry": {
                "type": "LineString",
                "coordinates": [[-86.8, 36.1], [-86.7, 36.2]],
            },
            "properties": {
                "is_route_segment": True,
                "route_relation_ids": ["789"],
            },
        },
    )

    assert conn.params["is_route_segment"] is True
    assert conn.params["route_relation_ids"] == ["789"]
