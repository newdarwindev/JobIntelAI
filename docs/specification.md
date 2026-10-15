# Контракты JobIntel AI

Исходные требования: [brief](source_brief.txt). Текущая область включает согласованные
веб-интерфейсы, локальные окружения, Responses emulator и CPU inference.
Критерии реализации и завершения находятся в [issues](https://github.com/newdarwindev/JobIntelAI/issues).

## 1. Назначение

Превратить текст вакансии в проверяемые требования, сопоставить с источниками кандидата
и посчитать показатели выбранного корпуса. Утверждение требует источника; цитата сама
по себе не доказывает семантическую корректность. Выводы не описывают весь рынок труда.

## 2. Архитектура

FastAPI/argparse используют общие сервисы и транзакции SQLAlchemy; Pydantic v2 запрещает
лишние поля, Alembic управляет схемой. PostgreSQL 16 — целевое хранилище, SQLite — локальный
режим. Исходные snapshots, extraction runs, candidate revisions и match runs разделены,
поэтому повторный запуск не переписывает историю. Схема хранения определяется
[моделями](../src/jobintel/db.py) и [миграциями](../alembic/versions).
Диаграмма единственного основного пути находится в [README](../README.md).
Не нужны очереди, vector store, orchestration, OAuth/Sheets integration или SaaS-слой.

## 3. Основной путь

Реестр → HTTP либо ручной текст → неизменяемый snapshot → provider → schema/evidence guard
→ aliases → matching/аналитика/оценка → JSON/CSV. Синтетический demo не требует ключей.
При отказе HTTP предлагается ручной ввод. Browser rendering — отдельное необязательное
расширение, не обход ограничений доступа. UI использует настоящие мигрированные сервисы;
его [приёмка](web_ui_spec.md) отделена от качества модели.

### Сохранённые операции и партии

Browser mutation получает UUID Idempotency-Key: method/path/canonical body hash связывают
повтор с исходным запросом. Reservation создаётся до работы; domain writes и исходный
HTTP status/body сохраняются одной транзакцией. Повтор key возвращает saved result без
повторного handler/provider; другой body — conflict. Unkeyed API/CLI сохраняют прежнюю семантику.
GET /operations/{id} сообщает not-received/uncertain/committed/rejected и saved response,
no-store. Неопределённый commit, включая process loss, не разрешает повторное выполнение.
Completed handler counts не равны upstream request counts или качеству модели.

UI сначала согласует потерянный ответ чтением; retransmission сохраняет body/key.
В storage остаётся только opaque pending ID. Reload восстанавливает saved result;
POST /operations/{id}/cancel-unsent атомарно запрещает позднюю доставку unsent request,
но не отменяет существующую reservation. Lookup — приватные данные без payload logs.

Batch фиксирует job/source/run IDs и candidate revision, хранит только ID/state metadata.
Один явный проход обрабатывает ≤20 unfinished items и останавливается при failure/uncertainty.
Continuation не повторяет completed items/saved stages; exit обновляет authoritative
state либо явно показывает недоступность counters. Prior rejections сохраняются после reload.
Явный source replan меняет только unfinished items; matching требует captured revision.
Optional expected_snapshot_id guards отвергают stale source до snapshot replacement/provider;
explicit null при создании означает отсутствие source, omitted сохраняет legacy contract.

## 4. Данные и доступ

Репозиторий хранит только авторские/лицензированные синтетические примеры. Реальные вакансии,
URL, candidate records, переписка, notes и приватные результаты — в ignored `local_data/`
либо вне checkout. `.env` и БД игнорируются; ignore не удаляет уже tracked файлы.
Доступность URL не даёт права на crawling/перепубликацию. Не обходить CAPTCHA/anti-bot.
API не аутентифицирован: только loopback, один локальный пользователь; не выставлять публично.

Секреты поступают из runtime environment или read-only mounted file, не из CLI arguments,
Git, postings или image layers. Python не загружает `.env` автоматически.
`jobintel.outcomes` выдаёт JSON INFO после commit/rollback: outcome, storage IDs, hash,
время и allowlisted error code. Исключены names, URLs, bodies, response/error text;
SQLAlchemy скрывает bound parameters. Внешние middleware/custom SQL logs этой гарантией не покрыты.
Успешные источники и URL всё же остаются приватными данными в локальной БД.

## 5. Реестр

Обязательны `job_id`, `company`, `role`; точные поля и длины задаёт OpenAPI/Pydantic.
`applied` — true/false/unknown, не выводится из notes/status. CSV/JSON import атомарен.
Повтор одинаковых метаданных идемпотентен; тот же ID с изменениями — 409.
Конфликт canonical URL или casefold company+role между разными ID — 409 без потери строк.
Такая консервативная идентичность может потребовать ручного разрешения разных openings.
URL canonicalization сохраняет значимые query/path case/trailing slash, убирает fragment
и default port, приводит scheme/host к нижнему регистру; это не разрешение на fetch.

## 6. Acquisition и snapshots

Ручной text/HTML ограничен 200 000 символами. HTTP принимает credential-free HTTP(S)
со стандартными портами, валидным IDNA host и без control/whitespace в URL.
Каждый hop/retry заново проверяет весь DNS answer: private, loopback, link-local,
metadata, reserved, multicast, scoped/transition/mapped IPv6 запрещены. Соединение
прикреплено к публичному numeric IP с peer check; Host/SNI и TLS certificate проверяют
исходный hostname. HTTPS не понижается до HTTP; redirects не обходят проверку.

| Ограничение | По умолчанию / верхняя граница |
| --- | --- |
| Connect/DNS; read inactivity | 3/10 секунд; 5/10 секунд |
| Общий deadline с DNS/hops/waits | 20/60 секунд |
| Попытки на hop; redirects | 3; 3 (максимум 12 запросов в общем deadline) |
| Wire/decompressed bytes | по 200 000 |
| Backoff base; wait cap | 0,5/10 секунд; 2/10 секунд |

Retry только transient network/DNS/timeouts, 429 и 5xx в общем бюджете; Retry-After capped.
TLS, access/proxy refusal, invalid content/destination не повторяются. Зависший resolver
не продлевает ожидание вызывающего. Поддерживаются text/plain, text/html, XHTML;
UTF-8/UTF-8-SIG/ASCII/Latin-1/Windows-1252, без charset — строгий UTF-8.
Identity/gzip/zlib-deflate проверяются потоково; malformed/truncated/concatenated streams,
PDF/binary/NUL/invalid text, пустой/JS-only/CAPTCHA и oversize требуют ручного ввода.

HTML cleaner удаляет служебные элементы, предпочитает main/article и проверенные ATS selectors,
сохраняет формулировки/list/table/Unicode; это не универсальный ATS parser. Decoded raw text
с BOM сохраняется точно; clean hash — SHA-256 UTF-8. Новый raw при прежнем clean создаёт
новый snapshot; latest identical raw+clean+URL использует старый ID/time/status.
HTTP reuse ручного snapshot не меняет его provenance: отдельный attempt хранит HTTP hash/size/type.

`auto` учитывает inherited proxy/NO_PROXY и требует local destination DNS;
`direct` требует прямой доступ без выбранного proxy; `pinned-proxy` требует HTTP gateway,
принимающий numeric requests/CONNECT. `policy-proxy` требует доверенного administrator
JobIntel egress-v1 gateway: complete-answer DNS validation, десятисекундные одноразовые pins,
revalidation перед upstream connect. Это доверие администратору, не криптографическая attestation.
Gateway запускается только на разрешённом direct-egress host без inherited outbound proxy,
разрешает точные hosts/стандартные порты, максимум 1024 leases, не следует redirects.
Его credential-free control channel допускается только в защищённой сети/loopback.
Explicit proxy modes требуют proxy на каждом hop; отказ не переключает на direct.
Authenticated/HTTPS/SOCKS proxy не поддерживаются. Исходные CA/прокси сохраняются;
scoped CA дополняет trust, TLS verification не отключается. Не пересылаются cookies/auth/referrer.

Readiness проверяет capability, не доступность каждого URL; неподдерживаемый proxy — 503
`proxy_capability`. Fetch success — 201; access/CAPTCHA — 403; oversize — 413;
MIME/compression — 415; destination/text/redirect — 422; DNS/TLS/proxy/5xx — 502;
исчерпанные 429 — 503; deadline — 504. Ошибка содержит безопасный code/retryable/manual_fallback.
Attempts сохраняют fetch/sequence/time/redirect/retry/wait/error и только success snapshot link;
до HTTP status=null. Failed bodies/headers не хранятся. Failure сохраняет прежний usable source.
Snapshot+attempt commit атомарен; SQL failure — sanitized 503 с rollback всего изменения.
Отсутствующий job — 404, URL — 422 без HTTP. Import/extract/startup сами ничего не fetch.
История неизменяема через сервис, но прямой SQL этой гарантией не покрыт.

## 7. Extraction и совместимость

Provider получает неизменённый clean source и versioned config. До persistence проверяются
schema и точные evidence slices `[start:end]` по Unicode code points, end exclusive,
включая non-BMP. Любая неверная цитата отменяет весь run, старый остаётся доступен.
Responsibilities отделены от требований; geography/work_mode/filters тоже требуют evidence.
Company address не задаёт географию роли; negated/conditional/conflicting mode — unknown.
Поддерживаемая grammar английских predicates консервативна: неизвестное не угадывается.

Тип требования и experience/production obligation — отдельные оси. EXPERIENCE не становится
MUST. Production preference: PREFERRED и explicit_production_required=false; отсутствие:
UNKNOWN/null. Years и obligation требуют источника; поддержаны числа zero–ten и числовые
диапазоны, неподдерживаемое — null. Confidence информационен и не заменяет evidence.
Версии привязаны к skill branch: product/comparator/numeric version/raw wording и вложенный
source span. Нельзя удалять version constraint либо переносить его на другую ветвь.

Новые данные — schema v2. `stored_schema_version` отличает проекцию legacy от нового run.
v1 читается без изменения JSON: неподтверждённые geography/mode/production становятся
unknown, experience obligation — UNKNOWN, version wording сохраняется. Unknown schema
version завершается явно. Старые labels нельзя объявлять v2 без новой source-аннотации;
старые frozen reports сохраняют hashes и совместимое rescoring.

Fixture отвечает только на известные synthetic hashes. Hosted OpenAI использует Responses
Structured Outputs; local CPU — отдельный Chat Completions protocol/schema sampler,
поскольку pinned engine Responses не соблюдает требуемую schema. Emulator исполняет
контракт по authored responses, без inference. Ни один отказ не подменяется fixture.
Schema/malformed/truncated output допускает одну validation retry; transport/refusal/evidence
не повторяются скрыто. Refusal/grounding — 422, provider/schema/quota — 502, timeout — 504;
retryability передаётся отдельно. OpenAI timeout 1–120 секунд, default 30.

Run provenance сохраняет source/snapshot, provider/model requested+returned, config/prompt/
schema/taxonomy/request hashes и доступные response IDs/usage/timing. Неизмеренное — null.
Failure attempts добавляются отдельно; savepoint и внешний commit не допускают частичного
успеха. SQLite использует явный BEGIN; rollback проверяется также в PostgreSQL.

## 8. Нормализация

[Taxonomy](../data/taxonomy.json) задаёт exact trim/casefold aliases. Postgres → PostgreSQL,
K8s → Kubernetes; AWS и AWS Bedrock различны. Неизвестные термины остаются дословными.
ANY/ALL и source skill terms сохраняются даже после alias-dedup до одной ветви.
Не объединять несовместимые версии, продукты или неоднозначные aliases.

## 9. Candidate matching

Профиль содержит независимые current_capability и production_evidence, source/quote и
явный complete (default false). Источник — предоставленное свидетельство, не внешняя
проверка credential. Нет вывода из employer name. Одинаковый validated payload внутри
profile переиспользует revision, изменение добавляет неизменяемую revision.

| Условие | Состояние |
| --- | --- |
| Strong и production не требуется либо confirmed | COVERED |
| Basic либо strong с limited/none требуемым production | PARTIAL |
| Явное отсутствие capability / записи при complete=true | MISSING |
| Неполные данные, противоречия, unknown требуемая ось | UNKNOWN |

ANY выбирает достаточную ветвь, ALL требует все. Версии кандидата без sourced version
predicates остаются UNKNOWN. Tenure использует подтверждённые датированные интервалы
[начало, конец), объединяет overlapping/adjacent периоды по canonical skill/kind,
считает calendar-anniversary years и дробный остаток. Будущие/неполные даты не доказывают
стаж. Minimum допускает known lower bound; maximum требует tenure_complete=true.
Короткий положительный complete tenure — PARTIAL; zero/absence при полноте или превышение
maximum — MISSING; incomplete deficit — UNKNOWN. Production years не заменяют capability.

Eligibility сравнивает только точные нормализованные scope/value и validity dates:
location/work_authorization/travel/residency/attendance. Expiry включительно; denial — MISSING;
противоречия/невалидная дата — UNKNOWN. Нет географической иерархии или вывода о citizenship.
Отсутствие неизвестно до явного eligibility_complete для kind. OTHER разделяет проверенный
предикат того же evidence span; неподдерживаемое OTHER abstains.

Match связывает точные extraction/source/profile revision/hash и assessment date.
Неверная пара profile/revision — 404, stale expected_run_id — 409; исторические revisions
остаются выбираемыми. Legacy full-profile payload совместим. UI хранит выбранные IDs,
не приватные тела. Новая source/extraction исключает старое matching из текущего вида,
не удаляя исторический match run.

## 10. Аналитика и экспорт

Обычный выбор: latest snapshot и latest successful extraction на нём, UTC time+ID tie-break.
Ошибка не заменяет usable result; empty success включается в N. Gap selection требует
profile_id+revision_id и latest match именно этой revision/current extraction; неполный
выбор — 422, неизвестный — 404. Повторы не умножают вакансии. Empty matched extraction
входит в matched_jobs_N. Данные пересчитываются при чтении, no-store, без provider calls.

Skill N — разные успешно извлечённые вакансии; gap N — matched_jobs_N выбранной revision.
Skill/type/category counts допускают пересечения. ANY — отдельная группа, ALL — отдельные
ветви. Gap identity сохраняет branches/operator/type/category/obligations/years/versions;
разные контексты одной вакансии могут иметь разные состояния, их суммы не обязаны давать N.
Нулевой знаменатель → null. applied фильтрует точное boolean; remote=true — grounded remote,
false — hybrid/onsite, unknown исключён. AND-фильтры пересчитывают все знаменатели.
Positive response не выводится из status/notes и требует отдельного typed import field.

Coverage buckets взаимоисключающие, в порядке приоритета: successful, successfully_empty,
acquisition_failed (нет source), pending_source, extraction_failed (нет current success),
stale (старый source извлекался), pending_extraction. Сумма — registered_selected;
excluded=registered_total−registered_selected, successful_N=первые два, unmatched=successful_N−matched_N.
Latest acquisition/extraction failure — отдельные пересекающиеся счётчики; не замена buckets.
Ordering attempts использует server recorded_at, sequence/ID; legacy — исходный timestamp,
без выдумывания истории. Window selection ограничивает число SQL запросов, но память/время
всё равно растут с корпусом: это не гарантия большого масштаба.

Export читает только сохранённое. History требует historical=true и explicit run/match IDs;
profile selection должен согласовываться со всеми match IDs. Evidence — одна source/run view.
JSON сохраняет exact strings/null, source/run/profile/hash и знаменатели, ANY/ALL arrays,
metadata/filters/responsibilities. Unmatched=null, вычисленный UNKNOWN — явная строка.
CSV UTF-8/CRLF с quoting каждого поля; первый visible =,+,-,@ (включая ведущие Unicode
control/format/whitespace) получает защитный apostrophe, остальные символы не меняются.
Nested objects — JSON в ячейке; null/empty в CSV совпадают, поэтому точный roundtrip — JSON.
Empty success даёт header-only CSV и metadata в companion JSON. Legacy skills сохраняет
семь первых колонок и исходные filenames. Частные exports в checkout разрешены только
в ignored путях с проверкой Git; browser downloads локальны. Installed distribution не требует Git.

## 11. Оценка

Определения метрик, review, failure accounting, бюджеты и публикация находятся только в
[методике](evaluation.md). `/evaluate` сохраняет точный report для чтения без повторных
запросов; ошибки не становятся empty success. Реальные live experiments для #9
требуют отдельного разрешения и не заменяются fixture/emulator/CPU результатами.

## 12. Интерфейсы

Актуальные endpoints/поля — в локальном `/docs` (OpenAPI); CLI — `jobintel --help` и
`jobintel experiment --help`. Общий контракт ошибок: безопасный code/message/retryable,
без private body/exception text. Missing — 404, prerequisite/stale — 409, input — 422,
неготовая БД/commit failure — 503. Health требует миграций, не выполняет paid readiness call.
`/ui/config` сообщает поддерживаемые configs, execution identity, budgets/readiness/actions,
без secrets/hosted endpoints. Hosted readiness подтверждает конфигурацию, не доступ upstream.

### Ограниченные каталоги и страницы

Навигация браузера использует `/v2`; прежние bulk endpoints сохраняются для API/CLI.
Списки возвращают `catalogue_version: 2`, `page.limit`, `page.has_more`, `page.next_cursor`.
По умолчанию 20 записей, `limit=1..100`; cursor непрозрачен и связан с коллекцией,
владельцем, поиском и фильтром. Неверные параметры, неизвестные query keys и чужой
cursor дают 422. Cursor содержит IDs, а не bodies; он не является авторизацией.

| Каталог | Ограниченные данные и порядок |
| --- | --- |
| `/v2/jobs` | Registry metadata, latest snapshot ID/hash/time, run ID/config/count; job ID по возрастанию |
| `/v2/jobs/{job}/snapshots` | Metadata и run count; fetched time/ID по убыванию |
| `/v2/jobs/{job}/acquisition-attempts` | IDs, URLs и typed outcomes; created time/ID по убыванию |
| `/v2/jobs/{job}/extraction-attempts` | IDs, config и typed outcomes; created time/ID по убыванию |
| `/v2/jobs/{job}/snapshots/{snapshot}/runs` | ID/config/schema/count; created time/ID по убыванию |
| `/v2/candidates/{profile}/revisions` | Revision/profile/time; created time/ID по убыванию |
| `/v2/evaluation-runs` | ID/dataset/status/time; created time/ID по убыванию |

Unique ID разрешает совпадающие timestamps; keyset pages не используют offset.
Это свежие reads, не frozen DB snapshot: новые backdated records могут появиться позже,
а source/extraction меняют membership. Refresh первой страницы обнаруживает leading records.
`q` — literal case-insensitive substring job ID либо normalized company/role; `%`/`_`
буквальны. `pipeline`: all/Awaiting source/Source ready/Extracted. Общие totals не зависят
от фильтра/страницы. Empty success входит в extracted; новая source исключает старый run.

Registry выполняет два SELECT независимо от размера корпуса; SQLite дополнительно BEGIN.
Metadata lists выбирают не более `limit + 1` rows без raw/clean source, profile/prediction
bodies и вложенных unbounded runs. Точный текущий posting читается через `/jobs/{id}`;
saved source — `/v2/jobs/{job}/snapshots/{snapshot}`, extraction — `/v2/extraction-runs/{run}`.
Связь job/snapshot проверяется, unknown/mismatch даёт 404. List не вызывает provider и не пишет БД.
UI15 проверяет поиск, страницы и точные reads; explicit batch planning перечисляет компактные
pages отдельно от навигации, сохраняя лимит исполнения 20 и исключение completed operations.
`make catalogue-check` сравнивает v1/v2 на одинаковом синтетическом корпусе в SQLite/PostgreSQL;
[измерения](issue-evidence/47/catalogue-performance.md) сохраняют SQL/bytes и source/config hashes.

## 13. Окружения и CPU

`make env ARGS='--help'` — единый lifecycle fixture/emulator/local. `run` владеет временными
resources и удаляет их при success/failure/SIGINT/SIGTERM/timeout; lifetime 30–7200 секунд
включает provisioning. Отдельный watchdog очищает после SIGKILL. Ownership+Compose labels
нужны перед удалением; existing/foreign project не присваивается. Нельзя global Docker prune.
`up --persistent` явно сохраняет session; stop сохраняет volumes, start проверяет ownership
и заново определяет ports; reset требует project и удаляет только его данные.
Legacy named runtime dev/demo/openai/contract-test/local-inference остаётся доступен
через `python scripts/runtime.py --help`; его проекты независимы от managed leases.

Origin/proxy/CA добавляются только с --acquisition. Emulator control endpoint loopback,
fixed development token не обеспечивает production auth; hosted secrets туда не передаются.
Unknown authored hashes fail. Scenarios/retry counts определены исполняемыми тестами.
Local engine internal-only, 2 CPU/5 GiB, один slot, context 8192, output ≤2048;
host Linux amd64, минимум 8 GiB RAM и 20 GiB диска. Ввод >6000 символов или >64 непустых
строк явно отвергается; меньший всё ещё может не поместиться в token context. Никакого clipping.

Единственный источник image/model/weight/license pins — [local_model.py](../src/jobintel/local_model.py).
llama.cpp — MIT, Qwen2.5-1.5B-F16 — Apache-2.0, 3 093 669 376 байт весов.
`make model-prepare` атомарно загружает и проверяет веса/лицензию под lock с deadline,
обновляет registry token между объектами. Corrupt cache не заменяется без явного удаления.
Stop/reset сохраняют общий cache; offline требует подготовленных wheels и весов.
Source-bound sampling выбирает целые source lines, затем строгий validator перепроверяет
output; это ограничивает spans, но не гарантирует semantics. Usage/engine/HTTP timing
различаются, CPU cost неизвестен. Diagnostics содержат только разрешённые counts/IDs/hashes,
service states и bounded protocol checks, без TLS keys/private bodies/environments.
