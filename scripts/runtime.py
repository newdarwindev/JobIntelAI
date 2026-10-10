"""Start, inspect or stop a named local Compose environment from the repository root."""

import argparse
import os
import re
import subprocess
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
MODES = ["dev", "demo", "openai", "contract-test", "local-inference"]


def existing_file(value, setting):
    if not value:
        raise ValueError(f"{setting} must name a readable file")
    path = Path(value).expanduser().resolve()
    if not path.is_file() or not os.access(path, os.R_OK) or path.stat().st_size == 0:
        raise ValueError(f"{setting} must name a readable, nonempty file")
    return str(path)


def provider_environment(mode, environment):
    if mode == "local-inference":
        raise ValueError("local-inference requires the inference engine and adapter from issue #24")
    if mode == "contract-test":
        environment.update(
            JOBINTEL_PROVIDER="openai",
            JOBINTEL_CONFIGURATION="openai_normalized_v1",
            JOBINTEL_OPENAI_MODEL="contract-schema-v2",
            JOBINTEL_RESPONSES_MODE="emulator",
            JOBINTEL_RESPONSES_ENDPOINT="http://responses-emulator:8033/v1/responses",
        )
    elif mode == "openai":
        if not environment.get("JOBINTEL_OPENAI_MODEL", "").strip():
            raise ValueError("openai requires JOBINTEL_OPENAI_MODEL")
        environment["JOBINTEL_OPENAI_KEY_FILE"] = existing_file(
            environment.get("JOBINTEL_OPENAI_KEY_FILE"), "JOBINTEL_OPENAI_KEY_FILE"
        )
        environment["JOBINTEL_PROVIDER"] = "openai"
        environment["JOBINTEL_RESPONSES_MODE"] = "hosted"
        environment.setdefault("JOBINTEL_CONFIGURATION", "openai_normalized_v1")
    else:
        if mode == "dev" and environment.get("JOBINTEL_PROVIDER", "fixture") != "fixture":
            raise ValueError("use --mode openai with a mounted key file for the OpenAI provider")
        environment["JOBINTEL_PROVIDER"] = "fixture"
        if mode == "demo":
            environment["JOBINTEL_CONFIGURATION"] = "fixture_normalized"
    return environment


def validate_configuration(environment):
    provider = environment["JOBINTEL_PROVIDER"]
    configurations = {
        "fixture": {"fixture_raw", "fixture_normalized"},
        "openai": {"openai_structured_v1", "openai_normalized_v1"},
    }
    configuration = environment.get("JOBINTEL_CONFIGURATION")
    if configuration and configuration not in configurations[provider]:
        raise ValueError("JOBINTEL_CONFIGURATION must match the explicitly selected provider")
    try:
        timeout = float(environment.get("JOBINTEL_OPENAI_TIMEOUT", "30"))
    except ValueError:
        raise ValueError("JOBINTEL_OPENAI_TIMEOUT must be between 1 and 120 seconds") from None
    if not 1 <= timeout <= 120:
        raise ValueError("JOBINTEL_OPENAI_TIMEOUT must be between 1 and 120 seconds")


def compose_environment(args):
    environment = provider_environment(args.mode, dict(os.environ))
    validate_configuration(environment)
    environment["JOBINTEL_API_PORT"] = str(args.port)
    password = environment.get("JOBINTEL_POSTGRES_PASSWORD") or "local-demo-only"
    if not environment.get("JOBINTEL_COMPOSE_DATABASE_URL"):
        environment["JOBINTEL_COMPOSE_DATABASE_URL"] = (
            f"postgresql+psycopg://jobintel:{quote(password, safe='')}@db/jobintel"
        )
    if args.ca_bundle:
        environment["JOBINTEL_CA_BUNDLE"] = existing_file(args.ca_bundle, "--ca-bundle")
    return environment


def compose_command(args, *, configured=False):
    command = ["docker", "compose", "--project-name", args.project, "-f", "docker-compose.yml"]
    if configured:
        command += ["--profile", args.mode]
        if args.offline:
            if not list((ROOT / "build/wheels").glob("*.whl")):
                raise ValueError("--offline requires prepared wheels in build/wheels; see README")
            command += ["-f", "docker-compose.offline.yml"]
        if args.ca_bundle:
            command += ["-f", "docker-compose.proxy.yml"]
        if args.mode in {"demo", "openai"}:
            command += ["-f", f"docker-compose.{args.mode}.yml"]
        if args.mode == "contract-test":
            command += ["-f", "docker-compose.responses.yml"]
            if args.ca_bundle:
                command += ["-f", "docker-compose.responses-proxy.yml"]
    else:
        command += ["-f", "docker-compose.responses.yml", "--profile", "contract-test"]
    return command


def execute(args):
    if args.action == "reset" and not args.explicit_project:
        raise ValueError(
            "reset requires an explicit --project; it deletes only that project's volumes"
        )
    configured = args.action == "up"
    environment = compose_environment(args) if configured else dict(os.environ)
    command = compose_command(args, configured=configured)
    if configured:
        command += ["up", "-d", "--wait", "--wait-timeout", str(args.wait_timeout)]
        command += ["--no-build" if args.no_build else "--build"]
    elif args.action == "status":
        command += ["ps", "--all"]
    else:
        command += ["down"]
        if args.action == "reset":
            command += ["--volumes"]
    subprocess.run(command, env=environment, check=True)
    if configured:
        print(
            f"Ready: {args.project} / {args.mode} at http://127.0.0.1:{args.port}/ui/", flush=True
        )


def arguments():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["up", "status", "stop", "reset"])
    parser.add_argument("--mode", choices=MODES, default="dev")
    parser.add_argument("--project", help="isolated Compose name beginning with jobintel-")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--wait-timeout", type=int, default=120)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--no-build", action="store_true")
    parser.add_argument("--ca-bundle", help="combined normal/proxy CA bundle; mounted read-only")
    args = parser.parse_args()
    args.explicit_project = args.project is not None
    args.project = args.project or f"jobintel-{args.mode}"
    if Path.cwd() != ROOT:
        parser.error("Run from the repository root")
    if not re.fullmatch(r"jobintel-[a-z0-9][a-z0-9-]{0,48}", args.project):
        parser.error(
            "--project must begin with jobintel- and use lowercase letters, digits or hyphens"
        )
    if not 1024 <= args.port <= 65535 or not 1 <= args.wait_timeout <= 600:
        parser.error("--port must be 1024..65535 and --wait-timeout must be 1..600 seconds")
    return args


def main():
    args = arguments()
    try:
        execute(args)
    except (ValueError, OSError) as error:
        # Do not expose process environments, secret content or upstream response bodies.
        message = str(error) if isinstance(error, ValueError) else "Docker could not be started"
        raise SystemExit(message) from None
    except subprocess.CalledProcessError as error:
        raise SystemExit(error.returncode) from None


if __name__ == "__main__":
    main()
