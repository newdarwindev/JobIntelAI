# Восстановление mutations: измеренные наблюдения

Источник: [Запуск GitHub Actions](https://github.com/newdarwindev/JobIntelAI/actions/runs/39441877552) · проверенный коммит `5384741088d5201efcd9fe63b3dcc75e2e4f6f43`.
SHA-256 исходного содержимого: `90ea58bd7c7d24a69f78da5537a307ae6140226d281f610d6e7e11a62b0d591c`. [Машинные наблюдения](mutation-comparison.json).

Авторский synthetic ввод, реальные API/БД; платные hosted запросы не выполнялись. Эти проверки не измеряют качество модели.

Каждая строка получена из успешного UI13: наблюдаемые browser requests, lookup сохранённой операции и API history/catalogues. Потеря до доставки даёт два POST с одним key, после commit — восстановление чтением. Отдельный conflicting-body probe возвращает 409. Completed handler executions не равны числу upstream requests или retries.

Snapshot/extraction/registry/revision/evaluation counts взяты из API. У matching нет каталога: число rows явно неизвестно, вместо него проверяются точный saved match ID и immutable response. Integration tests считают domain records напрямую. Unsent cancellation и validation rejection не запускают handler. Восстановление display/status не добавляет POST/run.

| Viewport | Mutation | Граница потери | Исход | Browser POST | Conflicting probes | Завершённые handlers | Записей до → после | Точный saved ID |
| --- | --- | --- | --- | ---: | ---: | ---: | --- | --- |
| desktop-chromium | registry | before_delivery | not_received → committed | 2 | 1 | 1 | 1 → 2 | Новый результат не сохранён |
| desktop-chromium | snapshot | before_delivery | not_received → committed | 2 | 1 | 1 | 1 → 2 | e6fe3e1f1d8d4a99bde1b1b7ac4ab466 |
| desktop-chromium | candidate | before_delivery | not_received → committed | 2 | 1 | 1 | 0 → 1 | 1eceeb1400b743118a11aada6c560857 |
| desktop-chromium | extract | before_delivery | not_received → committed | 2 | 1 | 1 | 1 → 2 | 386952e51d034fd3b7701f7a54acf46e |
| desktop-chromium | match | before_delivery | not_received → committed | 2 | 1 | 1 | Не перечислено → Не перечислено | 7759c07509544ce09d1cb6b7dbb4ef11 |
| desktop-chromium | evaluate | before_delivery | not_received → committed | 2 | 1 | 1 | 1 → 2 | 1a0806fbca1d4aaca3281c17e48d18c0 |
| desktop-chromium | fetch | before_delivery | not_received → committed | 2 | 1 | 1 | 2 → 3 | c4ab8a9f83d74299b64e802622725484 |
| desktop-chromium | registry | after_commit | committed → committed | 1 | 1 | 1 | 2 → 3 | Новый результат не сохранён |
| desktop-chromium | snapshot | after_commit | committed → committed | 1 | 1 | 1 | 3 → 4 | e8b0b0d8157e44b6885e36fc91570aa7 |
| desktop-chromium | candidate | after_commit | committed → committed | 1 | 1 | 1 | 0 → 1 | 9d5763f37b6d47719108034ff300c15b |
| desktop-chromium | extract | after_commit | committed → committed | 1 | 1 | 1 | 2 → 3 | 0dd07ab748eb433e9942ee7f4dfaf191 |
| desktop-chromium | match | after_commit | committed → committed | 1 | 1 | 1 | Не перечислено → Не перечислено | 9b98f665ff1f49b7ab9909843c7babb1 |
| desktop-chromium | evaluate | after_commit | committed → committed | 1 | 1 | 1 | 2 → 3 | 12d6d07748ca48b6a560ad6d82f2ae7d |
| desktop-chromium | fetch | after_commit | committed → committed | 1 | 1 | 1 | 4 → 5 | 15570858bd2b4fe5b63a4945b63898c7 |
| desktop-chromium | extract | display_read_lost | committed/display_pending → committed | 1 | 0 | 1 | Не перечислено → Не перечислено | 1d576ce9bf224582b28c2529f78dff34 |
| desktop-chromium | snapshot | unsent_reload_cancel | not_received → rejected | 1 | 1 | 0 | 5 → 5 | Новый результат не сохранён |
| desktop-chromium | extract | provider_in_flight | uncertain → committed | 1 | 0 | 1 | Не перечислено → Не перечислено | 337e94433bea455089b21562a9f6d1b1 |
| desktop-chromium | extract | lookup_lost_reload | uncertain → committed | 1 | 0 | 1 | 6 → 6 | dc2856a655d740bba8bb940dbc43910b |
| desktop-chromium | candidate | validation_rejected | rejected → rejected | 1 | 0 | 0 | 0 → 0 | Новый результат не сохранён |
| mobile-chromium | registry | before_delivery | not_received → committed | 2 | 1 | 1 | 1 → 2 | Новый результат не сохранён |
| mobile-chromium | snapshot | before_delivery | not_received → committed | 2 | 1 | 1 | 1 → 2 | 2ba792cbb0704f50a62c0978dd7a827d |
| mobile-chromium | candidate | before_delivery | not_received → committed | 2 | 1 | 1 | 0 → 1 | f5494a647e12454e9224b2f9b31f01f1 |
| mobile-chromium | extract | before_delivery | not_received → committed | 2 | 1 | 1 | 1 → 2 | 29f004030d464be9946e6b6dc56b811b |
| mobile-chromium | match | before_delivery | not_received → committed | 2 | 1 | 1 | Не перечислено → Не перечислено | d3ce4ced63b342879d126a25c258f9be |
| mobile-chromium | evaluate | before_delivery | not_received → committed | 2 | 1 | 1 | 1 → 2 | 91d94a135b8a473eb6c49a2ac5c3c949 |
| mobile-chromium | fetch | before_delivery | not_received → committed | 2 | 1 | 1 | 2 → 3 | c8a6616f763c47bb92280559736c4ce2 |
| mobile-chromium | registry | after_commit | committed → committed | 1 | 1 | 1 | 2 → 3 | Новый результат не сохранён |
| mobile-chromium | snapshot | after_commit | committed → committed | 1 | 1 | 1 | 3 → 4 | 08074b5957584084af5ac7b4a6640784 |
| mobile-chromium | candidate | after_commit | committed → committed | 1 | 1 | 1 | 0 → 1 | ecba3c8f3a9145258a3ac5170cdab801 |
| mobile-chromium | extract | after_commit | committed → committed | 1 | 1 | 1 | 2 → 3 | 6b002aed5f2a4a5a9e5fad35b0a39d82 |
| mobile-chromium | match | after_commit | committed → committed | 1 | 1 | 1 | Не перечислено → Не перечислено | 4824d55fa0294066afc689186b4cb5a7 |
| mobile-chromium | evaluate | after_commit | committed → committed | 1 | 1 | 1 | 2 → 3 | aa47a9a0f1834ef794f4231904e9a291 |
| mobile-chromium | fetch | after_commit | committed → committed | 1 | 1 | 1 | 4 → 5 | b632d809e31c41ac8c0f752bf74abb4e |
| mobile-chromium | extract | display_read_lost | committed/display_pending → committed | 1 | 0 | 1 | Не перечислено → Не перечислено | d75f0efa4d874509aec247403e1c0cb1 |
| mobile-chromium | snapshot | unsent_reload_cancel | not_received → rejected | 1 | 1 | 0 | 5 → 5 | Новый результат не сохранён |
| mobile-chromium | extract | provider_in_flight | uncertain → committed | 1 | 0 | 1 | Не перечислено → Не перечислено | 8dcb4a2e00204330bfa63e62a927c61e |
| mobile-chromium | extract | lookup_lost_reload | uncertain → committed | 1 | 0 | 1 | 6 → 6 | 7614ca74c526429f81ec706fd071527c |
| mobile-chromium | candidate | validation_rejected | rejected → rejected | 1 | 0 | 0 | 0 → 0 | Новый результат не сохранён |

[Desktop UI13](../../ui-recordings/UI13-desktop-chromium.webm) · [Mobile UI13](../../ui-recordings/UI13-mobile-chromium.webm)

Прежние snapshots/extractions/revisions/matches/evaluations прочитаны без изменений. In-flight case использует отдельный Responses emulator и bounded delay. Unknown outcome остаётся uncertain до подтверждения lookup, без повторного execution. Browser storage хранит только opaque operation ID.
