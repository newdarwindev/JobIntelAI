"""V44: audit distributions for licensed fixtures and forbidden private runtime files."""

import argparse
import json
import subprocess
import tarfile
import zipfile
from hashlib import sha256
from pathlib import Path, PurePosixPath

FORBIDDEN = {"local_data", "work", ".git", ".venv", "node_modules", "test-results", ".env"}


def entries(path):
    if path.suffix == ".whl":
        with zipfile.ZipFile(path) as archive:
            return {
                name: archive.read(name) for name in archive.namelist() if not name.endswith("/")
            }
    with tarfile.open(path, "r:gz") as archive:
        return {
            str(
                PurePosixPath(member.name).relative_to(PurePosixPath(member.name).parts[0])
            ): archive.extractfile(member).read()
            for member in archive.getmembers()
            if member.isfile()
        }


def audit(path, public_data):
    contents = entries(path)
    for name, value in contents.items():
        parts = PurePosixPath(name).parts
        if set(parts) & FORBIDDEN or "results/generated" in name:
            raise ValueError("release contains a private runtime path")
        if PurePosixPath(name).suffix in {".db", ".pem", ".key"}:
            raise ValueError("release contains a database or key file")
        markers = [b"-----BEGIN " + b"PRIVATE KEY-----", b"JOBINTEL_PRIVATE_" + b"RELEASE_SENTINEL"]
        if any(marker in value for marker in markers):
            raise ValueError("release contains private key/sentinel content")
        if parts and parts[0] == "data" and (name not in public_data or value != public_data[name]):
            raise ValueError("release fixture differs from the licensed tracked corpus")
    if path.suffix != ".whl" and not public_data.keys() <= contents.keys():
        raise ValueError("source release is missing licensed offline fixtures")
    if not any(PurePosixPath(name).name == "LICENSE" for name in contents):
        raise ValueError("release is missing its license")
    return {
        "file": path.name,
        "sha256": sha256(path.read_bytes()).hexdigest(),
        "files": len(contents),
        "fixture_files": sum(name.startswith("data/") for name in contents),
        "audit": "passed",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    files = subprocess.check_output(["git", "ls-files", "data"], text=True).splitlines()
    public_data = {name: Path(name).read_bytes() for name in files}
    archives = sorted([*args.directory.glob("*.whl"), *args.directory.glob("*.tar.gz")])
    if len(archives) != 2:
        raise SystemExit("audit requires exactly one wheel and one source distribution")
    report = {
        "policy": "tracked authored fixtures; no private runtime paths, databases or keys",
        "artifacts": [audit(path, public_data) for path in archives],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
