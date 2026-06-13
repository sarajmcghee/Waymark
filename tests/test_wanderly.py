from app.trails import (
    _estimated_duration_hours,
    _is_hike_intent,
    _normalized_difficulty,
    _wanderly_category,
)


def test_normalizes_difficulty_to_three_buckets():
    assert _normalized_difficulty([], ["footpath"], 2.5) == "easy"
    assert (
        _normalized_difficulty(["Class 3: Developed"], [], 2.5)
        == "moderate"
    )
    assert (
        _normalized_difficulty(["demanding_mountain_hiking"], [], 2.5)
        == "hard"
    )


def test_distance_sets_a_minimum_difficulty():
    assert _normalized_difficulty([], ["footpath"], 3) == "moderate"
    assert _normalized_difficulty([], ["footpath"], 7.9) == "moderate"
    assert _normalized_difficulty([], ["footpath"], 8) == "hard"
    assert _normalized_difficulty(["easy"], ["footpath"], 25) == "hard"


def test_estimated_duration_uses_distance_and_difficulty():
    assert _estimated_duration_hours(5000, "easy") == 1
    assert _estimated_duration_hours(5000, "moderate") == 1.15
    assert _estimated_duration_hours(5000, "hard") == 1.35


def test_category_uses_distance_and_difficulty():
    assert _wanderly_category(2.5, "easy") == "walk"
    assert _wanderly_category(4, "easy") == "moderate_hike"
    assert _wanderly_category(2, "moderate") == "moderate_hike"
    assert _wanderly_category(8, "easy") == "major_hike"
    assert _wanderly_category(2, "hard") == "major_hike"


def test_hike_intent_excludes_crossings_and_non_foot_paths():
    base = {
        "allowed_uses": ["hiking"],
        "trail_type": "path",
        "source_id": "123",
        "raw_properties": {},
    }

    assert _is_hike_intent(base) is True
    assert _is_hike_intent({**base, "allowed_uses": ["biking"]}) is False
    assert _is_hike_intent(
        {**base, "raw_properties": {"footway": "crossing"}}
    ) is False
    assert _is_hike_intent(
        {**base, "raw_properties": {"foot": "no"}}
    ) is False
    assert _is_hike_intent(
        {
            **base,
            "source_id": "relation:456",
            "raw_properties": {"foot": "no"},
        }
    ) is True
