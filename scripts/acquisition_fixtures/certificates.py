"""Create a disposable scoped CA; private keys stay in ignored runtime storage."""

import subprocess
from pathlib import Path


def certificates(directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    if (directory / "origin.pem").exists():
        valid = subprocess.run(
            ["openssl", "x509", "-checkend", "60", "-noout", "-in", "origin.pem"],
            cwd=directory,
            capture_output=True,
        )
        if valid.returncode:
            raise ValueError("Fixture TLS trust has expired; use a fresh acquisition project")
        return directory
    commands = [
        [
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-days",
            "2",
            "-subj",
            "/CN=JobIntel authored acquisition test CA",
            "-addext",
            "basicConstraints=critical,CA:TRUE",
            "-keyout",
            "ca.key",
            "-out",
            "ca.pem",
        ],
        [
            "req",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-subj",
            "/CN=example.com",
            "-keyout",
            "origin.key",
            "-out",
            "origin.csr",
        ],
        [
            "x509",
            "-req",
            "-in",
            "origin.csr",
            "-CA",
            "ca.pem",
            "-CAkey",
            "ca.key",
            "-CAcreateserial",
            "-days",
            "2",
            "-extfile",
            "extensions.cnf",
            "-out",
            "origin.pem",
        ],
    ]
    (directory / "extensions.cnf").write_text(
        "subjectAltName=DNS:example.com,DNS:rebind.example.test\n"
        "basicConstraints=critical,CA:FALSE\nextendedKeyUsage=serverAuth\n"
    )
    for arguments in commands:
        subprocess.run(["openssl", *arguments], cwd=directory, check=True, capture_output=True)
    for name in ["ca.key", "origin.key"]:
        (directory / name).chmod(0o600)
    return directory
