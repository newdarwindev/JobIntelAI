"""Выбор сценария и безопасная диагностика emulator по записанному владельцу проекта."""

import argparse
import json
from urllib.parse import urlsplit

from scripts.environment_lifecycle import read_record, resources
from scripts.responses_environment import request


def control_base(project):
    record = read_record(project)
    if not record or record.get("status") != "ready":
        raise ValueError(
            "Нет готового окружения; используйте make env ARGS='up --persistent --mode emulator'"
        )
    if record.get("configuration", {}).get("mode") != "emulator":
        raise ValueError("Проект не является emulator")
    owned = resources(project, record["owner"])
    if not owned["containers"] or resources(project) != owned:
        raise ValueError("Проект содержит чужие ресурсы")
    base = record["endpoints"]["control_base"]
    parsed = urlsplit(base)
    if parsed.scheme != "http" or parsed.hostname != "127.0.0.1" or not parsed.port:
        raise ValueError("Control endpoint должен быть локальным HTTP")
    if parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment:
        raise ValueError("Недопустимый control endpoint")
    return base


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    parser.add_argument(
        "--scenario", default="success", help="Имя authored-сценария, например quota"
    )
    args = parser.parse_args()
    base = control_base(args.project)
    request(base, "/control", {"scenario": args.scenario})
    print(json.dumps(request(base, "/diagnostics"), indent=2))


if __name__ == "__main__":
    main()
