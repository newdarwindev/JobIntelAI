"""#26: complete-answer checks, lease replay/rebinding and configuration refusal."""

import socket
import ssl

import pytest

from jobintel.acquisition import HttpAcquirer
from jobintel.egress_policy import CAPABILITIES, EgressPolicy
from jobintel.egress_proxy import EgressHandler
from jobintel.fetch_destinations import Destination
from jobintel.fetch_transport import HttpTransport
from jobintel.fetch_types import FetchError
from jobintel.policy_proxy_client import capability, policy_destination
from tests.acquisition_fakes import PUBLIC, URL, Resolver
from tests.unit.test_fetch_transport import WireSocket


@pytest.mark.parametrize(
    "answers", [["127.0.0.1"], [PUBLIC, "10.0.0.1"], ["::ffff:8.8.8.8"], ["169.254.169.254"]]
)
def test_gateway_rejects_complete_private_or_mixed_answers(answers):
    policy = EgressPolicy(["example.com"], resolver=Resolver([answers]))
    with pytest.raises(FetchError) as error:
        policy.issue("example.com", "https")
    assert error.value.code == "blocked_destination" and not policy.leases


def test_gateway_revalidates_before_consuming_and_never_reuses_lease():
    resolver = Resolver([[PUBLIC], [PUBLIC, "127.0.0.1"]])
    policy = EgressPolicy(["example.com"], resolver=resolver)
    route = policy.issue("example.com", "https")["route"]
    with pytest.raises(FetchError) as error:
        policy.consume(route, "example.com", "https")
    assert error.value.code == "blocked_destination"
    with pytest.raises(FetchError) as error:
        policy.consume(route, "example.com", "https")
    assert error.value.code == "proxy_denied" and len(resolver.calls) == 2


@pytest.mark.parametrize("host,scheme", [("other.example", "https"), ("example.com", "http")])
def test_lease_cannot_change_hostname_or_scheme(host, scheme):
    policy = EgressPolicy(["example.com"], resolver=Resolver([[PUBLIC]]))
    route = policy.issue("example.com", "https")["route"]
    with pytest.raises(FetchError) as error:
        policy.consume(route, host, scheme)
    assert error.value.code == "proxy_denied" and not policy.leases


def test_expired_and_exhausted_leases_fail_closed():
    clock = [0]
    policy = EgressPolicy(["example.com"], resolver=Resolver([[PUBLIC]]), clock=lambda: clock[0])
    route = policy.issue("example.com", "http")["route"]
    clock[0] = 10
    with pytest.raises(FetchError) as error:
        policy.consume(route, "example.com", "http")
    assert error.value.code == "proxy_denied"
    policy.leases = {str(i): (None, 30) for i in range(1024)}
    with pytest.raises(FetchError) as error:
        policy.issue("example.com", "http")
    assert error.value.code == "proxy_denied"


def test_unlisted_hostname_does_not_trigger_dns():
    resolver = Resolver([[PUBLIC]])
    policy = EgressPolicy(["example.com"], resolver=resolver)
    with pytest.raises(FetchError) as error:
        policy.issue("unlisted.example", "https")
    assert error.value.code == "proxy_denied" and resolver.calls == []


def test_gateway_connection_is_numeric_and_rejects_unexpected_peer(monkeypatch):
    calls, sock = [], WireSocket(peer="127.0.0.1")

    def connect(target, timeout):
        calls.append((target, timeout))
        return sock

    monkeypatch.setattr(socket, "create_connection", connect)
    destination = Destination(URL, "example.com", 443, PUBLIC, "https")
    with pytest.raises(FetchError) as error:
        EgressHandler.open_upstream(None, destination)
    assert error.value.code == "blocked_destination"
    assert calls == [((PUBLIC, 443), 3)] and sock.closed and sock.sent == []


@pytest.mark.parametrize(
    "value",
    [
        {},
        {**CAPABILITIES, "guarantees": ["hostname-connect"]},
        {**CAPABILITIES, "protocol": "other"},
    ],
)
def test_ordinary_or_incomplete_proxy_contract_is_not_ready(monkeypatch, value):
    monkeypatch.setattr("jobintel.policy_proxy_client.rpc", lambda *_args, **_kwargs: value)
    transport = HttpTransport(
        mode="policy-proxy", proxies={"http": "http://proxy:8080", "https": "http://proxy:8080"}
    )
    ready = transport.readiness()
    assert ready["ready"] is False and ready["error"]["code"] == "proxy_capability"
    result = HttpAcquirer(transport=transport).fetch(URL)
    assert result.error.code == "proxy_capability" and len(result.events) == 1


@pytest.mark.parametrize(
    "mode,proxies",
    [
        ("direct", {"https": "http://proxy:8080"}),
        ("pinned-proxy", {}),
        ("policy-proxy", {"https": "http://proxy:8080", "no": "example.com"}),
    ],
)
def test_explicit_routing_mode_never_falls_back_to_other_path(mode, proxies):
    resolver = Resolver([[PUBLIC]])
    result = HttpAcquirer(
        transport=HttpTransport(mode=mode, proxies=proxies), resolver=resolver
    ).fetch(URL)
    assert result.error.code == "proxy_capability" and resolver.calls == []


@pytest.mark.parametrize(
    "changes",
    [
        {"host": "other.example"},
        {"scheme": "http"},
        {"address": "10.0.0.1"},
        {"route": "bad\r\nHeader: value"},
    ],
)
def test_invalid_gateway_pin_or_lease_is_refused(monkeypatch, changes):
    value = {
        "host": "example.com",
        "scheme": "https",
        "address": PUBLIC,
        "route": "a" * 64,
        **changes,
    }
    monkeypatch.setattr("jobintel.policy_proxy_client.capability", lambda *_: None)
    monkeypatch.setattr("jobintel.policy_proxy_client.rpc", lambda *_args, **_kwargs: value)
    with pytest.raises(FetchError) as error:
        policy_destination(URL, ("proxy", 8080), 3)
    assert error.value.code in {"proxy_capability", "blocked_destination"}


def test_scoped_ca_preserves_default_trust_and_tls_verification(monkeypatch):
    context, loaded = ssl.create_default_context(), []
    monkeypatch.setenv("JOBINTEL_ACQUISITION_CA_FILE", "/authored/ca.pem")
    monkeypatch.setattr("jobintel.fetch_transport.ssl.create_default_context", lambda: context)
    monkeypatch.setattr(context, "load_verify_locations", lambda filename: loaded.append(filename))
    transport = HttpTransport()
    assert loaded == ["/authored/ca.pem"] and transport.context.check_hostname
    assert transport.context.verify_mode == ssl.CERT_REQUIRED


def test_unsupported_mode_is_explicit():
    with pytest.raises(ValueError, match="unsupported JOBINTEL_ACQUISITION_MODE"):
        HttpTransport(mode="hostname-only")


def test_full_capability_contract_is_required(monkeypatch):
    monkeypatch.setattr("jobintel.policy_proxy_client.rpc", lambda *_args, **_kwargs: CAPABILITIES)
    capability(("proxy", 8080), 3)


@pytest.mark.parametrize("host", ["example.com:443", "example.com/path", "example.com?query"])
def test_resolution_request_cannot_smuggle_a_port_or_path(host):
    policy = EgressPolicy([host], resolver=Resolver([[PUBLIC]]))
    with pytest.raises(FetchError) as error:
        policy.issue(host, "https")
    assert error.value.code == "invalid_url"
