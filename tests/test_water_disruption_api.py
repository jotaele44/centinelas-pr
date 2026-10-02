from fastapi.testclient import TestClient

from server.backend.main import app


def test_shadow_water_routes_are_mounted_and_discoverable():
    client = TestClient(app)
    health = client.get('/health')
    assert health.status_code == 200
    assert health.json()['shadow_water_pipeline'] is True
    assert client.get('/water-disruption/sources').status_code == 200
    console = client.get('/water-disruption/console')
    assert console.status_code == 200
    assert console.headers['content-type'].startswith('text/html')
    assert 'Shadow mode' in console.text


def test_outbox_reports_notifications_disabled():
    client = TestClient(app)
    payload = client.get('/water-disruption/outbox').json()
    assert payload['shadow_mode'] is True
    assert payload['notifications_enabled'] is False


def test_water_disruption_rejects_reserved_nonlocal_client():
    with TestClient(app, client=("203.0.113.10", 50000)) as remote_client:
        response = remote_client.get('/water-disruption/sources')

    assert response.status_code == 403
