# Batches: измеренные исходы до, после ошибки и продолжения

Источник: [Запуск GitHub Actions](https://github.com/newdarwindev/JobIntelAI/actions/runs/38727794951) · проверенный коммит `aefc151fc1acbe15e7a09ee8b9db4f865f406271`.
SHA-256 исходного содержимого: `08428f1651ed32c95b511669e49458604c9197c7db3b43b6f9666d82e2e6c18c`. [Машинные наблюдения](batch-comparison.json).

Авторский synthetic ввод, реальные API/БД; платные hosted запросы не выполнялись. Эти проверки не измеряют качество модели.

UI14 выбирает три authored jobs через обозначенный fixture-metadata read; snapshots/extraction/matching используют настоящие API. Unsupported fixture source и реальный stale extraction вызывают ошибки, успешные domain responses не подменяются. UI03/UI05 также проходят все 20 jobs, unit gate проверяет continuation bound на 45 items.

Completed items сохраняют точные result/attempt IDs при continuation: нет повторного POST или повторной успешной extraction/match. Before-delivery retry сохраняет key, post-commit lookup/reload не добавляет mutation. Явный replan меняет только unfinished items; другая candidate revision блокирует matching до восстановления captured selection. Empty batch ничего не отправляет.

Это counts captured batch и сервера, не качество модели. In-flight journal остаётся uncertain до доставки даже при server commit. Browser POST counts учитывают keyed snapshot/extract/match, исключая registry preparation, reads, profiles и независимую fault injection. У matching нет каталога: проверяются saved responses и operation IDs. Исходная extraction history сохранена.

| Viewport | Batch | Граница | До: зарегистрировано/извлечено | Частичные исходы | Частичный сервер | После continuation | Итоговый сервер | Browser POST | Сохранённые completed IDs |
| --- | --- | --- | --- | --- | --- | --- | --- | ---: | --- |
| desktop-chromium | extraction | failure_first | 0/0 | 0 завершено / 1 ошибок / 2 не начато / 0 неизвестно | 3/0 | 3 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 3/3 | 7 | До прерывания завершённых items нет |
| desktop-chromium | extraction | failure_middle | 0/0 | 1 завершено / 1 ошибок / 1 не начато / 0 неизвестно | 3/1 | 3 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 3/3 | 7 | SYN-01: ff0551165ad84dcf999e3324f642219f |
| desktop-chromium | extraction | failure_last | 0/0 | 2 завершено / 1 ошибок / 0 не начато / 0 неизвестно | 3/2 | 3 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 3/3 | 7 | SYN-01: a67873e36072470a876a7d020b0f4672<br>SYN-02: f38f1af01a2c4e568131b0d629506cda |
| desktop-chromium | matching | failure_first | 3/3 | 0 завершено / 1 ошибок / 2 не начато / 0 неизвестно | 3/3 | 3 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 3/3 | 4 | До прерывания завершённых items нет |
| desktop-chromium | matching | failure_middle | 3/3 | 1 завершено / 1 ошибок / 1 не начато / 0 неизвестно | 3/3 | 3 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 3/3 | 4 | SYN-01: 1de7626fb51045a699ddb235a841db5e |
| desktop-chromium | matching | failure_last | 3/3 | 2 завершено / 1 ошибок / 0 не начато / 0 неизвестно | 3/3 | 3 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 3/3 | 4 | SYN-01: 23bfe8064ef84497a25c29badbaed72f<br>SYN-02: 2df1cc4b07df41ffb78776fdea271a9c |
| desktop-chromium | extraction | before_delivery | 0/0 | 1 завершено / 0 ошибок / 1 не начато / 1 неизвестно | 3/1 | 3 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 3/3 | 7 | SYN-01: 7db401254ba74c868910ce9c35bfb149 |
| desktop-chromium | extraction | after_commit_lookup_lost_reload | 0/0 | 1 завершено / 0 ошибок / 1 не начато / 1 неизвестно | 3/2 | 3 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 3/3 | 6 | SYN-01: 07536ad2215f415a94e55ae50692d758 |
| desktop-chromium | matching | before_delivery | 3/3 | 1 завершено / 0 ошибок / 1 не начато / 1 неизвестно | 3/3 | 3 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 3/3 | 4 | SYN-01: 96c626eb72844477a33fe42aaa8e85a3 |
| desktop-chromium | matching | after_commit_lookup_lost_reload | 3/3 | 1 завершено / 0 ошибок / 1 не начато / 1 неизвестно | 3/3 | 3 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 3/3 | 3 | SYN-01: d64b720819d34e18b3b68d3dddc25b68 |
| desktop-chromium | extraction | navigation_in_flight | 0/0 | 1 завершено / 0 ошибок / 1 не начато / 1 неизвестно | 3/2 | 3 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 3/3 | 6 | SYN-01: 84fb411d78464f9b97d4c9783a97a272 |
| desktop-chromium | matching | navigation_in_flight | 3/3 | 1 завершено / 0 ошибок / 1 не начато / 1 неизвестно | 3/3 | 3 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 3/3 | 3 | SYN-01: 34b7ef432865414d8c0b04d9c4f31e53 |
| desktop-chromium | extraction | stale_source | 0/0 | 1 завершено / 1 ошибок / 1 не начато / 0 неизвестно | 3/1 | 3 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 3/3 | 7 | SYN-01: f87311f8423143789f706dd5f64fcc4c |
| desktop-chromium | matching | stale_revision | 3/3 | 1 завершено / 1 ошибок / 1 не начато / 0 неизвестно | 3/3 | 3 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 3/3 | 4 | SYN-01: 0a4a860ad74e4428a8e10c84d0779e22 |
| desktop-chromium | extraction | empty | 0/0 | 0 завершено / 0 ошибок / 0 не начато / 0 неизвестно | Нет данных | 0 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 0/0 | 0 | До прерывания завершённых items нет |
| desktop-chromium | matching | empty | 0/0 | 0 завершено / 0 ошибок / 0 не начато / 0 неизвестно | Нет данных | 0 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 0/0 | 0 | До прерывания завершённых items нет |
| mobile-chromium | extraction | failure_first | 0/0 | 0 завершено / 1 ошибок / 2 не начато / 0 неизвестно | 3/0 | 3 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 3/3 | 7 | До прерывания завершённых items нет |
| mobile-chromium | extraction | failure_middle | 0/0 | 1 завершено / 1 ошибок / 1 не начато / 0 неизвестно | 3/1 | 3 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 3/3 | 7 | SYN-01: 60eeceb59d664ee38bd17445fe28aeab |
| mobile-chromium | extraction | failure_last | 0/0 | 2 завершено / 1 ошибок / 0 не начато / 0 неизвестно | 3/2 | 3 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 3/3 | 7 | SYN-01: a552807cb14b4f098190f9d009c4197e<br>SYN-02: 98c1639378c74d7282489942c3535ed1 |
| mobile-chromium | matching | failure_first | 3/3 | 0 завершено / 1 ошибок / 2 не начато / 0 неизвестно | 3/3 | 3 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 3/3 | 4 | До прерывания завершённых items нет |
| mobile-chromium | matching | failure_middle | 3/3 | 1 завершено / 1 ошибок / 1 не начато / 0 неизвестно | 3/3 | 3 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 3/3 | 4 | SYN-01: 62f5b78fb9c04ecd9f2105369aacc541 |
| mobile-chromium | matching | failure_last | 3/3 | 2 завершено / 1 ошибок / 0 не начато / 0 неизвестно | 3/3 | 3 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 3/3 | 4 | SYN-01: 70fce9f901934b17b54a2d4d718b532c<br>SYN-02: 95644a7020a94c84a3fd21ff912b09d7 |
| mobile-chromium | extraction | before_delivery | 0/0 | 1 завершено / 0 ошибок / 1 не начато / 1 неизвестно | 3/1 | 3 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 3/3 | 7 | SYN-01: 37359cab1bd247e480299b35bbd2c817 |
| mobile-chromium | extraction | after_commit_lookup_lost_reload | 0/0 | 1 завершено / 0 ошибок / 1 не начато / 1 неизвестно | 3/2 | 3 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 3/3 | 6 | SYN-01: b0ae3b19f7b748638f931fa372918509 |
| mobile-chromium | matching | before_delivery | 3/3 | 1 завершено / 0 ошибок / 1 не начато / 1 неизвестно | 3/3 | 3 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 3/3 | 4 | SYN-01: a6d38f76fc81409d9e9f166aa56a6666 |
| mobile-chromium | matching | after_commit_lookup_lost_reload | 3/3 | 1 завершено / 0 ошибок / 1 не начато / 1 неизвестно | 3/3 | 3 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 3/3 | 3 | SYN-01: 16ada5ca28df44b6a770194d649964eb |
| mobile-chromium | extraction | navigation_in_flight | 0/0 | 1 завершено / 0 ошибок / 1 не начато / 1 неизвестно | 3/2 | 3 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 3/3 | 6 | SYN-01: 003c7c482a994b63a3a08d83f7d71fc7 |
| mobile-chromium | matching | navigation_in_flight | 3/3 | 1 завершено / 0 ошибок / 1 не начато / 1 неизвестно | 3/3 | 3 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 3/3 | 3 | SYN-01: 74c19c0786df4a26b554b5d4f286ea36 |
| mobile-chromium | extraction | stale_source | 0/0 | 1 завершено / 1 ошибок / 1 не начато / 0 неизвестно | 3/1 | 3 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 3/3 | 7 | SYN-01: fcb4a6ef87da4d0b815d8dc7b3d4b417 |
| mobile-chromium | matching | stale_revision | 3/3 | 1 завершено / 1 ошибок / 1 не начато / 0 неизвестно | 3/3 | 3 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 3/3 | 4 | SYN-01: 194f4acecd5f4a509e4a57e3195b5e8f |
| mobile-chromium | extraction | empty | 0/0 | 0 завершено / 0 ошибок / 0 не начато / 0 неизвестно | Нет данных | 0 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 0/0 | 0 | До прерывания завершённых items нет |
| mobile-chromium | matching | empty | 0/0 | 0 завершено / 0 ошибок / 0 не начато / 0 неизвестно | Нет данных | 0 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 0/0 | 0 | До прерывания завершённых items нет |

[Desktop UI14](../../ui-recordings/UI14-desktop-chromium.webm) · [Mobile UI14](../../ui-recordings/UI14-mobile-chromium.webm)

Панель сохраняет identities/states и prior rejected operation IDs при navigation/reload. Session storage содержит только IDs/config/selection/states, bodies и error messages читаются в память. Unknown operation блокирует continuation. Каждый exit пытается обновить authoritative state; failure обозначен как отсутствие данных.
