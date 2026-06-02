from app.config import Settings, get_firebase_web_config


def test_firebase_web_config_is_disabled_when_values_are_missing():
    settings = Settings(firebase_project_id="waymark-dev")

    assert get_firebase_web_config(settings) is None


def test_firebase_web_config_returns_client_config_when_complete():
    settings = Settings(
        firebase_project_id="waymark-dev",
        firebase_api_key="api-key",
        firebase_auth_domain="waymark-dev.firebaseapp.com",
        firebase_app_id="app-id",
    )

    assert get_firebase_web_config(settings) == {
        "apiKey": "api-key",
        "authDomain": "waymark-dev.firebaseapp.com",
        "projectId": "waymark-dev",
        "appId": "app-id",
    }
