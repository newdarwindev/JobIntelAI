# Batches: измеренные исходы до, после ошибки и продолжения

Источник: [Запуск GitHub Actions](https://github.com/newdarwindev/JobIntelAI/actions/runs/39440475953) · проверенный коммит `e30c2f4667edd14970f843fa15bd7a0811ff2945`.
SHA-256 исходного содержимого: `dc134a9714a84967c0e4ac05fe13dc7a32deda88049ea185f0b7599d84cbd5b5`. [Машинные наблюдения](batch-comparison.json).

Авторский synthetic ввод, реальные API/БД; платные hosted запросы не выполнялись. Эти проверки не измеряют качество модели.

UI14 выбирает три authored jobs через обозначенный fixture-metadata read; snapshots/extraction/matching используют настоящие API. Unsupported fixture source и реальный stale extraction вызывают ошибки, успешные domain responses не подменяются. UI03/UI05 также проходят все 20 jobs, unit gate проверяет continuation bound на 45 items.

Completed items сохраняют точные result/attempt IDs при continuation: нет повторного POST или повторной успешной extraction/match. Before-delivery retry сохраняет key, post-commit lookup/reload не добавляет mutation. Явный replan меняет только unfinished items; другая candidate revision блокирует matching до восстановления captured selection. Empty batch ничего не отправляет.

Это counts captured batch и сервера, не качество модели. In-flight journal остаётся uncertain до доставки даже при server commit. Browser POST counts учитывают keyed snapshot/extract/match, исключая registry preparation, reads, profiles и независимую fault injection. У matching нет каталога: проверяются saved responses и operation IDs. Исходная extraction history сохранена.

| Viewport | Batch | Граница | До: зарегистрировано/извлечено | Частичные исходы | Частичный сервер | После continuation | Итоговый сервер | Browser POST | Сохранённые completed IDs |
| --- | --- | --- | --- | --- | --- | --- | --- | ---: | --- |
| desktop-chromium | extraction | failure_first | 0/0 | 0 завершено / 1 ошибок / 2 не начато / 0 неизвестно | 3/0 | 3 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 3/3 | 7 | До прерывания завершённых items нет |
| desktop-chromium | extraction | failure_middle | 0/0 | 1 завершено / 1 ошибок / 1 не начато / 0 неизвестно | 3/1 | 3 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 3/3 | 7 | SYN-01: 07242f77b0b74448b33fba5579b0b2e7 |
| desktop-chromium | extraction | failure_last | 0/0 | 2 завершено / 1 ошибок / 0 не начато / 0 неизвестно | 3/2 | 3 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 3/3 | 7 | SYN-01: 28412fd8f02e4683b88d4c7aa9e6b2ef<br>SYN-02: c0594ceec8104ef8a1b3914f78571d4d |
| desktop-chromium | matching | failure_first | 3/3 | 0 завершено / 1 ошибок / 2 не начато / 0 неизвестно | 3/3 | 3 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 3/3 | 4 | До прерывания завершённых items нет |
| desktop-chromium | matching | failure_middle | 3/3 | 1 завершено / 1 ошибок / 1 не начато / 0 неизвестно | 3/3 | 3 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 3/3 | 4 | SYN-01: cd4ddb0eff964bb4b092f5fade98af90 |
| desktop-chromium | matching | failure_last | 3/3 | 2 завершено / 1 ошибок / 0 не начато / 0 неизвестно | 3/3 | 3 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 3/3 | 4 | SYN-01: 8b10a55a9e7f439eb335c6215bdcc78a<br>SYN-02: 9015ff51cfca46d4afca94bb5ea17319 |
| desktop-chromium | extraction | before_delivery | 0/0 | 1 завершено / 0 ошибок / 1 не начато / 1 неизвестно | 3/1 | 3 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 3/3 | 7 | SYN-01: 510ba8b66b0f4df4967d26db68a9a6a4 |
| desktop-chromium | extraction | after_commit_lookup_lost_reload | 0/0 | 1 завершено / 0 ошибок / 1 не начато / 1 неизвестно | 3/2 | 3 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 3/3 | 6 | SYN-01: 8f2d8370116e46e682289160eb10c776 |
| desktop-chromium | matching | before_delivery | 3/3 | 1 завершено / 0 ошибок / 1 не начато / 1 неизвестно | 3/3 | 3 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 3/3 | 4 | SYN-01: 76002208c3a74277b45ac1201904df73 |
| desktop-chromium | matching | after_commit_lookup_lost_reload | 3/3 | 1 завершено / 0 ошибок / 1 не начато / 1 неизвестно | 3/3 | 3 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 3/3 | 3 | SYN-01: 9a5dc2322567487499538fb65b6581ad |
| desktop-chromium | extraction | navigation_in_flight | 0/0 | 1 завершено / 0 ошибок / 1 не начато / 1 неизвестно | 3/2 | 3 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 3/3 | 6 | SYN-01: c9c59b0d2b674e40bde5c1542d15c832 |
| desktop-chromium | matching | navigation_in_flight | 3/3 | 1 завершено / 0 ошибок / 1 не начато / 1 неизвестно | 3/3 | 3 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 3/3 | 3 | SYN-01: 495cab82eef540039bd63465aebb5f53 |
| desktop-chromium | extraction | stale_source | 0/0 | 1 завершено / 1 ошибок / 1 не начато / 0 неизвестно | 3/1 | 3 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 3/3 | 7 | SYN-01: 6a6b01c6c84f4a88a1115494655820e8 |
| desktop-chromium | matching | stale_revision | 3/3 | 1 завершено / 1 ошибок / 1 не начато / 0 неизвестно | 3/3 | 3 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 3/3 | 4 | SYN-01: 3ed27d27e08945f58eb0a1e4675458d4 |
| desktop-chromium | extraction | empty | 0/0 | 0 завершено / 0 ошибок / 0 не начато / 0 неизвестно | Нет данных | 0 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 0/0 | 0 | До прерывания завершённых items нет |
| desktop-chromium | matching | empty | 0/0 | 0 завершено / 0 ошибок / 0 не начато / 0 неизвестно | Нет данных | 0 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 0/0 | 0 | До прерывания завершённых items нет |
| mobile-chromium | extraction | failure_first | 0/0 | 0 завершено / 1 ошибок / 2 не начато / 0 неизвестно | 3/0 | 3 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 3/3 | 7 | До прерывания завершённых items нет |
| mobile-chromium | extraction | failure_middle | 0/0 | 1 завершено / 1 ошибок / 1 не начато / 0 неизвестно | 3/1 | 3 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 3/3 | 7 | SYN-01: 0341bf236ba1424b83cb2bce0ab87dbf |
| mobile-chromium | extraction | failure_last | 0/0 | 2 завершено / 1 ошибок / 0 не начато / 0 неизвестно | 3/2 | 3 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 3/3 | 7 | SYN-01: be84dd2d77624814950db0eaf55c40de<br>SYN-02: 4f5b32bfdde74765a87da3538aa9b97d |
| mobile-chromium | matching | failure_first | 3/3 | 0 завершено / 1 ошибок / 2 не начато / 0 неизвестно | 3/3 | 3 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 3/3 | 4 | До прерывания завершённых items нет |
| mobile-chromium | matching | failure_middle | 3/3 | 1 завершено / 1 ошибок / 1 не начато / 0 неизвестно | 3/3 | 3 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 3/3 | 4 | SYN-01: 10d1d662da58466b9db7e1aa32cd2a33 |
| mobile-chromium | matching | failure_last | 3/3 | 2 завершено / 1 ошибок / 0 не начато / 0 неизвестно | 3/3 | 3 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 3/3 | 4 | SYN-01: aa6c3960f8df437e9974c8149331ccdb<br>SYN-02: bcdeeb8d75fe44a3996ca2fc0034f7ae |
| mobile-chromium | extraction | before_delivery | 0/0 | 1 завершено / 0 ошибок / 1 не начато / 1 неизвестно | 3/1 | 3 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 3/3 | 7 | SYN-01: ff24f991d4d64176ad8e042caaf77dc6 |
| mobile-chromium | extraction | after_commit_lookup_lost_reload | 0/0 | 1 завершено / 0 ошибок / 1 не начато / 1 неизвестно | 3/2 | 3 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 3/3 | 6 | SYN-01: f42414c4034b4ac0a377fe2bf118ca3c |
| mobile-chromium | matching | before_delivery | 3/3 | 1 завершено / 0 ошибок / 1 не начато / 1 неизвестно | 3/3 | 3 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 3/3 | 4 | SYN-01: cd17a0601f564df88fa66206059408ea |
| mobile-chromium | matching | after_commit_lookup_lost_reload | 3/3 | 1 завершено / 0 ошибок / 1 не начато / 1 неизвестно | 3/3 | 3 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 3/3 | 3 | SYN-01: 2145a2d22fa44ee2a97e5a5790596be2 |
| mobile-chromium | extraction | navigation_in_flight | 0/0 | 1 завершено / 0 ошибок / 1 не начато / 1 неизвестно | 3/2 | 3 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 3/3 | 6 | SYN-01: bfa06967a11b4019b63daf4ce9a16d3a |
| mobile-chromium | matching | navigation_in_flight | 3/3 | 1 завершено / 0 ошибок / 1 не начато / 1 неизвестно | 3/3 | 3 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 3/3 | 3 | SYN-01: 9fbcc4d171f94d428956d1aa053b9d70 |
| mobile-chromium | extraction | stale_source | 0/0 | 1 завершено / 1 ошибок / 1 не начато / 0 неизвестно | 3/1 | 3 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 3/3 | 7 | SYN-01: 11a2dc76774046faa7eded87e9b0e135 |
| mobile-chromium | matching | stale_revision | 3/3 | 1 завершено / 1 ошибок / 1 не начато / 0 неизвестно | 3/3 | 3 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 3/3 | 4 | SYN-01: 582caea0643f466eac6d81afb36c954f |
| mobile-chromium | extraction | empty | 0/0 | 0 завершено / 0 ошибок / 0 не начато / 0 неизвестно | Нет данных | 0 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 0/0 | 0 | До прерывания завершённых items нет |
| mobile-chromium | matching | empty | 0/0 | 0 завершено / 0 ошибок / 0 не начато / 0 неизвестно | Нет данных | 0 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 0/0 | 0 | До прерывания завершённых items нет |

[Desktop UI14](../../ui-recordings/UI14-desktop-chromium.webm) · [Mobile UI14](../../ui-recordings/UI14-mobile-chromium.webm)

Панель сохраняет identities/states и prior rejected operation IDs при navigation/reload. Session storage содержит только IDs/config/selection/states, bodies и error messages читаются в память. Unknown operation блокирует continuation. Каждый exit пытается обновить authoritative state; failure обозначен как отсутствие данных.
