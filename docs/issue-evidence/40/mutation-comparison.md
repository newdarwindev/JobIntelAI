# Восстановление mutations: измеренные наблюдения

Источник: [Запуск GitHub Actions](https://github.com/newdarwindev/JobIntelAI/actions/runs/38726964867) · проверенный коммит `2b4a88b20258341cc7594dc76491ae716c0c7e8b`.
SHA-256 исходного содержимого: `2df4acda6f4e4b1fca56f2c5397f11f01efd23ac54976934c809bfbd7bc5c59d`. [Машинные наблюдения](mutation-comparison.json).

Авторский synthetic ввод, реальные API/БД; платные hosted запросы не выполнялись. Эти проверки не измеряют качество модели.

Каждая строка получена из успешного UI13: наблюдаемые browser requests, lookup сохранённой операции и API history/catalogues. Потеря до доставки даёт два POST с одним key, после commit — восстановление чтением. Отдельный conflicting-body probe возвращает 409. Completed handler executions не равны числу upstream requests или retries.

Snapshot/extraction/registry/revision/evaluation counts взяты из API. У matching нет каталога: число rows явно неизвестно, вместо него проверяются точный saved match ID и immutable response. Integration tests считают domain records напрямую. Unsent cancellation и validation rejection не запускают handler. Восстановление display/status не добавляет POST/run.

| Viewport | Mutation | Граница потери | Исход | Browser POST | Conflicting probes | Завершённые handlers | Записей до → после | Точный saved ID |
| --- | --- | --- | --- | ---: | ---: | ---: | --- | --- |
| desktop-chromium | registry | before_delivery | not_received → committed | 2 | 1 | 1 | 1 → 2 | Новый результат не сохранён |
| desktop-chromium | snapshot | before_delivery | not_received → committed | 2 | 1 | 1 | 1 → 2 | 6a1b0a7964634a8fb2eb67d4bd98f912 |
| desktop-chromium | candidate | before_delivery | not_received → committed | 2 | 1 | 1 | 0 → 1 | aa318689d6834186959ecf50f0325911 |
| desktop-chromium | extract | before_delivery | not_received → committed | 2 | 1 | 1 | 1 → 2 | 9b720dbaaa854c5a9cd4a79f89622963 |
| desktop-chromium | match | before_delivery | not_received → committed | 2 | 1 | 1 | Не перечислено → Не перечислено | c09802bfa8984faabc20c87b880779ea |
| desktop-chromium | evaluate | before_delivery | not_received → committed | 2 | 1 | 1 | 1 → 2 | c72e91f4d13f45f1b77332157dd79ffd |
| desktop-chromium | fetch | before_delivery | not_received → committed | 2 | 1 | 1 | 2 → 3 | 71ff8d2e3e9345e183b64aee9ec2b56c |
| desktop-chromium | registry | after_commit | committed → committed | 1 | 1 | 1 | 2 → 3 | Новый результат не сохранён |
| desktop-chromium | snapshot | after_commit | committed → committed | 1 | 1 | 1 | 3 → 4 | 4ad6c65444d944a2b0143da0459af266 |
| desktop-chromium | candidate | after_commit | committed → committed | 1 | 1 | 1 | 0 → 1 | b903148571e74160a7d7d9e1c8fc7b15 |
| desktop-chromium | extract | after_commit | committed → committed | 1 | 1 | 1 | 2 → 3 | a3ee20e449514f97a53c6f26a255ee8d |
| desktop-chromium | match | after_commit | committed → committed | 1 | 1 | 1 | Не перечислено → Не перечислено | 1f3dfd525b834a2cad6a9c2fedd8458d |
| desktop-chromium | evaluate | after_commit | committed → committed | 1 | 1 | 1 | 2 → 3 | 08a60b659c4040b7ade0e9ccceffa07b |
| desktop-chromium | fetch | after_commit | committed → committed | 1 | 1 | 1 | 4 → 5 | 58029011715a42d39111b8b6f80b7c5d |
| desktop-chromium | extract | display_read_lost | committed/display_pending → committed | 1 | 0 | 1 | Не перечислено → Не перечислено | ecb10c5f142e4cd6ae76633083647e7d |
| desktop-chromium | snapshot | unsent_reload_cancel | not_received → rejected | 1 | 1 | 0 | 5 → 5 | Новый результат не сохранён |
| desktop-chromium | extract | provider_in_flight | uncertain → committed | 1 | 0 | 1 | Не перечислено → Не перечислено | 556673faf8524f808a6eebe50d412fb1 |
| desktop-chromium | extract | lookup_lost_reload | uncertain → committed | 1 | 0 | 1 | 6 → 6 | 186c3816018048aba3ef7f19ddb63c0f |
| desktop-chromium | candidate | validation_rejected | rejected → rejected | 1 | 0 | 0 | 0 → 0 | Новый результат не сохранён |
| mobile-chromium | registry | before_delivery | not_received → committed | 2 | 1 | 1 | 1 → 2 | Новый результат не сохранён |
| mobile-chromium | snapshot | before_delivery | not_received → committed | 2 | 1 | 1 | 1 → 2 | 362ee18815ea417a847737877fbb1769 |
| mobile-chromium | candidate | before_delivery | not_received → committed | 2 | 1 | 1 | 0 → 1 | 9dadd75c67624d489cc7a48a603edc90 |
| mobile-chromium | extract | before_delivery | not_received → committed | 2 | 1 | 1 | 1 → 2 | 216392d9cef6435d909866f14e6f6abe |
| mobile-chromium | match | before_delivery | not_received → committed | 2 | 1 | 1 | Не перечислено → Не перечислено | 7b5b355d7f1641599f92c560e918fae1 |
| mobile-chromium | evaluate | before_delivery | not_received → committed | 2 | 1 | 1 | 1 → 2 | c54c88e4e6a0439d977f8af52f03476c |
| mobile-chromium | fetch | before_delivery | not_received → committed | 2 | 1 | 1 | 2 → 3 | f98853e4eb3b4b6398814534c5733bd6 |
| mobile-chromium | registry | after_commit | committed → committed | 1 | 1 | 1 | 2 → 3 | Новый результат не сохранён |
| mobile-chromium | snapshot | after_commit | committed → committed | 1 | 1 | 1 | 3 → 4 | 0555b33c8d3347eaa07127ae1c2bfe01 |
| mobile-chromium | candidate | after_commit | committed → committed | 1 | 1 | 1 | 0 → 1 | c0dd9e1ed95f4188b894b64c83091df8 |
| mobile-chromium | extract | after_commit | committed → committed | 1 | 1 | 1 | 2 → 3 | bb9ca49a2c8b4c10a9acf0c4c1515e5b |
| mobile-chromium | match | after_commit | committed → committed | 1 | 1 | 1 | Не перечислено → Не перечислено | 547ef39e1f944f19839e3aeba1ed5385 |
| mobile-chromium | evaluate | after_commit | committed → committed | 1 | 1 | 1 | 2 → 3 | f269f305e4f94076ae1bc9a58a5335d0 |
| mobile-chromium | fetch | after_commit | committed → committed | 1 | 1 | 1 | 4 → 5 | f2224ac61a254d9a87649a4a1b215269 |
| mobile-chromium | extract | display_read_lost | committed/display_pending → committed | 1 | 0 | 1 | Не перечислено → Не перечислено | 7c0a20760a164ee0bd0da3b194829e6d |
| mobile-chromium | snapshot | unsent_reload_cancel | not_received → rejected | 1 | 1 | 0 | 5 → 5 | Новый результат не сохранён |
| mobile-chromium | extract | provider_in_flight | uncertain → committed | 1 | 0 | 1 | Не перечислено → Не перечислено | 47a6a930047f468f8b259c775617c455 |
| mobile-chromium | extract | lookup_lost_reload | uncertain → committed | 1 | 0 | 1 | 6 → 6 | 7db7a3a0d58b4204945021fbf5f99af9 |
| mobile-chromium | candidate | validation_rejected | rejected → rejected | 1 | 0 | 0 | 0 → 0 | Новый результат не сохранён |

[Desktop UI13](../../ui-recordings/UI13-desktop-chromium.webm) · [Mobile UI13](../../ui-recordings/UI13-mobile-chromium.webm)

Прежние snapshots/extractions/revisions/matches/evaluations прочитаны без изменений. In-flight case использует отдельный Responses emulator и bounded delay. Unknown outcome остаётся uncertain до подтверждения lookup, без повторного execution. Browser storage хранит только opaque operation ID.
