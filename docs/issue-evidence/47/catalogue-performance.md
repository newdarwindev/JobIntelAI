# Measured registry query and payload comparison

actual migrated SQLite/PostgreSQL, authored fixture replay, no paid calls

[Complete machine-readable measurements and provenance](catalogue-performance.json). The legacy route remains available for compatibility; browser navigation uses v2. Both routes read the same frozen synthetic records within each corpus size. Two SELECTs serve v2 at every size; SQLite additionally emits BEGIN. Source and extraction bodies are absent from the bounded SQL/payload. Local elapsed times are retained in JSON and are not throughput or production-scale claims.

| Database | Jobs | Legacy SQL / bytes | Bounded SQL / bytes | Returned jobs |
| --- | ---: | ---: | ---: | ---: |
| sqlite | 1 | 5 / 2,392 | 3 / 591 | 1 |
| sqlite | 10 | 32 / 23,830 | 3 / 4,465 | 10 |
| sqlite | 20 | 62 / 47,660 | 3 / 8,775 | 20 |
| sqlite | 100 | 302 / 238,300 | 3 / 8,839 | 20 |
| sqlite | 500 | 1502 / 1,191,900 | 3 / 8,840 | 20 |
| postgres | 1 | 4 / 2,392 | 2 / 591 | 1 |
| postgres | 10 | 31 / 23,830 | 2 / 4,465 | 10 |
| postgres | 20 | 61 / 47,660 | 2 / 8,775 | 20 |
| postgres | 100 | 301 / 238,300 | 2 / 8,839 | 20 |
| postgres | 500 | 1501 / 1,191,900 | 2 / 8,840 | 20 |

Reproduce with `TEST_DATABASE_URL` pointing to a disposable PostgreSQL database: `.venv/bin/python -m scripts.catalogue_benchmark`. A fresh PostgreSQL schema and temporary SQLite database isolate every run; cleanup removes them. All inputs use authored SYN-01 fixture replay. Successful empty/latest-source/history behavior is verified separately by the integration and UI15 journeys.

[Desktop UI15 recording](../../ui-recordings/UI15-desktop-chromium.webm) · [Mobile UI15 recording](../../ui-recordings/UI15-mobile-chromium.webm)
