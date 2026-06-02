NPS_PUBLIC_TRAILS_QUERY_URL = (
    "https://mapservices.nps.gov/arcgis/rest/services/"
    "NationalDatasets/NPS_Public_Trails_Geographic/FeatureServer/0/query"
)

NPS_TRAIL_OUT_FIELDS = (
    "OBJECTID,TRLNAME,MAPLABEL,TRLSTATUS,TRLSURFACE,TRLTYPE,TRLCLASS,TRLUSE,"
    "UNITCODE,UNITNAME,MAINTAINER,OPENTOPUBLIC,FEATUREID,GEOMETRYID,Shape__Length"
)

SOURCE_PRESETS = [
    {
        "id": "nps-public-trails-all",
        "label": "All NPS Public Trails",
        "agency": "National Park Service",
        "source": "nps-public-trails-all",
        "url": NPS_PUBLIC_TRAILS_QUERY_URL,
        "where": "1=1",
        "out_fields": NPS_TRAIL_OUT_FIELDS,
        "result_record_count": 1000,
        "max_pages": 40,
    },
    {
        "id": "nps-public-trails-grsm",
        "label": "Great Smoky Mountains",
        "agency": "National Park Service",
        "source": "nps-public-trails-grsm",
        "url": NPS_PUBLIC_TRAILS_QUERY_URL,
        "where": "UNITCODE = 'GRSM'",
        "out_fields": NPS_TRAIL_OUT_FIELDS,
        "result_record_count": 500,
        "max_pages": 5,
    },
    {
        "id": "nps-public-trails-yell",
        "label": "Yellowstone",
        "agency": "National Park Service",
        "source": "nps-public-trails-yell",
        "url": NPS_PUBLIC_TRAILS_QUERY_URL,
        "where": "UNITCODE = 'YELL'",
        "out_fields": NPS_TRAIL_OUT_FIELDS,
        "result_record_count": 500,
        "max_pages": 5,
    },
    {
        "id": "nps-public-trails-yose",
        "label": "Yosemite",
        "agency": "National Park Service",
        "source": "nps-public-trails-yose",
        "url": NPS_PUBLIC_TRAILS_QUERY_URL,
        "where": "UNITCODE = 'YOSE'",
        "out_fields": NPS_TRAIL_OUT_FIELDS,
        "result_record_count": 500,
        "max_pages": 5,
    },
    {
        "id": "nps-public-trails-grca",
        "label": "Grand Canyon",
        "agency": "National Park Service",
        "source": "nps-public-trails-grca",
        "url": NPS_PUBLIC_TRAILS_QUERY_URL,
        "where": "UNITCODE = 'GRCA'",
        "out_fields": NPS_TRAIL_OUT_FIELDS,
        "result_record_count": 500,
        "max_pages": 5,
    },
    {
        "id": "nps-public-trails-romo",
        "label": "Rocky Mountain",
        "agency": "National Park Service",
        "source": "nps-public-trails-romo",
        "url": NPS_PUBLIC_TRAILS_QUERY_URL,
        "where": "UNITCODE = 'ROMO'",
        "out_fields": NPS_TRAIL_OUT_FIELDS,
        "result_record_count": 500,
        "max_pages": 5,
    },
]
