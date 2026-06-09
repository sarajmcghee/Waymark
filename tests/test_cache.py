from app.cache import source_for_request
from scripts.import_geofabrik import state_for_region


def test_geofabrik_source_uses_state_slug():
    assert (
        source_for_request("geofabrik", "TN", None)
        == "osm-geofabrik-tennessee"
    )
    assert (
        source_for_request("geofabrik", "NC", None)
        == "osm-geofabrik-north-carolina"
    )


def test_geofabrik_import_infers_state_abbreviation():
    assert state_for_region("tennessee") == "TN"
    assert state_for_region("north-carolina") == "NC"
    assert state_for_region("custom-region") is None
