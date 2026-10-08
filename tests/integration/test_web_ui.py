"""UI contract boundaries, source history, and explicit corpus slicing."""

from pathlib import Path

DATA = Path(__file__).resolve().parents[2] / "data"


def test_ui_is_packaged_and_demo_reset_is_not_exposed(client):
    assert client.get("/ui/").status_code == 200
    assert "Evidence workspace" in client.get("/ui/").text
    assert client.get("/ui/app.js").status_code == 200
    assert client.get("/ui/styles.css").status_code == 200
    assert client.get("/ui/config").json() == {
        "demo": False,
        "provider": "fixture",
        "live_llm": False,
    }
    assert client.get("/ui/fixtures").status_code == 404
    assert client.post("/ui/reset").status_code == 405


def test_registry_history_retains_old_runs_and_latest_view_abstains(client):
    jobs = [
        {"job_id": "history", "company": "Authored History", "role": "Engineer", "applied": True}
    ]
    assert client.post("/jobs/import", json={"jobs": jobs}).status_code == 200
    source = (DATA / "sample_jobs/SYN-01.txt").read_text()
    old_snapshot = client.post("/jobs/history/snapshots", json={"text": source}).json()[
        "snapshot_id"
    ]
    old_run = client.post("/jobs/history/extract", json={}).json()["run_id"]
    assert client.get("/jobs").json()["jobs"][0]["extraction"]["run_id"] == old_run
    new_snapshot = client.post(
        "/jobs/history/snapshots", json={"text": "Authored changed source."}
    ).json()["snapshot_id"]
    assert client.get("/jobs").json()["jobs"][0]["extraction"] is None
    history = client.get("/jobs/history/history").json()["snapshots"]
    assert [item["id"] for item in history] == [new_snapshot, old_snapshot]
    assert history[0]["runs"] == []
    assert history[1]["runs"][0]["run_id"] == old_run
    assert history[1]["clean_text"].strip() == source.strip()
    assert client.get("/jobs/missing/history").status_code == 404


def test_applied_slices_recompute_success_denominator_and_exclude_unknown(client):
    source = (DATA / "sample_jobs/SYN-01.txt").read_text()
    jobs = [
        {"job_id": key, "company": f"Authored {key}", "role": "Engineer", "applied": applied}
        for key, applied in [("yes", True), ("no", False), ("unknown", None), ("pending", True)]
    ]
    client.post("/jobs/import", json={"jobs": jobs})
    for job in jobs[:3]:
        client.post(f"/jobs/{job['job_id']}/snapshots", json={"text": source})
        client.post(f"/jobs/{job['job_id']}/extract", json={})
    assert client.get("/analytics/skills").json()["N"] == 3
    for applied in ["true", "false"]:
        report = client.get(f"/analytics/skills?applied={applied}").json()
        assert report["N"] == 1
        assert all(row["N"] == row["n"] == 1 for row in report["skills"])
    assert client.get("/analytics/skills?applied=maybe").status_code == 422


def test_profile_validation_rejects_unsourced_claims_without_database_writes(client):
    payload = {
        "profile_id": "authored-profile",
        "evidence": [
            {
                "skill": "Python",
                "current_capability": "strong",
                "production_evidence": "confirmed",
                "source": "synthetic://proof",
                "quote": "Explicit authored proof.",
            }
        ],
    }
    assert client.post("/candidate/validate", json=payload).json()["complete"] is False
    payload["evidence"][0]["source"] = ""
    assert client.post("/candidate/validate", json=payload).status_code == 422
    assert client.get("/jobs").json()["jobs"] == []
