from pathlib import Path

DATA = Path(__file__).resolve().parents[2] / "data"


def seed(client):
    response = client.post(
        "/jobs/import", json={"csv_text": (DATA / "sample_registry.csv").read_text()}
    )
    assert response.status_code == 200
    return response


def test_end_to_end_manual_fixture_matching_analytics_and_evaluation(client):
    assert client.get("/health").json()["database"] == "ok"
    assert seed(client).json()["imported"] == 20
    assert seed(client).json()["duplicates"] == 20
    text = (DATA / "sample_jobs/SYN-01.txt").read_text()
    response = client.post("/jobs/SYN-01/snapshots", json={"text": text})
    assert response.status_code == 201
    snapshot_id = response.json()["snapshot_id"]
    assert (
        client.post("/jobs/SYN-01/snapshots", json={"text": text}).json()["snapshot_id"]
        == snapshot_id
    )
    extraction = client.post("/jobs/SYN-01/extract", json={}).json()
    assert extraction["snapshot_id"] == snapshot_id
    assert extraction["requirements"][1]["skills"] == ["PostgreSQL"]
    for item in extraction["requirements"]:
        evidence = item["evidence"]
        assert text[evidence["start"] : evidence["end"]] == evidence["quote"]
    candidate = (DATA / "sample_candidate.json").read_text()
    match = client.post(
        "/jobs/SYN-01/match", content=candidate, headers={"content-type": "application/json"}
    )
    assert match.status_code == 200
    assert {m["status"] for m in match.json()["matches"]} == {"COVERED", "UNKNOWN"}
    assert client.get("/analytics/skills").json()["N"] == 1
    evaluation = client.post("/evaluate", json={})
    assert evaluation.status_code == 200
    assert evaluation.json()["dataset_size"] == 20
    assert (
        evaluation.json()["results"][0]["metrics"]["precision"]
        < evaluation.json()["results"][1]["metrics"]["precision"]
    )
    assert evaluation.json()["results"][1]["tokens"] is None


def test_new_snapshot_never_reuses_old_extraction(client):
    seed(client)
    text = (DATA / "sample_jobs/SYN-01.txt").read_text()
    client.post("/jobs/SYN-01/snapshots", json={"text": text})
    assert client.post("/jobs/SYN-01/extract", json={}).status_code == 200
    client.post("/jobs/SYN-01/snapshots", json={"text": "A changed posting."})
    assert client.get("/jobs/SYN-01").json()["extraction"] is None
    assert client.get("/analytics/skills").json()["N"] == 0
    assert client.post("/jobs/SYN-01/extract", json={}).status_code == 501
    assert (
        client.post("/jobs/SYN-01/match", json={"profile_id": "x", "evidence": []}).status_code
        == 409
    )


def test_import_conflict_rolls_back_entire_batch(client):
    jobs = [
        {"job_id": "one", "company": "Demo", "role": "Engineer"},
        {"job_id": "two", "company": "demo", "role": "engineer"},
    ]
    assert client.post("/jobs/import", json={"jobs": jobs}).status_code == 409
    assert client.get("/jobs/one").status_code == 404
    assert client.post("/jobs/import", json={"jobs": jobs[:1]}).status_code == 200
    assert (
        client.post("/jobs/import", json={"jobs": [{**jobs[0], "role": "Other"}]}).status_code
        == 409
    )


def test_errors_and_explicit_fetch_stub(client):
    assert client.get("/jobs/missing").status_code == 404
    assert client.post("/jobs/import", json={}).status_code == 422
    assert (
        client.post(
            "/jobs/import",
            json={"csv_text": "job_id,company,role,applied\nx,Demo,Engineer,maybe\n"},
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/jobs/import",
            json={
                "jobs": [
                    {
                        "job_id": "x",
                        "company": "Demo",
                        "role": "Engineer",
                        "official_url": "https://example.com/job",
                    }
                ]
            },
        ).status_code
        == 200
    )
    assert client.post("/jobs/x/fetch").status_code == 501
    assert client.post("/jobs/x/extract", json={}).status_code == 409
