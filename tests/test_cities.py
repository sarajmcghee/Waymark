from zipfile import ZipFile

from fastapi import HTTPException

from app.trails import _resolve_nearby_origin, _validate_length_range
from scripts.import_cities import place_rows


class UnusedConnection:
    pass


def test_nearby_origin_accepts_coordinates():
    assert _resolve_nearby_origin(
        UnusedConnection(),
        lat=36.16,
        lng=-86.78,
        city=None,
        state=None,
    ) == (36.16, -86.78)


def test_nearby_origin_requires_complete_location():
    try:
        _resolve_nearby_origin(
            UnusedConnection(),
            lat=36.16,
            lng=None,
            city=None,
            state=None,
        )
    except HTTPException as exc:
        assert exc.status_code == 400
        assert exc.detail == "Both lat and lng are required."
    else:
        raise AssertionError("Expected incomplete coordinates to fail.")


def test_place_rows_reads_census_pipe_delimited_zip(tmp_path):
    zip_path = tmp_path / "places.zip"
    content = (
        "USPS|GEOID|NAME|INTPTLAT|INTPTLONG\n"
        "TN|4752006|Nashville-Davidson|36.1718000|-86.7850000\n"
    )
    with ZipFile(zip_path, "w") as archive:
        archive.writestr("2025_Gaz_place_national.txt", content)

    assert list(place_rows(zip_path)) == [
        {
            "USPS": "TN",
            "GEOID": "4752006",
            "NAME": "Nashville-Davidson",
            "INTPTLAT": "36.1718000",
            "INTPTLONG": "-86.7850000",
        }
    ]


def test_length_range_rejects_inverted_values():
    try:
        _validate_length_range(10, 5)
    except HTTPException as exc:
        assert exc.status_code == 400
        assert exc.detail == "min_length_km cannot exceed max_length_km."
    else:
        raise AssertionError("Expected inverted length range to fail.")
