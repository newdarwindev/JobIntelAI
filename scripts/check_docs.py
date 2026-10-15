"""Проверить локальные ссылки, anchors и связи UI с секциями спецификации."""

import argparse
import json
import re
import subprocess
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]


def anchors(path):
    result = set()
    for heading in re.findall(r"^#+ (.+)$", path.read_text(), re.MULTILINE):
        slug = re.sub(r"[^\w\s-]", "", heading.lower()).replace(" ", "-")
        result.add(slug)
    return result


def check_links(path):
    for target in re.findall(r"\]\(([^\s)]+)\)", path.read_text()):
        parsed = urlsplit(target)
        if parsed.scheme or parsed.netloc:
            continue
        destination = path.parent / unquote(parsed.path) if parsed.path else path
        if not destination.exists():
            raise ValueError(f"{path}: отсутствует {target}")
        if parsed.fragment and destination.suffix == ".md":
            if unquote(parsed.fragment) not in anchors(destination):
                raise ValueError(f"{path}: отсутствует anchor {target}")


def check():
    files = subprocess.check_output(["git", "ls-files", "*.md"], text=True).splitlines()
    for name in files:
        path = ROOT / name
        if path.exists():
            check_links(path)
    spec = (ROOT / "docs/specification.md").read_text()
    sections = {int(number) for number in re.findall(r"^## (\d+)\.", spec, re.MULTILINE)}
    contract = json.loads((ROOT / "docs/web_ui_workflows.json").read_text())
    for workflow in contract["workflows"]:
        if not set(workflow["spec_sections"]).issubset(sections):
            raise ValueError(f"Неизвестная секция спецификации: {workflow['id']}")
    check_scenarios(contract)
    print("Локальные ссылки, anchors и секции UI проверены.")


def check_scenarios(contract):
    mapping = json.loads((ROOT / "docs/acceptance_map.json").read_text())
    known = set(mapping["regressions"]) | set(mapping["acceptance_issues"])
    for workflow in contract["workflows"]:
        if not set(workflow["scenarios"]).issubset(known):
            raise ValueError(f"Неизвестный сценарий: {workflow['id']}")
    for paths in mapping["regressions"].values():
        for path in paths:
            if not (ROOT / "tests" / path.split(" (")[0]).is_file():
                raise ValueError(f"Отсутствует regression test: {path}")


def main():
    argparse.ArgumentParser(description=__doc__).parse_args()
    check()


if __name__ == "__main__":
    main()
