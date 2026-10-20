# Восстановление mutations: измеренные наблюдения

Источник: [Запуск GitHub Actions](https://github.com/newdarwindev/JobIntelAI/actions/runs/39452006080) · проверенный коммит `e348949bd47f6b11fcf7917930524d1debcc1f76`.
SHA-256 исходного содержимого: `90ea58bd7c7d24a69f78da5537a307ae6140226d281f610d6e7e11a62b0d591c`. [Машинные наблюдения](mutation-comparison.json).

Авторский synthetic ввод, реальные API/БД; платные hosted запросы не выполнялись. Эти проверки не измеряют качество модели.

Каждая строка получена из успешного UI13: наблюдаемые browser requests, lookup сохранённой операции и API history/catalogues. Потеря до доставки даёт два POST с одним key, после commit — восстановление чтением. Отдельный conflicting-body probe возвращает 409. Completed handler executions не равны числу upstream requests или retries.

Snapshot/extraction/registry/revision/evaluation counts взяты из API. У matching нет каталога: число rows явно неизвестно, вместо него проверяются точный saved match ID и immutable response. Integration tests считают domain records напрямую. Unsent cancellation и validation rejection не запускают handler. Восстановление display/status не добавляет POST/run.

| Viewport | Mutation | Граница потери | Исход | Browser POST | Conflicting probes | Завершённые handlers | Записей до → после | Точный saved ID |
| --- | --- | --- | --- | ---: | ---: | ---: | --- | --- |
| desktop-chromium | registry | before_delivery | not_received → committed | 2 | 1 | 1 | 1 → 2 | Новый результат не сохранён |
| desktop-chromium | snapshot | before_delivery | not_received → committed | 2 | 1 | 1 | 1 → 2 | d5f3f29c1a134433bba07230c346da63 |
| desktop-chromium | candidate | before_delivery | not_received → committed | 2 | 1 | 1 | 0 → 1 | 36454a44663548db85751eb1d4233ac5 |
| desktop-chromium | extract | before_delivery | not_received → committed | 2 | 1 | 1 | 1 → 2 | e2c1c9029d974effafc6a49ff2e51cd9 |
| desktop-chromium | match | before_delivery | not_received → committed | 2 | 1 | 1 | Не перечислено → Не перечислено | ca2afce4546a4f41b2f6cf4fb30d5bd8 |
| desktop-chromium | evaluate | before_delivery | not_received → committed | 2 | 1 | 1 | 1 → 2 | b9cb8d12d4a947d0937c61737ddfe059 |
| desktop-chromium | fetch | before_delivery | not_received → committed | 2 | 1 | 1 | 2 → 3 | 74c422b2fb4844299cbdee61b55e61d2 |
| desktop-chromium | registry | after_commit | committed → committed | 1 | 1 | 1 | 2 → 3 | Новый результат не сохранён |
| desktop-chromium | snapshot | after_commit | committed → committed | 1 | 1 | 1 | 3 → 4 | 6a41200bc72a45ffa9fca0b23c69a068 |
| desktop-chromium | candidate | after_commit | committed → committed | 1 | 1 | 1 | 0 → 1 | d684a347d37b4e4ca41a8912323ea9ef |
| desktop-chromium | extract | after_commit | committed → committed | 1 | 1 | 1 | 2 → 3 | efe439e26a574db09a4aa787cb30b249 |
| desktop-chromium | match | after_commit | committed → committed | 1 | 1 | 1 | Не перечислено → Не перечислено | 9cec955100ee4c79939cf61127d12cca |
| desktop-chromium | evaluate | after_commit | committed → committed | 1 | 1 | 1 | 2 → 3 | baef45f59087408ea50a6afbae5cb2a3 |
| desktop-chromium | fetch | after_commit | committed → committed | 1 | 1 | 1 | 4 → 5 | f6f7ec4a57c740df843dd3fc07ef5aad |
| desktop-chromium | extract | display_read_lost | committed/display_pending → committed | 1 | 0 | 1 | Не перечислено → Не перечислено | bc27d0bc846445e99a1df35cf18c9722 |
| desktop-chromium | snapshot | unsent_reload_cancel | not_received → rejected | 1 | 1 | 0 | 5 → 5 | Новый результат не сохранён |
| desktop-chromium | extract | provider_in_flight | uncertain → committed | 1 | 0 | 1 | Не перечислено → Не перечислено | 829dbc013f904b0d8e34a90d320d95de |
| desktop-chromium | extract | lookup_lost_reload | uncertain → committed | 1 | 0 | 1 | 6 → 6 | d8384efc2d4f45309ffcb231c84e1b95 |
| desktop-chromium | candidate | validation_rejected | rejected → rejected | 1 | 0 | 0 | 0 → 0 | Новый результат не сохранён |
| mobile-chromium | registry | before_delivery | not_received → committed | 2 | 1 | 1 | 1 → 2 | Новый результат не сохранён |
| mobile-chromium | snapshot | before_delivery | not_received → committed | 2 | 1 | 1 | 1 → 2 | e5e495d0b6f04965a528e82b1f48abe2 |
| mobile-chromium | candidate | before_delivery | not_received → committed | 2 | 1 | 1 | 0 → 1 | bda0d76191564ee18c79e212c6d06ff7 |
| mobile-chromium | extract | before_delivery | not_received → committed | 2 | 1 | 1 | 1 → 2 | 41015a37b5824848a6f2e34c9c107052 |
| mobile-chromium | match | before_delivery | not_received → committed | 2 | 1 | 1 | Не перечислено → Не перечислено | 316e4295bcdb4012ab2878345ef4596f |
| mobile-chromium | evaluate | before_delivery | not_received → committed | 2 | 1 | 1 | 1 → 2 | e61f34dde2e9429ea4f73f0fce7855f2 |
| mobile-chromium | fetch | before_delivery | not_received → committed | 2 | 1 | 1 | 2 → 3 | 02aa932956334cc6aaa4314de163d17a |
| mobile-chromium | registry | after_commit | committed → committed | 1 | 1 | 1 | 2 → 3 | Новый результат не сохранён |
| mobile-chromium | snapshot | after_commit | committed → committed | 1 | 1 | 1 | 3 → 4 | f25d6bade53346d29032bb0c8c69c32e |
| mobile-chromium | candidate | after_commit | committed → committed | 1 | 1 | 1 | 0 → 1 | 5fcbba8a23344e5281fc580ced7c0a38 |
| mobile-chromium | extract | after_commit | committed → committed | 1 | 1 | 1 | 2 → 3 | 11c8a009932c40f1800c17e25d55e356 |
| mobile-chromium | match | after_commit | committed → committed | 1 | 1 | 1 | Не перечислено → Не перечислено | 2d316aa619664a64bb66874664bf70c0 |
| mobile-chromium | evaluate | after_commit | committed → committed | 1 | 1 | 1 | 2 → 3 | 30946aa16f9c4e1d9d748901a4a724ee |
| mobile-chromium | fetch | after_commit | committed → committed | 1 | 1 | 1 | 4 → 5 | 3781bb85ae7f423f9fbca60f5393d8e8 |
| mobile-chromium | extract | display_read_lost | committed/display_pending → committed | 1 | 0 | 1 | Не перечислено → Не перечислено | 5ad66ecd7c474f56be4870d1aa3a6a5e |
| mobile-chromium | snapshot | unsent_reload_cancel | not_received → rejected | 1 | 1 | 0 | 5 → 5 | Новый результат не сохранён |
| mobile-chromium | extract | provider_in_flight | uncertain → committed | 1 | 0 | 1 | Не перечислено → Не перечислено | 26b531fca38147a78c6845ca5dccc12f |
| mobile-chromium | extract | lookup_lost_reload | uncertain → committed | 1 | 0 | 1 | 6 → 6 | 3dce29b331674910b1fabd1efce992f9 |
| mobile-chromium | candidate | validation_rejected | rejected → rejected | 1 | 0 | 0 | 0 → 0 | Новый результат не сохранён |

[Desktop UI13](../../ui-recordings/UI13-desktop-chromium.webm) · [Mobile UI13](../../ui-recordings/UI13-mobile-chromium.webm)

Прежние snapshots/extractions/revisions/matches/evaluations прочитаны без изменений. In-flight case использует отдельный Responses emulator и bounded delay. Unknown outcome остаётся uncertain до подтверждения lookup, без повторного execution. Browser storage хранит только opaque operation ID.
