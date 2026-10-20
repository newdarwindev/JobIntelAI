# Измеренное сравнение запросов и размера ответов реестра

actual migrated SQLite/PostgreSQL, authored fixture replay, no paid calls

[Полные измерения и provenance](catalogue-performance.json). Legacy endpoint сохранён для совместимости, навигация использует v2. Для каждого размера алгоритмы читают одинаковые frozen synthetic records. V2 выполняет два SELECT, SQLite дополнительно BEGIN. Bounded SQL/payload не содержит source/extraction bodies. Локальное время сохранено в JSON; это не throughput или production-scale benchmark.

| База | Вакансий | Legacy SQL / bytes | Bounded SQL / bytes | Возвращено вакансий |
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

Воспроизведение: `make catalogue-check`. Команда создаёт собственную временную PostgreSQL, если disposable TEST_DATABASE_URL не задан. Отдельная PostgreSQL schema и временная SQLite изолируют каждый запуск и удаляются после него. Ввод — авторский SYN-01 fixture replay. Empty success, latest source и history отдельно проверяют integration tests и UI15.

[Запись UI15 desktop](../../ui-recordings/UI15-desktop-chromium.webm) · [Запись UI15 mobile](../../ui-recordings/UI15-mobile-chromium.webm)
