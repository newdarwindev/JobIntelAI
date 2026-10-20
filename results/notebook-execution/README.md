# Notebook execution evidence

Кратко: реальный offline fixture run, точный пересчёт сохранённых scores и отказ
preflight без создания output. Эти результаты не измеряют качество LLM.

Source commit: `6070290c5ffea5290c0e36798a148d992c6ca19f`; dirty: `False`.
Python source SHA-256: `3aa7b3f38a69304d6ff65dfe952611d65c6edfbacf1a0a37091c1e0f908335e5`.

| Scenario | Visible outcome | Underlying evidence |
| --- | --- | --- |
| Fixture | succeeded; fake evidence; no measured tokens/cost | [manifest](fixture/manifest.json), [report](fixture/report.json), [comparison](fixture/comparison.md) |
| Saved report | succeeded; no new inference; scores byte-identical | [manifest](saved/manifest.json), [scores](saved/scores.json) |
| Bad corpus pin | exit 2, corpus_checksum; no output allocated | [structured outcomes](evidence.json) |

| Test result | Passed | Failed | Errors | Skipped |
| --- | ---: | ---: | ---: | ---: |
| unit12.xml | 31 | 0 | 0 | 0 |
| unit311.xml | 31 | 0 | 0 | 0 |
| full12.xml | 757 | 0 | 0 | 154 |

The full [machine-readable evidence](evidence.json) retains actual outcomes and
test counts. Skips are not implementation proof. Fresh-kernel checks run separately
under Python 3.11/3.12 in Actions and publish `notebook-kernel.json`.

Reproduce from the repository root into a new output directory:

```bash
python -m scripts.notebook_execution_evidence --output work/notebook-evidence
```

Training execution is a separately implemented capability in issue #81. This
interface refuses an unavailable training runner before allocating output.

## Fresh-kernel measurements

Both environments executed the real kernel checks from the clean source commit above,
with database/HTTP access forbidden and exact saved-score reproduction.

| Local environment | Evidence |
| --- | --- |
| Python 3.11.16 | [kernel result](kernel311.json), [31-pass JUnit](unit311.xml) |
| Python 3.12.14 | [kernel result](kernel12.json), [31-pass JUnit](unit12.xml) |
| Full Python 3.12 checks | [757-pass / 154-skip JUnit](full12.xml) |

Local skipped tests are not acceptance evidence. Remote PostgreSQL/container
verification is tracked in the implementing PR and issue #77.
