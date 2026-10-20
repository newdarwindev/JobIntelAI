# Восстановление mutations: измеренные наблюдения

Источник: [Запуск GitHub Actions](https://github.com/newdarwindev/JobIntelAI/actions/runs/38727794951) · проверенный коммит `aefc151fc1acbe15e7a09ee8b9db4f865f406271`.
SHA-256 исходного содержимого: `08428f1651ed32c95b511669e49458604c9197c7db3b43b6f9666d82e2e6c18c`. [Машинные наблюдения](mutation-comparison.json).

Авторский synthetic ввод, реальные API/БД; платные hosted запросы не выполнялись. Эти проверки не измеряют качество модели.

Каждая строка получена из успешного UI13: наблюдаемые browser requests, lookup сохранённой операции и API history/catalogues. Потеря до доставки даёт два POST с одним key, после commit — восстановление чтением. Отдельный conflicting-body probe возвращает 409. Completed handler executions не равны числу upstream requests или retries.

Snapshot/extraction/registry/revision/evaluation counts взяты из API. У matching нет каталога: число rows явно неизвестно, вместо него проверяются точный saved match ID и immutable response. Integration tests считают domain records напрямую. Unsent cancellation и validation rejection не запускают handler. Восстановление display/status не добавляет POST/run.

| Viewport | Mutation | Граница потери | Исход | Browser POST | Conflicting probes | Завершённые handlers | Записей до → после | Точный saved ID |
| --- | --- | --- | --- | ---: | ---: | ---: | --- | --- |
| desktop-chromium | registry | before_delivery | not_received → committed | 2 | 1 | 1 | 1 → 2 | Новый результат не сохранён |
| desktop-chromium | snapshot | before_delivery | not_received → committed | 2 | 1 | 1 | 1 → 2 | fbb099dddf1643388705abbf9907853d |
| desktop-chromium | candidate | before_delivery | not_received → committed | 2 | 1 | 1 | 0 → 1 | 5970adc9ecc846829fc0d33076486079 |
| desktop-chromium | extract | before_delivery | not_received → committed | 2 | 1 | 1 | 1 → 2 | b13aa6f31bb043e1ad4ea998bea06942 |
| desktop-chromium | match | before_delivery | not_received → committed | 2 | 1 | 1 | Не перечислено → Не перечислено | 311ba6bfba48424daba7e2e9d9767afa |
| desktop-chromium | evaluate | before_delivery | not_received → committed | 2 | 1 | 1 | 1 → 2 | c20ea8c707704f95bcce6cf8a5b835fa |
| desktop-chromium | fetch | before_delivery | not_received → committed | 2 | 1 | 1 | 2 → 3 | 7181d1ad26b54d3bae8358cfb2dcdd9d |
| desktop-chromium | registry | after_commit | committed → committed | 1 | 1 | 1 | 2 → 3 | Новый результат не сохранён |
| desktop-chromium | snapshot | after_commit | committed → committed | 1 | 1 | 1 | 3 → 4 | f59c06bcd6834dd88742627d73d20227 |
| desktop-chromium | candidate | after_commit | committed → committed | 1 | 1 | 1 | 0 → 1 | e44fd99f899f43c89de18c2174c312c4 |
| desktop-chromium | extract | after_commit | committed → committed | 1 | 1 | 1 | 2 → 3 | b171f736a62740049bafb1bb5f058204 |
| desktop-chromium | match | after_commit | committed → committed | 1 | 1 | 1 | Не перечислено → Не перечислено | 041b0ce4b3a64092850d40651b0ebd40 |
| desktop-chromium | evaluate | after_commit | committed → committed | 1 | 1 | 1 | 2 → 3 | d688d59e8afb4dbbb9a38d4f32ac73b6 |
| desktop-chromium | fetch | after_commit | committed → committed | 1 | 1 | 1 | 4 → 5 | 480f96b333dd4d2d8c61d0826280952a |
| desktop-chromium | extract | display_read_lost | committed/display_pending → committed | 1 | 0 | 1 | Не перечислено → Не перечислено | 642db4d215df42b49057748c68b06f5d |
| desktop-chromium | snapshot | unsent_reload_cancel | not_received → rejected | 1 | 1 | 0 | 5 → 5 | Новый результат не сохранён |
| desktop-chromium | extract | provider_in_flight | uncertain → committed | 1 | 0 | 1 | Не перечислено → Не перечислено | 133b15117149486289362f1af928df43 |
| desktop-chromium | extract | lookup_lost_reload | uncertain → committed | 1 | 0 | 1 | 6 → 6 | 3bad076128884ae4a3f3d5d6ff5a7197 |
| desktop-chromium | candidate | validation_rejected | rejected → rejected | 1 | 0 | 0 | 0 → 0 | Новый результат не сохранён |
| mobile-chromium | registry | before_delivery | not_received → committed | 2 | 1 | 1 | 1 → 2 | Новый результат не сохранён |
| mobile-chromium | snapshot | before_delivery | not_received → committed | 2 | 1 | 1 | 1 → 2 | dd99c62584f64efab804267e3aa65121 |
| mobile-chromium | candidate | before_delivery | not_received → committed | 2 | 1 | 1 | 0 → 1 | bcb79ea722194d4e8058921a2b60870d |
| mobile-chromium | extract | before_delivery | not_received → committed | 2 | 1 | 1 | 1 → 2 | f9729a4cb14b480d83ee8cd011f2131d |
| mobile-chromium | match | before_delivery | not_received → committed | 2 | 1 | 1 | Не перечислено → Не перечислено | 5cc227efa9f04ed0b6ebc54d54fab5f4 |
| mobile-chromium | evaluate | before_delivery | not_received → committed | 2 | 1 | 1 | 1 → 2 | 0c4fd727efd34e94ac96dc11fb61d241 |
| mobile-chromium | fetch | before_delivery | not_received → committed | 2 | 1 | 1 | 2 → 3 | e1f20f35970840ac9ee56367fd2415a2 |
| mobile-chromium | registry | after_commit | committed → committed | 1 | 1 | 1 | 2 → 3 | Новый результат не сохранён |
| mobile-chromium | snapshot | after_commit | committed → committed | 1 | 1 | 1 | 3 → 4 | df29ade7bdc642779efefe0d6c3f794d |
| mobile-chromium | candidate | after_commit | committed → committed | 1 | 1 | 1 | 0 → 1 | 12a91aa2ac2941c89ac606b9048122a9 |
| mobile-chromium | extract | after_commit | committed → committed | 1 | 1 | 1 | 2 → 3 | f5077e657eb545a4be57518fb6a941eb |
| mobile-chromium | match | after_commit | committed → committed | 1 | 1 | 1 | Не перечислено → Не перечислено | b9ff85428fa54cdd93ec136c0b54e9fd |
| mobile-chromium | evaluate | after_commit | committed → committed | 1 | 1 | 1 | 2 → 3 | 23b7533c482b48ff95b94619f588161e |
| mobile-chromium | fetch | after_commit | committed → committed | 1 | 1 | 1 | 4 → 5 | c17ca19122544ff8a87771e55d10945c |
| mobile-chromium | extract | display_read_lost | committed/display_pending → committed | 1 | 0 | 1 | Не перечислено → Не перечислено | 4649de722c684a73afadcdbf8f87124d |
| mobile-chromium | snapshot | unsent_reload_cancel | not_received → rejected | 1 | 1 | 0 | 5 → 5 | Новый результат не сохранён |
| mobile-chromium | extract | provider_in_flight | uncertain → committed | 1 | 0 | 1 | Не перечислено → Не перечислено | f817ad9097ba4bb88323a439c855c2b9 |
| mobile-chromium | extract | lookup_lost_reload | uncertain → committed | 1 | 0 | 1 | 6 → 6 | b18cd01b41b242c4a0e276cfca501231 |
| mobile-chromium | candidate | validation_rejected | rejected → rejected | 1 | 0 | 0 | 0 → 0 | Новый результат не сохранён |

[Desktop UI13](../../ui-recordings/UI13-desktop-chromium.webm) · [Mobile UI13](../../ui-recordings/UI13-mobile-chromium.webm)

Прежние snapshots/extractions/revisions/matches/evaluations прочитаны без изменений. In-flight case использует отдельный Responses emulator и bounded delay. Unknown outcome остаётся uncertain до подтверждения lookup, без повторного execution. Browser storage хранит только opaque operation ID.
