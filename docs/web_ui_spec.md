# Приёмка веб-интерфейса

UI — HTML/CSS/JavaScript FastAPI `/ui/`, без внешних assets. Браузер вызывает настоящие
мигрированные сервисы; доменные [контракты](specification.md) не подменяются static success.
Fixture/emulator — authored coverage, CPU — реальная inference, hosted — только при
отдельном разрешении. Неизвестный fixture hash завершается явно.

## Экраны и ожидаемый результат

| Экран | Существенная приёмка | Journey IDs |
| --- | --- | --- |
| Обзор/реестр | Empty onboarding, atomic CSV/JSON import, typed applied, duplicates/conflicts без частичной записи, поиск/фильтры и переходы | UI01, UI08–UI11 |
| Источники/извлечение | Ручной text/HTML, URL/manual recovery, immutable source/hash/time, история attempts/runs, stale invalidation, точная Unicode-подсветка, raw/normalized, ANY/ALL, metadata/versions/obligations/responsibilities и provenance export | UI02, UI03, UI07, UI09–UI11 |
| Кандидат | Strict sourced JSON, явная полнота, immutable revision save/reload/select, четыре состояния, tenure/eligibility и contradiction abstention, separate capability/production, matching/export выбранной revision и extraction | UI04, UI09–UI11 |
| Аналитика | Persisted n/N и gap denominator, coverage/overlaps, applied/grounded remote, revision selection после refresh, JSON/CSV parity, formula safety, stale/history selection | UI05, UI09–UI11 |
| Оценка | Поддерживаемые configs из API, reject empty selection, fixture/reviewed datasets, numerator/denominator/null, failures и per-case diagnostics, reload report по ID/после refresh, экспорт режима | UI06, UI09–UI11 |

Все экраны: labelled controls, keyboard access, responsive desktop/mobile, deep links,
busy/error/empty states и escaped input. HTML не исполняется. Ошибка сохраняет prior usable
source/run и несохранённый редактор, не показывает успех с пустыми данными. Provider status
refresh не заменяет text/format. Выбранные profile/revision/evaluation IDs переживают refresh;
private bodies не копируются в browser storage. Revision switch очищает текущие projections,
matching отправляет inspected run ID; stale — 409, отсутствующий saved revision — явная ошибка.

UI02 проходит реальный production HTTP transport через scoped policy-proxy/origin и
verified HTTPS: redirect success, inert script, 403/JS-only, сохранённая attempt history,
прежний extraction/unsaved manual text, manual recovery и reload. Diagnostics доказывают
TLS handshake и single-use numeric pin за hostname CONNECT. UI08 проверяет gateway
capability/readiness и manual capture при unsupported proxy/503. Это не Internet crawling.
UI03 проверяет non-BMP offsets, metadata evidence, preferred production и version predicates;
пока candidate version evidence не поддержан, UI04 показывает UNKNOWN.

UI07 использует отдельный Responses emulator: success, refusal/invalid evidence (422),
quota/server/malformed/connection close (502), timeout (504), retryability и request counts:
malformed output — два запроса, остальные failures — один. History сохраняется, success
восстанавливает работу. Control routes существуют только в launcher. Browser interception
ограничен Unicode read fixture и browser-to-API connection failure.

UI09–UI11 используют отдельные нормальные PostgreSQL APIs без demo/reset routes:
import → verified acquisition → extraction → evidence highlight/export → revision save/reload
→ match → analytics/export → saved evaluation. UI09 отвергает unseen source без потери
старого run. UI10 сохраняет реальные emulator failures. UI11 делает CPU inference,
загружает frozen REV-01/23/25 evaluation со всеми ошибками, останавливает/запускает engine,
проверяет readiness/recovery и сохранность истории. Model quality отделено от service pass.
`/ui/config` задаёт supported configs, execution labels, readiness, budgets/actions, без secrets.
Hosted controls покрыты fake HTTP, что не доказывает доступность платного сервиса.

## Покрытие и записи

Единственный список journeys/projects и связь с S/V IDs/секциями спецификации —
[web_ui_workflows.json](web_ui_workflows.json), executable journeys — [tests/e2e](../tests/e2e).
Новые flows добавляются в оба источника; нельзя удалять/ослаблять проверки ради сокращения prose.
Записи покрывают все workflow/project, successful attempt, source/video hashes, timestamp,
attempt index и честный local/Actions origin в [manifest](ui-recordings/manifest.json).

`make ui-check` выполняет все desktop/mobile journeys и публикует только полный успешный
набор. Failures/traces остаются diagnostics. После финального изменения входов hash gate
нужны свежие записи. Изменения одной документации/renderer не разрешают обойти этот gate.
Actions сохраняет artifacts при любом исходе; default-branch trusted upstream publisher
обновляет README/видео. Fork/PR read-only, без pull_request_target и обхода branch policy.
Публикация сохраняет Git identity по [AGENTS](../AGENTS.md).

Runner использует существующие owned leases: fresh loopback ports, bounded deadline,
явные migrations/readiness, scoped cleanup после failures/signals/SIGKILL, порядок API →
origin/provider. Persistent volumes и checksum-pinned licensed weights переживают teardown;
TLS keys/private environments не входят в diagnostics. Незавершённый checkpoint или
непроверенный rescore не считается успешным browser evidence.
