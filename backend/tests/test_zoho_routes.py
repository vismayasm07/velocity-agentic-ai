from app.main import app


def test_zoho_integration_route_methods() -> None:
    paths = app.openapi()["paths"]

    assert set(paths["/api/integrations/zoho/authorize"]) >= {"get", "post"}
    assert set(paths["/api/integrations/zoho/callback"]) >= {"get"}
    assert set(paths["/api/integrations/zoho/status"]) >= {"get"}
    assert set(paths["/api/integrations/zoho/test"]) >= {"post"}
    assert set(paths["/api/integrations/zoho/deals"]) >= {"get"}
    assert set(paths["/api/integrations/zoho/sync/deals"]) >= {"post"}
    assert set(paths["/api/integrations/zoho"]) >= {"delete"}