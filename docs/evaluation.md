# Методика оценки и экспериментов

## Корпус и независимость

`fixture` — 20 синтетических вакансий/22 требования; gold и replay происходят из общих
определений и проверяют pipeline, не качество LLM. `reviewed` — 25 frozen MIT-licensed
авторских источников, labels/rationales, source hashes, candidate и assessment date в
[data/evaluation/reviewed-v1.json](../data/evaluation/reviewed-v1.json).
Разметка написана и проверена по source отдельно от generator/replay/predictions.
Reviewer — Codex, один автоматизированный review, не human panel или независимый model benchmark.
20 источников пересекаются с fixture, пять добавляют сложные случаи. Изменение labels
требует нового review/revision/pin, не регенерации из ответов модели.

Fixture знает 20 reviewed hashes: остальные пять остаются provider_unavailable.
Команда сохраняет диагностику и завершается кодом 1. Нельзя заполнять failures из gold.
Результаты и ограничения: [каталог](../results/README.md).

## Метрики и ошибки

Каждая доля имеет numerator/denominator; нулевой знаменатель — null. Exact-key multiset
alignment расходует каждый gold максимум один раз, учитывает operator/branches/versions/
obligations/production/years, не использует fuzzy matching. Aliases намеренно различаются
до normalization. Type/evidence оцениваются после alignment.

| Показатель | Определение |
| --- | --- |
| Precision / recall | Aligned predictions / все predictions; aligned / все gold requirements |
| F1 | Гармоническое среднее при определённых precision и recall, иначе null |
| Type accuracy | Верный type / aligned pairs; отдельно MUST/PREFERRED и confusion matrix |
| Evidence accuracy | Точный gold span / aligned pairs |
| Unsupported-span rate | Неверные source slices / predicted items; это не semantic hallucination |
| Semantic unsupported | Неподтверждённые source-аннотациями claims / проверяемые claims; invalid span отдельно |
| Abstention precision/recall | Верные unknown / все unknown; верные unknown / ожидаемые unknown slots |
| Matching / false COVERED | Совпадение четырёх состояний; неверный COVERED / все COVERED |

Semantic review различает продукты, ANY/ALL, типы, positive years/production/version claims.
Валидная нерелевантная цитата остаётся неподтверждённой. Пропущенный predicate — abstention,
не positive hallucination. Конечный набор supporting spans не является универсальным entailment judge.
Filters/responsibilities имеют независимые one-to-one precision/recall. Abstention slots:
geography/mode/filters, years/production/experience obligation/production obligation каждого
требования; пропущенное требование также снижает recall. Matching на **gold requirements**
и sourced candidate изолирует matcher, не измеряет end-to-end matching с generated output.

Quality aggregates относятся к успешным cases; failed/not_attempted стоят рядом. All-failed
quality — null. Live `/evaluate` останавливает configuration после первой ошибки, другая
явно выбранная config имеет свою диагностику. API сохраняет report ID и возвращает error
status, CLI экспортирует до exit 1. Исторические reports/production rows не меняются.
`jobintel evaluate --run-id ID` и API reads не вызывают provider; UI хранит только ID.

Report содержит dataset/candidate/config/model/prompt/schema/taxonomy/source/code hashes,
UTC timestamps, predictions, per-case errors/counts. Без Git сохраняется Python source hash,
а commit/dirty неизвестны. Posting/provider-adapter/evaluation elapsed не равны provider-only
LLM time. Только фактически возвращённый usage учитывается, включая bounded retries.
Цена — датированная оценка с model/source/input-output USD rates, не billing reconciliation.
При неполном usage полный cost=null, известный priced usage показывается отдельно.

## Воспроизведение и инструменты

`make experiment-replay ARGS='--output local_data/experiments/new-run'` выполняет
fixture freeze → plan → run → rescore на reviewed corpus, сохраняя failures и exit 1.
`--dataset fixture` даёт исходную 20-case regression. Каталог должен быть новым;
повтор не перезаписывает output. `make experiment-rescore ARGS='--help'` пересчитывает
готовый report без ключей, provider и запросов; `make reports` рендерит опубликованные
русские таблицы из неизменённых JSON. S/V IDs сохраняются в [карте](acceptance_map.json), тестах/issues, UI IDs —
в [машинной карте](web_ui_workflows.json).

A — schema в prompt, свободный output с независимым аудитом; B — strict output + evidence;
C — B с deterministic taxonomy normalization. A без grounding не попадает в production.
B/C делают отдельные запросы на одинаковых snapshots: вариативность ответов мешает
приписывать разницу только normalization. Нельзя предполагать победу C.

`make network-experiment ARGS='--provider local'` и `--provider emulator` используют
существующие scoped services и reviewed subsets. Local: REV-01/23/25, B/C, pinned model,
8192 context, ≤2048 output. Emulator: REV-01, B/C, contract-schema-v2, ≤8192 output.
A для этих режимов не поддержан. `--cases` разрешён только при reviewed freezing;
 generator labels не приобретают independent=true. Reservations используют conservative
UTF-8 request bounds; это не измеренные tokens. Local cost/CPU power неизвестен,
emulator tokens/cost/inference time неизвестны. Платные hosted credentials не загружаются.

## Платные запросы и публикация

Hosted plan/run — существующий `jobintel experiment`, provider=openai; по умолчанию fake.
Config JSON требует минимум две A/B/C configurations, explicit model, max_calls,
max_input_tokens, max_output_tokens, budget_usd, pricing (model/source/date/input-output rates)
и authorization_reference. Reservation покрывает cases×configs и все token/cost bounds
до transport/request. Проверяйте актуальные цены. Reference не заменяет отдельного
разрешения пользователя на расходы. В CI и браузере платные запросы не запускаются.
Ключ — только secure runtime/secret file, store=false, verified proxy/TLS, fixed hosted endpoint.

Quota/rate-limit/network/model-identity/usage-limit failure останавливает последующие slots;
не начатые остаются not_attempted. Case-local schema/evidence/refusal остаются diagnostics.
Ошибки не превращаются в empty success, raw output bounded, error bodies/credentials исключены.
Atomic fsynced checkpoint сохраняет active case. Exit 1 означает сохранённые failures,
exit 2 — rejected preflight/input. `make experiment-resume` поддерживает только zero-cost
local/emulator с теми же corpus/config/code: uncertain active slot становится interrupted,
не повторяется, usage/time неизвестны. Hosted resume не разрешён автоматически.

`make experiment-audit` создаёт **неодобренный** draft. Reviewer проверяет каждый raw output,
prediction, failure, denominator, лицензию и приватность, указывает честную identity/method/
revision/timezone-aware timestamp после run. Source-label review — отдельная запись.
Pattern checks не заменяют содержательный review. `make experiment-publish` принимает только
complete report и одобренный audit его точного hash; stale audit отвергается.
Публикация сохраняет report/scores/audit/corpus/configuration links. README обновляется
только внутри LIVE-EXPERIMENTS markers; local/emulator не заменяют hosted section.
[Issue #9](https://github.com/newdarwindev/JobIntelAI/issues/9) закрывается только реальными
раздельно разрешёнными hosted измерениями и аудитом, не этим документационным изменением.
