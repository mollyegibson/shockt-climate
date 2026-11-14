"""Tests for the /routes endpoint."""

from starlette.testclient import TestClient


class TestRoutesBasic:
    def test_vessel_routes_bangladesh_to_texas(self, client: TestClient) -> None:
        resp = client.get("/routes", params={"origin": "BGD", "destination": "TX"})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["vessel_direct"]) > 0
        route = data["vessel_direct"][0]
        assert route["total_wtw_kg_co2e_per_t"] > 0
        assert route["scenario"] == "open"
        assert len(route["legs"]) == 2

    def test_vessel_route_leg_structure(self, client: TestClient) -> None:
        resp = client.get("/routes", params={"origin": "BGD", "destination": "TX"})
        data = resp.json()
        route = data["vessel_direct"][0]
        sea_leg = route["legs"][0]
        assert sea_leg["network"] == "sea"
        assert sea_leg["mode"] == "ocean"
        assert sea_leg["km"] > 0
        assert sea_leg["duration_h"] is not None
        assert sea_leg["wtw_kg_co2e_per_tkm"] > 0
        assert sea_leg["from_name"] in ("Chittagong", "Mongla")
        assert sea_leg["to_name"] in ("Los Angeles", "New York")
        assert "from_lat" in sea_leg
        assert "from_lon" in sea_leg
        assert "to_lat" in sea_leg
        assert "to_lon" in sea_leg

        inland_leg = route["legs"][1]
        assert inland_leg["network"] == "road"
        assert inland_leg["mode"] == "truck"

    def test_vessel_route_emissions_consistency(self, client: TestClient) -> None:
        """total emissions = sum of leg emissions."""
        resp = client.get("/routes", params={"origin": "BGD", "destination": "TX"})
        data = resp.json()
        for route in data["vessel_direct"]:
            expected_wtw = sum(leg["km"] * leg["wtw_kg_co2e_per_tkm"] for leg in route["legs"])
            assert abs(route["total_wtw_kg_co2e_per_t"] - round(expected_wtw, 1)) <= 0.2

    def test_air_routes_bangladesh_to_texas(self, client: TestClient) -> None:
        resp = client.get("/routes", params={"origin": "BGD", "destination": "TX"})
        data = resp.json()
        assert len(data["air"]) > 0
        route = data["air"][0]
        assert len(route["legs"]) == 2
        assert route["legs"][0]["network"] == "air"
        assert route["legs"][0]["mode"] == "air"
        assert route["legs"][1]["network"] == "road"
        assert route["legs"][1]["mode"] == "truck"

    def test_routes_sorted_by_emissions(self, client: TestClient) -> None:
        resp = client.get("/routes", params={"origin": "BGD", "destination": "TX"})
        data = resp.json()
        direct = data["vessel_direct"]
        for i in range(len(direct) - 1):
            assert direct[i]["total_wtw_kg_co2e_per_t"] <= direct[i + 1]["total_wtw_kg_co2e_per_t"]


class TestRoutesWithCargo:
    def test_cargo_t_computes_total_emissions(self, client: TestClient) -> None:
        resp = client.get("/routes", params={"origin": "BGD", "destination": "TX", "cargo_t": 10.0})
        data = resp.json()
        route = data["vessel_direct"][0]
        assert route["total_wtw_kg_co2e"] is not None
        expected = round(route["total_wtw_kg_co2e_per_t"] * 10.0, 1)
        assert abs(route["total_wtw_kg_co2e"] - expected) <= 0.5

    def test_no_cargo_t_omits_total(self, client: TestClient) -> None:
        resp = client.get("/routes", params={"origin": "BGD", "destination": "TX"})
        data = resp.json()
        assert data["vessel_direct"][0]["total_wtw_kg_co2e"] is None


class TestRoutesFiltering:
    def test_mode_filter_vessel_only(self, client: TestClient) -> None:
        resp = client.get(
            "/routes", params={"origin": "BGD", "destination": "TX", "modes": "vessel"}
        )
        data = resp.json()
        assert len(data["vessel_direct"]) > 0
        assert data["air"] == []
        assert data["truck"] == []
        assert data["rail"] == []

    def test_mode_filter_air_only(self, client: TestClient) -> None:
        resp = client.get("/routes", params={"origin": "BGD", "destination": "TX", "modes": "air"})
        data = resp.json()
        assert data["vessel_direct"] == []
        assert len(data["air"]) > 0

    def test_limit_caps_results(self, client: TestClient) -> None:
        resp = client.get("/routes", params={"origin": "BGD", "destination": "TX", "limit": 1})
        data = resp.json()
        assert len(data["vessel_direct"]) <= 1

    def test_origin_by_node_id(self, client: TestClient) -> None:
        resp = client.get(
            "/routes",
            params={"origin": "departure_port:BGD_100", "destination": "TX"},
        )
        data = resp.json()
        for route in data["vessel_direct"]:
            assert route["legs"][0]["from_node"] == "departure_port:BGD_100"


class TestRoutesScenario:
    def test_alternate_scenario(self, client: TestClient) -> None:
        resp = client.get(
            "/routes",
            params={"origin": "BGD", "destination": "TX", "scenario": "suez_closed"},
        )
        data = resp.json()
        # Only BGD_100 → 2704 has a suez_closed distance
        for route in data["vessel_direct"]:
            assert route["scenario"] == "suez_closed"

    def test_scenario_comparison(self, client: TestClient) -> None:
        resp = client.get(
            "/routes",
            params={
                "origin": "CHN",
                "destination": "TX",
                "compare_scenario": "panama_closed",
                "modes": "vessel",
            },
        )
        data = resp.json()
        assert data["comparison"] is not None
        # CHN→NY has both open and panama_closed, so there should be matched routes
        comp = data["comparison"]
        all_entries = []
        for cat in ("vessel_direct", "vessel_feeder", "air", "truck", "rail"):
            all_entries.extend(comp.get(cat, []))
        assert len(all_entries) > 0

    def test_comparison_delta_sign(self, client: TestClient) -> None:
        """panama_closed routes are longer, so delta should be positive for CHN→NY."""
        resp = client.get(
            "/routes",
            params={
                "origin": "CHN",
                "destination": "TX",
                "compare_scenario": "panama_closed",
                "modes": "vessel",
            },
        )
        data = resp.json()
        comp = data["comparison"]
        for entry in comp.get("vessel_direct", []):
            if entry["compare"] is not None and entry["delta_wtw_kg_co2e_per_t"] is not None:
                # panama_closed NY route is longer (22100 vs 19200), so delta > 0
                if "0401" in entry["primary"]["legs"][0]["to_node"]:
                    assert entry["delta_wtw_kg_co2e_per_t"] > 0

    def test_comparison_primary_only_note(self, client: TestClient) -> None:
        """BGD→NY exists under open but not suez_closed; note should name suez_closed."""
        resp = client.get(
            "/routes",
            params={
                "origin": "BGD",
                "destination": "TX",
                "modes": "vessel",
                "compare_scenario": "suez_closed",
            },
        )
        data = resp.json()
        comp = data["comparison"]
        for entry in comp.get("vessel_direct", []):
            if entry["compare"] is None:
                assert "suez_closed" in entry["note"]

    def test_comparison_compare_only_route(self, client: TestClient) -> None:
        """BGD→NY exists under open but not suez_closed; reversing gives a compare-only route."""
        resp = client.get(
            "/routes",
            params={
                "origin": "BGD",
                "destination": "TX",
                "modes": "vessel",
                "scenario": "suez_closed",
                "compare_scenario": "open",
            },
        )
        data = resp.json()
        comp = data["comparison"]
        compare_only = [e for cat in comp.values() for e in cat if e["primary"] is None]
        assert len(compare_only) > 0
        for entry in compare_only:
            assert entry["compare"] is not None
            assert "suez_closed" in entry["note"]


class TestRoutesPassages:
    def test_passages_propagated(self, client: TestClient) -> None:
        resp = client.get("/routes", params={"origin": "BGD", "destination": "TX"})
        data = resp.json()
        # BGD→LA goes through babalmandab, suez, gibraltar
        for route in data["vessel_direct"]:
            if "2704" in route["legs"][0]["to_node"]:
                assert "babalmandab" in route["passages"]
                assert "suez" in route["passages"]

    def test_passage_free_route(self, client: TestClient) -> None:
        """CHN→LA has no passages."""
        resp = client.get(
            "/routes",
            params={"origin": "CHN", "destination": "CA", "modes": "vessel"},
        )
        data = resp.json()
        for route in data["vessel_direct"]:
            if "2704" in route["legs"][0]["to_node"] and "CHN" in route["legs"][0]["from_node"]:
                assert route["passages"] == []


class TestMexicoRoutes:
    def test_truck_routes(self, client: TestClient) -> None:
        resp = client.get(
            "/routes", params={"origin": "MEX", "destination": "TX", "modes": "truck"}
        )
        data = resp.json()
        assert len(data["truck"]) > 0
        route = data["truck"][0]
        assert len(route["legs"]) == 2
        assert route["legs"][0]["from_node"].startswith("mexico_plant:")
        assert route["legs"][0]["to_node"].startswith("border_crossing:")
        assert route["legs"][1]["from_node"].startswith("border_crossing:")
        assert route["legs"][1]["to_node"].startswith("destination_state:")

    def test_hs6_filters_plants(self, client: TestClient) -> None:
        resp = client.get(
            "/routes",
            params={"origin": "MEX", "destination": "TX", "modes": "truck", "hs6": "841810"},
        )
        data = resp.json()
        assert len(data["truck"]) > 0
        for route in data["truck"]:
            assert route["legs"][0]["from_node"] == "mexico_plant:plant_1"

    def test_nonmex_has_no_truck_routes(self, client: TestClient) -> None:
        resp = client.get(
            "/routes", params={"origin": "BGD", "destination": "TX", "modes": "truck"}
        )
        data = resp.json()
        assert data["truck"] == []


class TestRoutesResponseShape:
    def test_response_has_all_keys(self, client: TestClient) -> None:
        resp = client.get("/routes", params={"origin": "BGD", "destination": "TX"})
        data = resp.json()
        assert set(data.keys()) >= {
            "vessel_direct",
            "vessel_feeder",
            "air",
            "truck",
            "rail",
            "factors",
            "query",
        }

    def test_factors_present(self, client: TestClient) -> None:
        resp = client.get("/routes", params={"origin": "BGD", "destination": "TX"})
        data = resp.json()
        factors = data["factors"]
        assert "ocean" in factors
        assert "air" in factors
        assert "truck" in factors
        assert "rail" in factors
        ocean = factors["ocean"]
        assert ocean["source"] == "uk_desnz"
        assert ocean["vehicle_type"] == "container_ship"
        assert ocean["wtw"] > 0
        assert abs(ocean["wtw"] - ocean["ttw"] - ocean["wtt"]) < 1e-6

    def test_query_echo(self, client: TestClient) -> None:
        resp = client.get(
            "/routes",
            params={"origin": "BGD", "destination": "TX", "cargo_t": 5, "scenario": "open"},
        )
        data = resp.json()
        q = data["query"]
        assert q["origin"] == "BGD"
        assert q["destination"] == "TX"
        assert q["cargo_t"] == 5.0
        assert q["scenario"] == "open"
        assert q["inland_mode"] == "truck"

    def test_duration_on_legs(self, client: TestClient) -> None:
        resp = client.get("/routes", params={"origin": "BGD", "destination": "TX"})
        data = resp.json()
        for route in data["vessel_direct"]:
            for leg in route["legs"]:
                assert leg["duration_h"] is not None
                assert leg["duration_h"] > 0


class TestDisruptions:
    def test_disruptions_endpoint_returns_list(self, client: TestClient) -> None:
        resp = client.get("/disruptions")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)
