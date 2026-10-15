"""Команды разработки. make <цель>; параметры отдельных команд: make <цель> ARGS='--help'.

setup — .venv и зависимости; migrate — явные миграции настроенной БД;
demo — изолированный синтетический прогон; serve — временный веб-стенд;
check / check-postgres — полные проверки; prepare-offline — Linux x86_64/Python 3.12 wheels;
env — общий lifecycle (run/up/start/status/stop/reset, fixture/emulator/local);
emulator-scenario — управление сценарием по PROJECT и SCENARIO;
acquisition-check / acquisition-public-check — локальный / явно выбранный публичный smoke;
model-prepare / model-check — проверенные веса / CPU smoke;
experiment-replay — freeze/plan/run/rescore без платных запросов;
experiment-rescore/audit/publish/resume — существующие команды экспериментов;
network-experiment — B/C через локальную модель или emulator;
reports — русский рендер сохранённых измерений; docs-check — ссылки документации;
ui-install / ui-check — зависимости браузера / все journeys и проверенные записи.
"""

import argparse
import os
import platform
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]


def run(*command, environment=None):
    environment = dict(os.environ if environment is None else environment)
    environment["PATH"] = str(Path(sys.executable).parent) + os.pathsep + environment["PATH"]
    return subprocess.run(command, cwd=ROOT, env=environment, check=True)


def setup():
    run(sys.executable, "-m", "venv", ".venv")
    run(
        str(ROOT / ".venv/bin/python"),
        "-m",
        "pip",
        "install",
        "-c",
        "requirements.lock.txt",
        "-e",
        ".[dev]",
    )


def migrate():
    (ROOT / "local_data").mkdir(exist_ok=True)
    run(sys.executable, "-m", "alembic", "upgrade", "head")


def demo():
    with TemporaryDirectory(prefix="jobintel-demo-") as directory:
        environment = {
            **os.environ,
            "JOBINTEL_DATABASE_URL": f"sqlite:///{directory}/demo.db",
            "JOBINTEL_PROVIDER": "fixture",
            "JOBINTEL_CONFIGURATION": "fixture_normalized",
            "JOBINTEL_FIXTURE_ROOT": str(ROOT / "data"),
        }
        run(sys.executable, "-m", "alembic", "upgrade", "head", environment=environment)
        for action in ("demo", "evaluate"):
            run(
                sys.executable,
                "-m",
                "jobintel.cli",
                action,
                "--output",
                "results/generated/demo",
                environment=environment,
            )


def quality():
    run(sys.executable, "-m", "ruff", "check", ".")
    run(sys.executable, "-m", "ruff", "format", "--check", ".")
    run("shellcheck", "scripts/install_actionlint.sh")
    run("bash", "scripts/install_actionlint.sh")
    run("local_data/bin/actionlint", "-color")
    run(sys.executable, "-m", "scripts.check_docs")


def prepare_offline():
    if (platform.system(), platform.machine(), sys.version_info[:2]) != (
        "Linux",
        "x86_64",
        (3, 12),
    ):
        raise ValueError("Wheels для образа требуют Linux x86_64 и Python 3.12")
    run(
        sys.executable,
        "-m",
        "pip",
        "wheel",
        "--wheel-dir",
        "build/wheels",
        "-c",
        "requirements.lock.txt",
        "-r",
        "requirements.lock.txt",
        "setuptools>=75",
        "wheel",
        ".",
    )


def ui_install():
    run("npm", "ci")
    run("npx", "playwright", "install", "--with-deps", "chromium")


def ui_check():
    environment = {**os.environ, "UI_PYTHON": sys.executable}
    for action in (
        "test:recordings",
        "test:drafts",
        "test:mutations",
        "test:batches",
        "test:ui",
        "record:ui",
        "check:ui",
        "prepare:ui-artifacts",
    ):
        run("npm", "run", action, environment=environment)


def main():
    actions = {
        "setup": setup,
        "migrate": migrate,
        "demo": demo,
        "quality": quality,
        "prepare-offline": prepare_offline,
        "ui-install": ui_install,
        "ui-check": ui_check,
    }
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("action", choices=actions)
    args = parser.parse_args()
    actions[args.action]()


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as error:
        raise SystemExit(error.returncode) from None
    except (OSError, ValueError) as error:
        raise SystemExit(str(error)) from None
