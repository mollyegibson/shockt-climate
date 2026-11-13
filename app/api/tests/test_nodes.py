"""Tests for node search and country listing endpoints."""

from starlette.testclient import TestClient


class TestNodeSearch:
    def test_search_by_name(self, client: TestClient) -> None:
        resp = client.get("/nodes/search", params={"q": "Chittagong"})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1
        assert data[0]["name"] == "Chittagong"
        assert data[0]["iso3"] == "BGD"

    def test_search_by_iso3(self, client: TestClient) -> None:
        resp = client.get("/nodes/search", params={"q": "BGD"})
        assert resp.status_code == 200
        data = resp.json()
        assert any(r["iso3"] == "BGD" for r in data)

    def test_search_by_country_name(self, client: TestClient) -> None:
        resp = client.get("/nodes/search", params={"q": "Bangladesh"})
        assert resp.status_code == 200
        data = resp.json()
        assert any(r["iso3"] == "BGD" for r in data)

    def test_search_with_kind_filter(self, client: TestClient) -> None:
        resp = client.get("/nodes/search", params={"q": "BGD", "kind": "departure_port"})
        assert resp.status_code == 200
        data = resp.json()
        assert all(r["kind"] == "departure_port" for r in data)

    def test_search_with_limit(self, client: TestClient) -> None:
        resp = client.get("/nodes/search", params={"q": "a", "limit": 2})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) <= 2

    def test_search_no_results(self, client: TestClient) -> None:
        resp = client.get("/nodes/search", params={"q": "zzzznoexist"})
        assert resp.status_code == 200
        assert resp.json() == []

    def test_search_result_shape(self, client: TestClient) -> None:
        resp = client.get("/nodes/search", params={"q": "Los Angeles"})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1
        node = data[0]
        assert set(node.keys()) == {"node_id", "kind", "name", "iso3", "lat", "lon"}


class TestCountries:
    def test_lists_origin_countries(self, client: TestClient) -> None:
        resp = client.get("/countries")
        assert resp.status_code == 200
        data = resp.json()
        iso3s = [c["iso3"] for c in data]
        assert "BGD" in iso3s
        assert "CHN" in iso3s

    def test_mexico_has_overland_modes(self, client: TestClient) -> None:
        resp = client.get("/countries")
        data = resp.json()
        mex = next(c for c in data if c["iso3"] == "MEX")
        assert "truck" in mex["modes"]
        assert "rail" in mex["modes"]

    def test_country_result_shape(self, client: TestClient) -> None:
        resp = client.get("/countries")
        data = resp.json()
        assert len(data) >= 1
        c = data[0]
        assert set(c.keys()) == {"iso3", "name", "modes"}
