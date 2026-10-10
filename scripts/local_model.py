"""Prepare verified licensed weights in a reusable cache; never download during inference."""

import argparse
import fcntl
import hashlib
import os
from pathlib import Path
from time import monotonic

import httpx

from jobintel.local_model import (
    LICENSE_BYTES,
    LICENSE_SHA256,
    MODEL_BYTES,
    MODEL_FILE,
    MODEL_REPOSITORY,
    MODEL_SHA256,
)


def verify(path, checksum, size):
    if path.stat().st_size != size:
        raise ValueError("local model cache size mismatch; remove the corrupt file explicitly")
    with path.open("rb") as file:
        actual = hashlib.file_digest(file, "sha256").hexdigest()
    if actual != checksum:
        raise ValueError("local model cache checksum mismatch; remove the corrupt file explicitly")


def download(client, path, checksum, size, token, *, deadline):
    temporary = path.with_suffix(path.suffix + ".partial")
    digest = hashlib.sha256()
    received = 0
    url = f"https://registry-1.docker.io/v2/{MODEL_REPOSITORY}/blobs/sha256:{checksum}"
    try:
        with client.stream("GET", url, headers={"Authorization": f"Bearer {token}"}) as response:
            response.raise_for_status()
            with temporary.open("wb") as file:
                for chunk in response.iter_bytes(1024 * 1024):
                    received += len(chunk)
                    if received > size or monotonic() > deadline:
                        raise ValueError("local model download exceeded its size or time limit")
                    digest.update(chunk)
                    file.write(chunk)
                file.flush()
                os.fsync(file.fileno())
        if received != size or digest.hexdigest() != checksum:
            raise ValueError("local model download checksum/size mismatch")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def prepare(cache, *, offline=False, transport=None):
    cache.mkdir(parents=True, exist_ok=True)
    files = [
        (cache / MODEL_FILE, MODEL_SHA256, MODEL_BYTES),
        (cache / "LICENSE", LICENSE_SHA256, LICENSE_BYTES),
    ]
    with (cache / ".prepare.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        missing = []
        for path, checksum, size in files:
            if path.exists():
                verify(path, checksum, size)
            else:
                missing.append((path, checksum, size))
        if missing and offline:
            raise ValueError("offline local inference requires prepared model weights and license")
        if not missing:
            return
        with httpx.Client(timeout=60, follow_redirects=True, transport=transport) as client:
            deadline = monotonic() + 3600
            for path, checksum, size in missing:
                # A multi-GiB stream can outlive the registry's five-minute token.
                response = client.get(
                    "https://auth.docker.io/token",
                    params={
                        "service": "registry.docker.io",
                        "scope": f"repository:{MODEL_REPOSITORY}:pull",
                    },
                )
                response.raise_for_status()
                token = response.json()["token"]
                download(client, path, checksum, size, token, deadline=deadline)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, default=Path("local_data/models"))
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    started = monotonic()
    try:
        prepare(args.cache, offline=args.offline or os.getenv("JOBINTEL_LOCAL_OFFLINE") == "1")
    except (ValueError, KeyError, OSError, httpx.HTTPError):
        # Signed registry redirects and tokens must never appear in diagnostics.
        raise SystemExit(
            "Model preparation failed: check policy, verified CA trust and cache integrity"
        ) from None
    print(f"Verified model cache; preparation elapsed {monotonic() - started:.3f}s", flush=True)


if __name__ == "__main__":
    main()
