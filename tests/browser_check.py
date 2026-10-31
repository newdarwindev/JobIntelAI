"""Optional visual smoke: install Playwright/Chromium, then run this script locally."""

import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from uuid import uuid4

from playwright.sync_api import sync_playwright

from jobintel.store import Store


def main():
    with tempfile.TemporaryDirectory() as directory:
        database = Path(directory) / "browser.sqlite"
        store = Store(str(database))
        key = str(uuid4())
        store.reserve(key, "synthetic")
        job = "We require <img src=x onerror=window.pwned=1> Python."
        record = store.save(
            key,
            "synthetic",
            job,
            "I built Python APIs with <script>window.pwned=1</script>.",
            None,
            "synthetic-test/no-inference",
            [
                {
                    "requirement": "<img src=x onerror=window.pwned=1> Python",
                    "status": "UNKNOWN",
                    "reason": "<script>window.pwned=1</script>",
                    "job": {
                        "quote": "Python",
                        "start": job.index("Python"),
                        "end": job.index("Python") + len("Python"),
                    },
                    "candidate": None,
                }
            ],
        )
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        env = {**os.environ, "JOBINTEL_DB": str(database)}
        server = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "jobintel.app:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
            ],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(
                    headless=True,
                    executable_path=os.environ.get("JOBINTEL_CHROMIUM", "/usr/bin/chromium"),
                    args=["--no-sandbox", "--disable-dev-shm-usage"],
                )
                for name, width, height in [("desktop", 1440, 900), ("mobile", 390, 844)]:
                    page = browser.new_page(viewport={"width": width, "height": height})
                    for _ in range(30):
                        try:
                            page.goto(f"http://127.0.0.1:{port}/#{record['id']}")
                            break
                        except Exception:
                            time.sleep(0.1)
                    page.wait_for_selector("#output:not([hidden])")
                    assert page.locator("#items article").count() == 1
                    assert page.locator("#items img, #items script").count() == 0
                    assert page.evaluate("window.pwned === undefined")
                    assert page.evaluate(
                        "document.documentElement.scrollWidth <= window.innerWidth"
                    )
                    page.screenshot(path=f"{directory}/{name}.png", full_page=True)
                    print(f"{name}: rendered, no overflow, injected markup inert")
                    page.close()
                browser.close()
        finally:
            server.terminate()
            server.wait(timeout=10)


if __name__ == "__main__":
    main()
