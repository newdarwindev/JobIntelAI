"""#26: protocol refusal and connect-time lease checks over real fixture sockets."""

import http.client
import json

from fastapi.testclient import TestClient

from jobintel.api import create_app
from jobintel.egress_policy import RESOLVE_PATH, ROUTE_HEADER, EgressPolicy
from scripts.acquisition_fixtures.client import FixtureResolver
from scripts.acquisition_fixtures.local import local_acquirer
from tests.integration.test_acquisition_boundary import SOURCE, register
from tests.integration.test_acquisition_wire import wire as wire
from tests.integration.test_extraction_boundary_v2 import DATA, migrate
from tests.integration.test_extraction_boundary_v2 import isolated_database as isolated_database


def connection(wire):
    return http.client.HTTPConnection("127.0.0.1", wire["gateway"].server_port, timeout=3)


def issue(wire, host="example.com"):
    conn = connection(wire)
    try:
        conn.request("POST", RESOLVE_PATH, json.dumps({"host": host, "scheme": "https"}))
        response = conn.getresponse()
        assert response.status == 200
        return json.loads(response.read())["route"]
    finally:
        conn.close()


def connect(wire, route, host="example.com"):
    conn = connection(wire)
    try:
        conn.request("CONNECT", f"{host}:443", headers={ROUTE_HEADER: route})
        response = conn.getresponse()
        return response.status, response.getheader("JobIntel-Egress-Error")
    finally:
        conn.close()


def test_connect_revalidates_and_rebound_host_sends_no_origin_bytes(wire):
    wire["gateway"].policy = EgressPolicy(["rebind.example.test"], resolver=FixtureResolver())
    before = wire["origin"].snapshot()
    route = issue(wire, "rebind.example.test")
    assert connect(wire, route, "rebind.example.test") == (422, "blocked_destination")
    assert connect(wire, route, "rebind.example.test") == (502, "proxy_denied")
    assert wire["origin"].snapshot() == before


def test_single_use_connect_grant_cannot_change_host_or_be_replayed(wire):
    wire["gateway"].policy = EgressPolicy(["example.com"], resolver=FixtureResolver())
    before = wire["origin"].snapshot()
    route = issue(wire)
    assert connect(wire, route, "wrong.example.test") == (502, "proxy_denied")
    assert connect(wire, route) == (502, "proxy_denied")
    assert wire["origin"].snapshot() == before


def test_unsupported_real_proxy_contract_health_and_fetch_preserve_manual_history(
    wire, isolated_database, monkeypatch
):
    migrate(isolated_database, "head", monkeypatch)
    monkeypatch.setattr("jobintel.egress_proxy.CAPABILITIES", {"protocol": "hostname-only"})
    with TestClient(
        create_app(isolated_database, DATA, acquirer=local_acquirer(wire, mode="policy-proxy"))
    ) as client:
        register(client)
        client.post("/jobs/fetched/snapshots", json={"text": SOURCE})
        run = client.post("/jobs/fetched/extract", json={}).json()["run_id"]
        before = wire["origin"].snapshot()
        health = client.get("/health")
        assert health.status_code == 503 and health.json()["acquisition"]["ready"] is False
        result = client.post("/jobs/fetched/fetch")
        assert result.status_code == 503 and result.json()["detail"]["code"] == "proxy_capability"
        assert result.json()["attempts"][0]["http_status"] is None
        assert client.get("/jobs/fetched").json()["extraction"]["run_id"] == run
        assert len(client.get("/jobs/fetched/history").json()["acquisition_attempts"]) == 1
        assert wire["origin"].snapshot() == before
