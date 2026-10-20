# Восстановление mutations: измеренные наблюдения

Источник: [Запуск GitHub Actions](https://github.com/newdarwindev/JobIntelAI/actions/runs/39437770672) · проверенный коммит `7cc99839cd97e2a8c3d9a83a95dfc0ebae3af060`.
SHA-256 исходного содержимого: `dc134a9714a84967c0e4ac05fe13dc7a32deda88049ea185f0b7599d84cbd5b5`. [Машинные наблюдения](mutation-comparison.json).

Авторский synthetic ввод, реальные API/БД; платные hosted запросы не выполнялись. Эти проверки не измеряют качество модели.

Каждая строка получена из успешного UI13: наблюдаемые browser requests, lookup сохранённой операции и API history/catalogues. Потеря до доставки даёт два POST с одним key, после commit — восстановление чтением. Отдельный conflicting-body probe возвращает 409. Completed handler executions не равны числу upstream requests или retries.

Snapshot/extraction/registry/revision/evaluation counts взяты из API. У matching нет каталога: число rows явно неизвестно, вместо него проверяются точный saved match ID и immutable response. Integration tests считают domain records напрямую. Unsent cancellation и validation rejection не запускают handler. Восстановление display/status не добавляет POST/run.

| Viewport | Mutation | Граница потери | Исход | Browser POST | Conflicting probes | Завершённые handlers | Записей до → после | Точный saved ID |
| --- | --- | --- | --- | ---: | ---: | ---: | --- | --- |
| desktop-chromium | registry | before_delivery | not_received → committed | 2 | 1 | 1 | 1 → 2 | Новый результат не сохранён |
| desktop-chromium | snapshot | before_delivery | not_received → committed | 2 | 1 | 1 | 1 → 2 | aec7b1081d784ef6bf23fb9553b6a971 |
| desktop-chromium | candidate | before_delivery | not_received → committed | 2 | 1 | 1 | 0 → 1 | 737363cfd73e41d8bed4b91634c202e3 |
| desktop-chromium | extract | before_delivery | not_received → committed | 2 | 1 | 1 | 1 → 2 | 1f2672302ec544889d707db86999e674 |
| desktop-chromium | match | before_delivery | not_received → committed | 2 | 1 | 1 | Не перечислено → Не перечислено | d1170c86483f4150bae3e6a64642c9d8 |
| desktop-chromium | evaluate | before_delivery | not_received → committed | 2 | 1 | 1 | 1 → 2 | 806920a52a3a40b9864b2231d0a90561 |
| desktop-chromium | fetch | before_delivery | not_received → committed | 2 | 1 | 1 | 2 → 3 | 07b246190d34478fa01aa1b17a84f905 |
| desktop-chromium | registry | after_commit | committed → committed | 1 | 1 | 1 | 2 → 3 | Новый результат не сохранён |
| desktop-chromium | snapshot | after_commit | committed → committed | 1 | 1 | 1 | 3 → 4 | 30c82639138b45d2b820c706b8b25f16 |
| desktop-chromium | candidate | after_commit | committed → committed | 1 | 1 | 1 | 0 → 1 | 7cde561cf90340b0b2b0db05f5fdd00e |
| desktop-chromium | extract | after_commit | committed → committed | 1 | 1 | 1 | 2 → 3 | b7ef6f6c9e6549f8a5d2ce5f7fcd5cb6 |
| desktop-chromium | match | after_commit | committed → committed | 1 | 1 | 1 | Не перечислено → Не перечислено | 908364bc134a472f8257b9714b04a276 |
| desktop-chromium | evaluate | after_commit | committed → committed | 1 | 1 | 1 | 2 → 3 | 4efe563c73d04d29850c215e24b08318 |
| desktop-chromium | fetch | after_commit | committed → committed | 1 | 1 | 1 | 4 → 5 | 6ee7c1b914874d818b4705cd9d563082 |
| desktop-chromium | extract | display_read_lost | committed/display_pending → committed | 1 | 0 | 1 | Не перечислено → Не перечислено | 647126d7cedf42d58bf0e72abb501d0f |
| desktop-chromium | snapshot | unsent_reload_cancel | not_received → rejected | 1 | 1 | 0 | 5 → 5 | Новый результат не сохранён |
| desktop-chromium | extract | provider_in_flight | uncertain → committed | 1 | 0 | 1 | Не перечислено → Не перечислено | 492deb62cd0c43888f47416b133a2d88 |
| desktop-chromium | extract | lookup_lost_reload | uncertain → committed | 1 | 0 | 1 | 6 → 6 | 4b36401b870749ecbd815eede3d76d37 |
| desktop-chromium | candidate | validation_rejected | rejected → rejected | 1 | 0 | 0 | 0 → 0 | Новый результат не сохранён |
| mobile-chromium | registry | before_delivery | not_received → committed | 2 | 1 | 1 | 1 → 2 | Новый результат не сохранён |
| mobile-chromium | snapshot | before_delivery | not_received → committed | 2 | 1 | 1 | 1 → 2 | 618a65ba97a94275bcf7fda97d543814 |
| mobile-chromium | candidate | before_delivery | not_received → committed | 2 | 1 | 1 | 0 → 1 | 025ff8226b7b46b39f74653c8147fe77 |
| mobile-chromium | extract | before_delivery | not_received → committed | 2 | 1 | 1 | 1 → 2 | b2932b7562884a51b2c79dd752c9b7f0 |
| mobile-chromium | match | before_delivery | not_received → committed | 2 | 1 | 1 | Не перечислено → Не перечислено | fb158ce8e59045b58a218ea1cdafbff9 |
| mobile-chromium | evaluate | before_delivery | not_received → committed | 2 | 1 | 1 | 1 → 2 | ef1fbce83035440a8795cb1790ef794c |
| mobile-chromium | fetch | before_delivery | not_received → committed | 2 | 1 | 1 | 2 → 3 | bb8880778d6844a0ac7c2ce9412a6492 |
| mobile-chromium | registry | after_commit | committed → committed | 1 | 1 | 1 | 2 → 3 | Новый результат не сохранён |
| mobile-chromium | snapshot | after_commit | committed → committed | 1 | 1 | 1 | 3 → 4 | 1b807eee49004d4581754f50c9e9f221 |
| mobile-chromium | candidate | after_commit | committed → committed | 1 | 1 | 1 | 0 → 1 | d02659c55c124c24beca21bbee5ed126 |
| mobile-chromium | extract | after_commit | committed → committed | 1 | 1 | 1 | 2 → 3 | f43a3f098ad440e4a1799b7aa00aa66d |
| mobile-chromium | match | after_commit | committed → committed | 1 | 1 | 1 | Не перечислено → Не перечислено | 074a9e58deb1434a85a088d848df0e41 |
| mobile-chromium | evaluate | after_commit | committed → committed | 1 | 1 | 1 | 2 → 3 | 6f2c04ad06ec438ea33a970b699d0761 |
| mobile-chromium | fetch | after_commit | committed → committed | 1 | 1 | 1 | 4 → 5 | 835664ff3e8340ee886f389d15219595 |
| mobile-chromium | extract | display_read_lost | committed/display_pending → committed | 1 | 0 | 1 | Не перечислено → Не перечислено | e398a57c2dd443a1a3c1fce954ee3d5e |
| mobile-chromium | snapshot | unsent_reload_cancel | not_received → rejected | 1 | 1 | 0 | 5 → 5 | Новый результат не сохранён |
| mobile-chromium | extract | provider_in_flight | uncertain → committed | 1 | 0 | 1 | Не перечислено → Не перечислено | dfacafcfb1d649fea08fe0789610320d |
| mobile-chromium | extract | lookup_lost_reload | uncertain → committed | 1 | 0 | 1 | 6 → 6 | 4304f3a3f7e24af4be39dd259c7ea647 |
| mobile-chromium | candidate | validation_rejected | rejected → rejected | 1 | 0 | 0 | 0 → 0 | Новый результат не сохранён |

[Desktop UI13](../../ui-recordings/UI13-desktop-chromium.webm) · [Mobile UI13](../../ui-recordings/UI13-mobile-chromium.webm)

Прежние snapshots/extractions/revisions/matches/evaluations прочитаны без изменений. In-flight case использует отдельный Responses emulator и bounded delay. Unknown outcome остаётся uncertain до подтверждения lookup, без повторного execution. Browser storage хранит только opaque operation ID.
