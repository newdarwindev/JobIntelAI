# Batches: измеренные исходы до, после ошибки и продолжения

Источник: [Запуск GitHub Actions](https://github.com/newdarwindev/JobIntelAI/actions/runs/39441877552) · проверенный коммит `5384741088d5201efcd9fe63b3dcc75e2e4f6f43`.
SHA-256 исходного содержимого: `90ea58bd7c7d24a69f78da5537a307ae6140226d281f610d6e7e11a62b0d591c`. [Машинные наблюдения](batch-comparison.json).

Авторский synthetic ввод, реальные API/БД; платные hosted запросы не выполнялись. Эти проверки не измеряют качество модели.

UI14 выбирает три authored jobs через обозначенный fixture-metadata read; snapshots/extraction/matching используют настоящие API. Unsupported fixture source и реальный stale extraction вызывают ошибки, успешные domain responses не подменяются. UI03/UI05 также проходят все 20 jobs, unit gate проверяет continuation bound на 45 items.

Completed items сохраняют точные result/attempt IDs при continuation: нет повторного POST или повторной успешной extraction/match. Before-delivery retry сохраняет key, post-commit lookup/reload не добавляет mutation. Явный replan меняет только unfinished items; другая candidate revision блокирует matching до восстановления captured selection. Empty batch ничего не отправляет.

Это counts captured batch и сервера, не качество модели. In-flight journal остаётся uncertain до доставки даже при server commit. Browser POST counts учитывают keyed snapshot/extract/match, исключая registry preparation, reads, profiles и независимую fault injection. У matching нет каталога: проверяются saved responses и operation IDs. Исходная extraction history сохранена.

| Viewport | Batch | Граница | До: зарегистрировано/извлечено | Частичные исходы | Частичный сервер | После continuation | Итоговый сервер | Browser POST | Сохранённые completed IDs |
| --- | --- | --- | --- | --- | --- | --- | --- | ---: | --- |
| desktop-chromium | extraction | failure_first | 0/0 | 0 завершено / 1 ошибок / 2 не начато / 0 неизвестно | 3/0 | 3 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 3/3 | 7 | До прерывания завершённых items нет |
| desktop-chromium | extraction | failure_middle | 0/0 | 1 завершено / 1 ошибок / 1 не начато / 0 неизвестно | 3/1 | 3 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 3/3 | 7 | SYN-01: 38a77190955e41eb911837db2610cff6 |
| desktop-chromium | extraction | failure_last | 0/0 | 2 завершено / 1 ошибок / 0 не начато / 0 неизвестно | 3/2 | 3 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 3/3 | 7 | SYN-01: 8603dd858c374d40a2346502cf53e261<br>SYN-02: 8d99d799ab5d4f20b8816dc4544bd1cb |
| desktop-chromium | matching | failure_first | 3/3 | 0 завершено / 1 ошибок / 2 не начато / 0 неизвестно | 3/3 | 3 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 3/3 | 4 | До прерывания завершённых items нет |
| desktop-chromium | matching | failure_middle | 3/3 | 1 завершено / 1 ошибок / 1 не начато / 0 неизвестно | 3/3 | 3 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 3/3 | 4 | SYN-01: 2c1f91c2dd584d909b50b552b725f2e4 |
| desktop-chromium | matching | failure_last | 3/3 | 2 завершено / 1 ошибок / 0 не начато / 0 неизвестно | 3/3 | 3 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 3/3 | 4 | SYN-01: 5d53e2001b0842dbb78619b54010afd5<br>SYN-02: 8f848d6952e74096b686c0791dccb7b0 |
| desktop-chromium | extraction | before_delivery | 0/0 | 1 завершено / 0 ошибок / 1 не начато / 1 неизвестно | 3/1 | 3 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 3/3 | 7 | SYN-01: fe47da1925c545a7bea4ea47a03b2060 |
| desktop-chromium | extraction | after_commit_lookup_lost_reload | 0/0 | 1 завершено / 0 ошибок / 1 не начато / 1 неизвестно | 3/2 | 3 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 3/3 | 6 | SYN-01: 4629c5e55b08427ab2f9451a66fb0c76 |
| desktop-chromium | matching | before_delivery | 3/3 | 1 завершено / 0 ошибок / 1 не начато / 1 неизвестно | 3/3 | 3 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 3/3 | 4 | SYN-01: c8eb5441d44c49908a40def9ef478d33 |
| desktop-chromium | matching | after_commit_lookup_lost_reload | 3/3 | 1 завершено / 0 ошибок / 1 не начато / 1 неизвестно | 3/3 | 3 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 3/3 | 3 | SYN-01: 7b5abe3c700d46c0a2de8d2a1f5fa508 |
| desktop-chromium | extraction | navigation_in_flight | 0/0 | 1 завершено / 0 ошибок / 1 не начато / 1 неизвестно | 3/2 | 3 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 3/3 | 6 | SYN-01: 40e8dd9ec9c14c4e9a1815e7fe48ad84 |
| desktop-chromium | matching | navigation_in_flight | 3/3 | 1 завершено / 0 ошибок / 1 не начато / 1 неизвестно | 3/3 | 3 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 3/3 | 3 | SYN-01: f0515dc74e004660b6193068091c9b0d |
| desktop-chromium | extraction | stale_source | 0/0 | 1 завершено / 1 ошибок / 1 не начато / 0 неизвестно | 3/1 | 3 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 3/3 | 7 | SYN-01: 937171f8bfbd49318a7b643d98467e05 |
| desktop-chromium | matching | stale_revision | 3/3 | 1 завершено / 1 ошибок / 1 не начато / 0 неизвестно | 3/3 | 3 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 3/3 | 4 | SYN-01: 294cd4bbccbe4489b3e7055b89e2cc59 |
| desktop-chromium | extraction | empty | 0/0 | 0 завершено / 0 ошибок / 0 не начато / 0 неизвестно | Нет данных | 0 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 0/0 | 0 | До прерывания завершённых items нет |
| desktop-chromium | matching | empty | 0/0 | 0 завершено / 0 ошибок / 0 не начато / 0 неизвестно | Нет данных | 0 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 0/0 | 0 | До прерывания завершённых items нет |
| mobile-chromium | extraction | failure_first | 0/0 | 0 завершено / 1 ошибок / 2 не начато / 0 неизвестно | 3/0 | 3 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 3/3 | 7 | До прерывания завершённых items нет |
| mobile-chromium | extraction | failure_middle | 0/0 | 1 завершено / 1 ошибок / 1 не начато / 0 неизвестно | 3/1 | 3 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 3/3 | 7 | SYN-01: 649bfce169e94f958f9f4632ecc51779 |
| mobile-chromium | extraction | failure_last | 0/0 | 2 завершено / 1 ошибок / 0 не начато / 0 неизвестно | 3/2 | 3 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 3/3 | 7 | SYN-01: da003e7a1dcb48ef84914d8e76626efc<br>SYN-02: 19ea8f58c3704aa29bdc706af70e6f57 |
| mobile-chromium | matching | failure_first | 3/3 | 0 завершено / 1 ошибок / 2 не начато / 0 неизвестно | 3/3 | 3 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 3/3 | 4 | До прерывания завершённых items нет |
| mobile-chromium | matching | failure_middle | 3/3 | 1 завершено / 1 ошибок / 1 не начато / 0 неизвестно | 3/3 | 3 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 3/3 | 4 | SYN-01: aa4288ce75aa4fb68b02e24564fed7a7 |
| mobile-chromium | matching | failure_last | 3/3 | 2 завершено / 1 ошибок / 0 не начато / 0 неизвестно | 3/3 | 3 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 3/3 | 4 | SYN-01: ccd12ec9f8cf44f7acedd4917b0f8773<br>SYN-02: 27914d4c3a684c6282342702e97f2c6b |
| mobile-chromium | extraction | before_delivery | 0/0 | 1 завершено / 0 ошибок / 1 не начато / 1 неизвестно | 3/1 | 3 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 3/3 | 7 | SYN-01: 0516c45860a74f97ad1379d00b35964a |
| mobile-chromium | extraction | after_commit_lookup_lost_reload | 0/0 | 1 завершено / 0 ошибок / 1 не начато / 1 неизвестно | 3/2 | 3 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 3/3 | 6 | SYN-01: da3da49a28a04dc1ac2c109faa6d5053 |
| mobile-chromium | matching | before_delivery | 3/3 | 1 завершено / 0 ошибок / 1 не начато / 1 неизвестно | 3/3 | 3 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 3/3 | 4 | SYN-01: 1f512989b57c42d8a5b0876c16e11fbe |
| mobile-chromium | matching | after_commit_lookup_lost_reload | 3/3 | 1 завершено / 0 ошибок / 1 не начато / 1 неизвестно | 3/3 | 3 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 3/3 | 3 | SYN-01: 001d509931424c288d44c43e6c1e935b |
| mobile-chromium | extraction | navigation_in_flight | 0/0 | 1 завершено / 0 ошибок / 1 не начато / 1 неизвестно | 3/2 | 3 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 3/3 | 6 | SYN-01: 278f52e6829f4f05ad994f5186f92be5 |
| mobile-chromium | matching | navigation_in_flight | 3/3 | 1 завершено / 0 ошибок / 1 не начато / 1 неизвестно | 3/3 | 3 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 3/3 | 3 | SYN-01: 0525802aba8c473b815d7849efacad18 |
| mobile-chromium | extraction | stale_source | 0/0 | 1 завершено / 1 ошибок / 1 не начато / 0 неизвестно | 3/1 | 3 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 3/3 | 7 | SYN-01: 8642d7ae073d44e69cd518e16959205a |
| mobile-chromium | matching | stale_revision | 3/3 | 1 завершено / 1 ошибок / 1 не начато / 0 неизвестно | 3/3 | 3 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 3/3 | 4 | SYN-01: 576c9ebbce80441cae69868da497b11e |
| mobile-chromium | extraction | empty | 0/0 | 0 завершено / 0 ошибок / 0 не начато / 0 неизвестно | Нет данных | 0 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 0/0 | 0 | До прерывания завершённых items нет |
| mobile-chromium | matching | empty | 0/0 | 0 завершено / 0 ошибок / 0 не начато / 0 неизвестно | Нет данных | 0 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 0/0 | 0 | До прерывания завершённых items нет |

[Desktop UI14](../../ui-recordings/UI14-desktop-chromium.webm) · [Mobile UI14](../../ui-recordings/UI14-mobile-chromium.webm)

Панель сохраняет identities/states и prior rejected operation IDs при navigation/reload. Session storage содержит только IDs/config/selection/states, bodies и error messages читаются в память. Unknown operation блокирует continuation. Каждый exit пытается обновить authoritative state; failure обозначен как отсутствие данных.
