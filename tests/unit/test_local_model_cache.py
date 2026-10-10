"""Model preparation rejects corrupt or interrupted weights without an inference fallback."""

import hashlib
from pathlib import Path
from time import monotonic

import httpx
import pytest

from scripts import local_model


def test_cache_rejects_size_and_digest_mismatch(tmp_path):
    path = tmp_path / "weights"
    path.write_bytes(b"authored-cache")
    checksum = hashlib.sha256(b"other-content").hexdigest()
    with pytest.raises(ValueError, match="size mismatch"):
        local_model.verify(path, checksum, 1)
    with pytest.raises(ValueError, match="checksum mismatch"):
        local_model.verify(path, checksum, path.stat().st_size)


@pytest.mark.parametrize("body,deadline", [(b"too large", 60), (b"bad", 60), (b"good", -1)])
def test_bad_download_cannot_replace_a_saved_cache(tmp_path, body, deadline):
    path = tmp_path / "weights.gguf"
    path.write_bytes(b"saved")
    checksum = hashlib.sha256(b"good").hexdigest()
    transport = httpx.MockTransport(lambda request: httpx.Response(200, content=body))
    with httpx.Client(transport=transport) as client, pytest.raises(ValueError):
        local_model.download(
            client, path, checksum, 4, "authored-token", deadline=monotonic() + deadline
        )
    assert path.read_bytes() == b"saved"
    assert not list(tmp_path.glob("*.partial"))


def test_verified_download_publishes_atomically(tmp_path):
    path = tmp_path / "weights.gguf"
    content = b"authored-weight-bytes"
    checksum = hashlib.sha256(content).hexdigest()
    seen = []

    def respond(request):
        seen.append(request)
        assert not path.exists()
        return httpx.Response(200, content=content)

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        local_model.download(
            client, path, checksum, len(content), "authored-token", deadline=monotonic() + 60
        )
    local_model.verify(path, checksum, len(content))
    assert seen[0].url.host == "registry-1.docker.io"
    assert not list(tmp_path.glob("*.partial"))


def test_offline_missing_cache_never_contacts_a_registry(tmp_path):
    transport = httpx.MockTransport(lambda request: pytest.fail("offline request"))
    with pytest.raises(ValueError, match="prepared model"):
        local_model.prepare(tmp_path, offline=True, transport=transport)


def test_offline_reuses_verified_weights_and_license(tmp_path, monkeypatch):
    content = b"authored"
    checksum = hashlib.sha256(content).hexdigest()
    for key in ["MODEL_SHA256", "LICENSE_SHA256"]:
        monkeypatch.setattr(local_model, key, checksum)
    for key in ["MODEL_BYTES", "LICENSE_BYTES"]:
        monkeypatch.setattr(local_model, key, len(content))
    (tmp_path / local_model.MODEL_FILE).write_bytes(content)
    (tmp_path / "LICENSE").write_bytes(content)
    transport = httpx.MockTransport(lambda request: pytest.fail("cached request"))
    local_model.prepare(tmp_path, offline=True, transport=transport)


def test_prepare_does_not_redownload_a_corrupt_cache(tmp_path):
    (tmp_path / local_model.MODEL_FILE).write_bytes(b"broken")
    transport = httpx.MockTransport(lambda request: pytest.fail("corrupt cache request"))
    with pytest.raises(ValueError, match="mismatch"):
        local_model.prepare(Path(tmp_path), transport=transport)
