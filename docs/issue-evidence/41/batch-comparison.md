# Batches: измеренные исходы до, после ошибки и продолжения

Источник: [Запуск GitHub Actions](https://github.com/newdarwindev/JobIntelAI/actions/runs/38312031669) · проверенный коммит `dfca80099bb64af736db436556546f9f08de1493`.
SHA-256 исходного содержимого: `2df4acda6f4e4b1fca56f2c5397f11f01efd23ac54976934c809bfbd7bc5c59d`. [Машинные наблюдения](batch-comparison.json).

Авторский synthetic ввод, реальные API/БД; платные hosted запросы не выполнялись. Эти проверки не измеряют качество модели.

UI14 выбирает три authored jobs через обозначенный fixture-metadata read; snapshots/extraction/matching используют настоящие API. Unsupported fixture source и реальный stale extraction вызывают ошибки, успешные domain responses не подменяются. UI03/UI05 также проходят все 20 jobs, unit gate проверяет continuation bound на 45 items.

Completed items сохраняют точные result/attempt IDs при continuation: нет повторного POST или повторной успешной extraction/match. Before-delivery retry сохраняет key, post-commit lookup/reload не добавляет mutation. Явный replan меняет только unfinished items; другая candidate revision блокирует matching до восстановления captured selection. Empty batch ничего не отправляет.

Это counts captured batch и сервера, не качество модели. In-flight journal остаётся uncertain до доставки даже при server commit. Browser POST counts учитывают keyed snapshot/extract/match, исключая registry preparation, reads, profiles и независимую fault injection. У matching нет каталога: проверяются saved responses и operation IDs. Исходная extraction history сохранена.

| Viewport | Batch | Граница | До: зарегистрировано/извлечено | Частичные исходы | Частичный сервер | После continuation | Итоговый сервер | Browser POST | Сохранённые completed IDs |
| --- | --- | --- | --- | --- | --- | --- | --- | ---: | --- |
| desktop-chromium | extraction | failure_first | 0/0 | 0 завершено / 1 ошибок / 2 не начато / 0 неизвестно | 3/0 | 3 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 3/3 | 7 | До прерывания завершённых items нет |
| desktop-chromium | extraction | failure_middle | 0/0 | 1 завершено / 1 ошибок / 1 не начато / 0 неизвестно | 3/1 | 3 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 3/3 | 7 | SYN-01: 1dc76c0081d34a2181095c6dd77e43e1 |
| desktop-chromium | extraction | failure_last | 0/0 | 2 завершено / 1 ошибок / 0 не начато / 0 неизвестно | 3/2 | 3 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 3/3 | 7 | SYN-01: 9a082ae99bad465aafa725325c69e7ad<br>SYN-02: ef4322a2fc0c46199b8d4004fe4775f5 |
| desktop-chromium | matching | failure_first | 3/3 | 0 завершено / 1 ошибок / 2 не начато / 0 неизвестно | 3/3 | 3 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 3/3 | 4 | До прерывания завершённых items нет |
| desktop-chromium | matching | failure_middle | 3/3 | 1 завершено / 1 ошибок / 1 не начато / 0 неизвестно | 3/3 | 3 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 3/3 | 4 | SYN-01: ad2bd566965446d0b0f20bcc30c7af0a |
| desktop-chromium | matching | failure_last | 3/3 | 2 завершено / 1 ошибок / 0 не начато / 0 неизвестно | 3/3 | 3 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 3/3 | 4 | SYN-01: 915480811dcc487a83c5e4d3a9cd54df<br>SYN-02: 72ede53dce904ab28f7bc7c6bd093de9 |
| desktop-chromium | extraction | before_delivery | 0/0 | 1 завершено / 0 ошибок / 1 не начато / 1 неизвестно | 3/1 | 3 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 3/3 | 7 | SYN-01: 50ebbd40b30e4f67a94b89c9d7ad3c18 |
| desktop-chromium | extraction | after_commit_lookup_lost_reload | 0/0 | 1 завершено / 0 ошибок / 1 не начато / 1 неизвестно | 3/2 | 3 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 3/3 | 6 | SYN-01: d5ebcfcc5bee4ff19c25677dfec5f81a |
| desktop-chromium | matching | before_delivery | 3/3 | 1 завершено / 0 ошибок / 1 не начато / 1 неизвестно | 3/3 | 3 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 3/3 | 4 | SYN-01: 1fd00c2c24374f10ba9cce49846b5882 |
| desktop-chromium | matching | after_commit_lookup_lost_reload | 3/3 | 1 завершено / 0 ошибок / 1 не начато / 1 неизвестно | 3/3 | 3 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 3/3 | 3 | SYN-01: 9df0bd8413ea4b41b1e38b7b80fe1adb |
| desktop-chromium | extraction | navigation_in_flight | 0/0 | 1 завершено / 0 ошибок / 1 не начато / 1 неизвестно | 3/2 | 3 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 3/3 | 6 | SYN-01: ad09b6c2a6fd4f75821129e388b31535 |
| desktop-chromium | matching | navigation_in_flight | 3/3 | 1 завершено / 0 ошибок / 1 не начато / 1 неизвестно | 3/3 | 3 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 3/3 | 3 | SYN-01: 503731e71a6546bba5ff302641f22c51 |
| desktop-chromium | extraction | stale_source | 0/0 | 1 завершено / 1 ошибок / 1 не начато / 0 неизвестно | 3/1 | 3 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 3/3 | 7 | SYN-01: af8c78e941994fa4afeb908d1f5bb43c |
| desktop-chromium | matching | stale_revision | 3/3 | 1 завершено / 1 ошибок / 1 не начато / 0 неизвестно | 3/3 | 3 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 3/3 | 4 | SYN-01: 9af74363c08844d6b672dd74878a679b |
| desktop-chromium | extraction | empty | 0/0 | 0 завершено / 0 ошибок / 0 не начато / 0 неизвестно | Нет данных | 0 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 0/0 | 0 | До прерывания завершённых items нет |
| desktop-chromium | matching | empty | 0/0 | 0 завершено / 0 ошибок / 0 не начато / 0 неизвестно | Нет данных | 0 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 0/0 | 0 | До прерывания завершённых items нет |
| mobile-chromium | extraction | failure_first | 0/0 | 0 завершено / 1 ошибок / 2 не начато / 0 неизвестно | 3/0 | 3 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 3/3 | 7 | До прерывания завершённых items нет |
| mobile-chromium | extraction | failure_middle | 0/0 | 1 завершено / 1 ошибок / 1 не начато / 0 неизвестно | 3/1 | 3 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 3/3 | 7 | SYN-01: b2b9792952c24fcc9363615a953e5c4d |
| mobile-chromium | extraction | failure_last | 0/0 | 2 завершено / 1 ошибок / 0 не начато / 0 неизвестно | 3/2 | 3 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 3/3 | 7 | SYN-01: 3ecc3358e2d140279b917eecf269d3eb<br>SYN-02: cef59be98fe64a629f44570bd8266980 |
| mobile-chromium | matching | failure_first | 3/3 | 0 завершено / 1 ошибок / 2 не начато / 0 неизвестно | 3/3 | 3 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 3/3 | 4 | До прерывания завершённых items нет |
| mobile-chromium | matching | failure_middle | 3/3 | 1 завершено / 1 ошибок / 1 не начато / 0 неизвестно | 3/3 | 3 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 3/3 | 4 | SYN-01: e3bac732acc443fea9f08134007e42c2 |
| mobile-chromium | matching | failure_last | 3/3 | 2 завершено / 1 ошибок / 0 не начато / 0 неизвестно | 3/3 | 3 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 3/3 | 4 | SYN-01: 0a4ba290482b4fbc902720fa4ea7728d<br>SYN-02: 4405d142362844d7ac51ee033e89cf4f |
| mobile-chromium | extraction | before_delivery | 0/0 | 1 завершено / 0 ошибок / 1 не начато / 1 неизвестно | 3/1 | 3 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 3/3 | 7 | SYN-01: 218e52044ce24f7cb0f25c8974780015 |
| mobile-chromium | extraction | after_commit_lookup_lost_reload | 0/0 | 1 завершено / 0 ошибок / 1 не начато / 1 неизвестно | 3/2 | 3 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 3/3 | 6 | SYN-01: 51cc3be605c047a984d3af9ae1ecd62c |
| mobile-chromium | matching | before_delivery | 3/3 | 1 завершено / 0 ошибок / 1 не начато / 1 неизвестно | 3/3 | 3 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 3/3 | 4 | SYN-01: 93a2a71632e04519982a18f510a6d276 |
| mobile-chromium | matching | after_commit_lookup_lost_reload | 3/3 | 1 завершено / 0 ошибок / 1 не начато / 1 неизвестно | 3/3 | 3 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 3/3 | 3 | SYN-01: 4363e849e08d4ac7ba2134d52e3bb287 |
| mobile-chromium | extraction | navigation_in_flight | 0/0 | 1 завершено / 0 ошибок / 1 не начато / 1 неизвестно | 3/2 | 3 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 3/3 | 6 | SYN-01: c14a70b26f5942a7980d089e35e55c50 |
| mobile-chromium | matching | navigation_in_flight | 3/3 | 1 завершено / 0 ошибок / 1 не начато / 1 неизвестно | 3/3 | 3 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 3/3 | 3 | SYN-01: 8e883a8d062048cb8b5260878572c731 |
| mobile-chromium | extraction | stale_source | 0/0 | 1 завершено / 1 ошибок / 1 не начато / 0 неизвестно | 3/1 | 3 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 3/3 | 7 | SYN-01: 8a45c9eb4f664051b56e09cbe6f7b5cf |
| mobile-chromium | matching | stale_revision | 3/3 | 1 завершено / 1 ошибок / 1 не начато / 0 неизвестно | 3/3 | 3 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 3/3 | 4 | SYN-01: 375453c4340541fcb6f1a16355022f51 |
| mobile-chromium | extraction | empty | 0/0 | 0 завершено / 0 ошибок / 0 не начато / 0 неизвестно | Нет данных | 0 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 0/0 | 0 | До прерывания завершённых items нет |
| mobile-chromium | matching | empty | 0/0 | 0 завершено / 0 ошибок / 0 не начато / 0 неизвестно | Нет данных | 0 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 0/0 | 0 | До прерывания завершённых items нет |

[Desktop UI14](../../ui-recordings/UI14-desktop-chromium.webm) · [Mobile UI14](../../ui-recordings/UI14-mobile-chromium.webm)

Панель сохраняет identities/states и prior rejected operation IDs при navigation/reload. Session storage содержит только IDs/config/selection/states, bodies и error messages читаются в память. Unknown operation блокирует continuation. Каждый exit пытается обновить authoritative state; failure обозначен как отсутствие данных.
