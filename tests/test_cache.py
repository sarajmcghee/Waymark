from types import SimpleNamespace

from app.cache import source_for_request
from scripts.import_geofabrik import (
    TrailRelationHandler,
    allowed_uses,
    is_trail_like,
    state_for_region,
    trail_type,
)


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


def test_relation_membership_classifies_hiking_routes():
    relations = [
        {
            "id": "123",
            "route": "hiking",
            "name": "Long Trail",
        }
    ]

    assert trail_type({"highway": "service"}, relations) == "hiking_route"
    assert allowed_uses({"highway": "service"}, relations) == ["hiking"]


def test_way_tags_have_clear_trail_types():
    assert trail_type({"highway": "footway"}) == "footpath"
    assert trail_type({"highway": "track"}) == "track"
    assert (
        trail_type({"highway": "path", "sac_scale": "mountain_hiking"})
        == "alpine_hiking_trail"
    )


def test_standalone_sidewalks_are_not_trails():
    tags = {"highway": "footway", "footway": "sidewalk"}

    assert is_trail_like(tags) is False
    assert trail_type(tags) == "sidewalk"


def test_relation_handler_collects_member_ways():
    handler = TrailRelationHandler()
    relation = SimpleNamespace(
        id=123,
        tags=[
            SimpleNamespace(k="type", v="route"),
            SimpleNamespace(k="route", v="hiking"),
            SimpleNamespace(k="name", v="Long Trail"),
        ],
        members=[
            SimpleNamespace(type="w", ref=456),
            SimpleNamespace(type="n", ref=789),
        ],
    )

    handler.relation(relation)

    assert handler.relation_count == 1
    assert handler.way_relations[456][0]["name"] == "Long Trail"
    assert 789 not in handler.way_relations
