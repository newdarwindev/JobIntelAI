# Результаты и ограничения

Это сохранённые измерения на авторских синтетических данных, не оценка рынка труда.
Исходные JSON, timestamps, hashes и dirty provenance не переписываются при переводе.
`make reports` обновляет русское представление без запросов к провайдеру.

| Режим | Что измерено | Исходные результаты |
| --- | --- | --- |
| Fixture, 20 вакансий | Raw alignment 18/22, normalized 22/22; shared gold/replay проверяют pipeline, не LLM | [JSON](fixture_evaluation.json), [пример n/N](example_skill_counts.csv) |
| Reviewed fixture, 25 случаев | По 20 success/5 provider_unavailable на конфигурацию; diagnostics сохранены | [JSON](reviewed_fixture_evaluation.json), [русская сводка](reviewed_fixture_evaluation.txt), [A/B/C таблица](experiments/reviewed-fake/comparison.md), [report](experiments/reviewed-fake/report.json), [scores](experiments/reviewed-fake/scores.json) |
| Исходный fake experiment | Полный 20-case A/B/C regression; только C нормализует aliases | [report](experiments/fake/report.json), [scores](experiments/fake/scores.json) |
| CPU, исходная генерация | 0/3 valid: два invalid_evidence, timeout; 4 service checks успешны | [initial.json](local-inference/initial.json) |
| CPU, source-bound генерация | 1/3 valid, два invalid_evidence; recall 1/2, type 0/1 на успешном случае, пропущен Postgres/неверный Python type | [source-bound.json](local-inference/source-bound.json) |
| CPU, network B/C | Шесть реальных запросов, у каждой config 2/3 valid, REV-23 invalid_evidence; successful-case recall 1/2, precision/type/evidence 1/1; по 1753/478 input/output tokens с failure | [таблица](network-experiments/local/comparison.md), [report](network-experiments/local/report.json), [scores](network-experiments/local/scores.json), [audit](network-experiments/local/audit.json), [service evidence](network-experiments/local/service-evidence.json) |
| Emulator, network B/C | Два authored HTTP ответа; raw Postgres даёт 1/2 alignment, normalized 2/2. Без inference/usage/cost | [таблица](network-experiments/emulator/comparison.md), [report](network-experiments/emulator/report.json), [scores](network-experiments/emulator/scores.json), [audit](network-experiments/emulator/audit.json) |

Failure не входит в знаменатель успешных quality metrics, но остаётся в report.
Неизмеренный cost/LLM latency — null. Fixture time — время replay. Три CPU cases не
доказывают качество на произвольных вакансиях или причинный эффект normalization/prompt.
Source review и output/privacy audits — отдельные автоматизированные проверки Codex.
CPU reports сохраняют development git_dirty=true; source hash связывает исходный run
с реализацией, не превращая его задним числом в clean-commit run.

Hardware timings зависят от cache/конкуренции: исходная подготовка весов заняла 661,09 с;
source-bound fresh stack/recreation — 39,84/16,24 с, unseen request — 59,31 с/2173 tokens,
cgroup peak — 708 747 264 байта. Initial — 61,95/21,42 с и 1 448 337 408 байт.
Это warm-cache accounting, не cold boot и не полная host RAM. Требования к машине —
[в спецификации](../docs/specification.md#13-окружения-и-cpu), методика — [отдельно](../docs/evaluation.md).

Runtime exports находятся в ignored `results/generated/`; приватный корпус сюда не коммитится.
Live release gate и его статус: [issue #9](https://github.com/newdarwindev/JobIntelAI/issues/9).
