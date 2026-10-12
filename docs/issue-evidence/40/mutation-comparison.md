# Mutation recovery — measured browser verification

Source: [GitHub Actions run](https://github.com/newdarwindev/JobIntelAI/actions/runs/38305588007) · tested commit `f7869937abcea70dfdd1b535289058cd0285b068`.
Source content SHA-256: `4d7089d5e733086940330612067b90f2cace45c042b45fffb933fedae041f0b1`. [Machine-readable observations](mutation-comparison.json).

authored fixture replay and Responses emulator; actual API/DB operations; no paid calls.

Each row comes from the passing UI13 attempt, observed browser requests, saved operation lookup and readable API history/catalogues. Before-delivery loss sends two browser POSTs with one identity; after-commit loss recovers with a read. The conflicting-body probe is a separate test API POST and returns 409. Completed keyed handler executions are recorded by the server; they do not measure model quality or internal provider retries.

Snapshot/extraction/registry/revision/evaluation counts come from their actual API catalogues. Matching has no catalogue, so its row count is explicitly not enumerated; its exact saved match ID and immutable response are verified instead. PostgreSQL/SQLite integration tests additionally count all mutation records directly. Unsent cancellation and validation rejection start zero handlers. Display/status-read recovery adds no POST or saved run.

| Viewport | Mutation | Interrupted boundary | Observed outcome | Browser POSTs | Conflicting test POSTs | Completed handler executions | Saved records before → after | Exact saved identity |
| --- | --- | --- | --- | ---: | ---: | ---: | --- | --- |
| desktop-chromium | registry | before_delivery | not_received → committed | 2 | 1 | 1 | 1 → 2 | No new saved result |
| desktop-chromium | snapshot | before_delivery | not_received → committed | 2 | 1 | 1 | 1 → 2 | e40a9c8cb822440b97e36550d554423d |
| desktop-chromium | candidate | before_delivery | not_received → committed | 2 | 1 | 1 | 0 → 1 | ae006d61e4784e518e33b6e6c85c5b34 |
| desktop-chromium | extract | before_delivery | not_received → committed | 2 | 1 | 1 | 1 → 2 | 176e347932cc48b98bbfbafa90c765af |
| desktop-chromium | match | before_delivery | not_received → committed | 2 | 1 | 1 | Not enumerated → Not enumerated | 907bdfac8384484e870fb01b62a66d84 |
| desktop-chromium | evaluate | before_delivery | not_received → committed | 2 | 1 | 1 | 1 → 2 | 65dab049f8c64e999047ef41077c2f97 |
| desktop-chromium | fetch | before_delivery | not_received → committed | 2 | 1 | 1 | 2 → 3 | e8cd3b602b6445b68a1c13250f042e28 |
| desktop-chromium | registry | after_commit | committed → committed | 1 | 1 | 1 | 2 → 3 | No new saved result |
| desktop-chromium | snapshot | after_commit | committed → committed | 1 | 1 | 1 | 3 → 4 | 8e835a04fa5e4fbc87cae49dc2544345 |
| desktop-chromium | candidate | after_commit | committed → committed | 1 | 1 | 1 | 0 → 1 | ec6fc3ade9e64942a13e5cdc1e4d4c7a |
| desktop-chromium | extract | after_commit | committed → committed | 1 | 1 | 1 | 2 → 3 | b31ce4e67e2544e5b92cb91aaa9850d2 |
| desktop-chromium | match | after_commit | committed → committed | 1 | 1 | 1 | Not enumerated → Not enumerated | 367d5ebaee01445ea8847bcc644bff5d |
| desktop-chromium | evaluate | after_commit | committed → committed | 1 | 1 | 1 | 2 → 3 | 7e96d37351b4456f9a1b971421cbb7b3 |
| desktop-chromium | fetch | after_commit | committed → committed | 1 | 1 | 1 | 4 → 5 | 58a62e2eebfd469396587c2e481cc126 |
| desktop-chromium | extract | display_read_lost | committed/display_pending → committed | 1 | 0 | 1 | Not enumerated → Not enumerated | 07e7f14b15b148cfa2111282c54acb0c |
| desktop-chromium | snapshot | unsent_reload_cancel | not_received → rejected | 1 | 1 | 0 | 5 → 5 | No new saved result |
| desktop-chromium | extract | provider_in_flight | uncertain → committed | 1 | 0 | 1 | Not enumerated → Not enumerated | a526faae1c724cbba1ac9619f12a7938 |
| desktop-chromium | extract | lookup_lost_reload | uncertain → committed | 1 | 0 | 1 | 6 → 6 | 45cb223be8a14d639926e7759e6e6545 |
| desktop-chromium | candidate | validation_rejected | rejected → rejected | 1 | 0 | 0 | 0 → 0 | No new saved result |
| mobile-chromium | registry | before_delivery | not_received → committed | 2 | 1 | 1 | 1 → 2 | No new saved result |
| mobile-chromium | snapshot | before_delivery | not_received → committed | 2 | 1 | 1 | 1 → 2 | d0aeb93f660342c79d9bce0d5713134f |
| mobile-chromium | candidate | before_delivery | not_received → committed | 2 | 1 | 1 | 0 → 1 | bc766d56b05f4b0ea18bc04b2a71b872 |
| mobile-chromium | extract | before_delivery | not_received → committed | 2 | 1 | 1 | 1 → 2 | cd60d27bfd5f4d8492670feb640214b2 |
| mobile-chromium | match | before_delivery | not_received → committed | 2 | 1 | 1 | Not enumerated → Not enumerated | 2bdcb7d7cca54efea2df1d0d790eb393 |
| mobile-chromium | evaluate | before_delivery | not_received → committed | 2 | 1 | 1 | 1 → 2 | 4f813bebc5a44efcb7bcb6b8f0aae69c |
| mobile-chromium | fetch | before_delivery | not_received → committed | 2 | 1 | 1 | 2 → 3 | 162b56a43fbd48ddb80d466865f382d9 |
| mobile-chromium | registry | after_commit | committed → committed | 1 | 1 | 1 | 2 → 3 | No new saved result |
| mobile-chromium | snapshot | after_commit | committed → committed | 1 | 1 | 1 | 3 → 4 | 6642c5f240744dfbb508736303d1a00f |
| mobile-chromium | candidate | after_commit | committed → committed | 1 | 1 | 1 | 0 → 1 | d2b9b667933f40fa812b6d38547f2428 |
| mobile-chromium | extract | after_commit | committed → committed | 1 | 1 | 1 | 2 → 3 | 2b5d698070d34d91b137bf7f4c1ec668 |
| mobile-chromium | match | after_commit | committed → committed | 1 | 1 | 1 | Not enumerated → Not enumerated | f0e15f3a6f3f499eb2a91ccf2e7fb626 |
| mobile-chromium | evaluate | after_commit | committed → committed | 1 | 1 | 1 | 2 → 3 | e9ed9040e04d4e1c903da7d3e8c047f3 |
| mobile-chromium | fetch | after_commit | committed → committed | 1 | 1 | 1 | 4 → 5 | f53da4ba245f4d25a6609fea95f8c776 |
| mobile-chromium | extract | display_read_lost | committed/display_pending → committed | 1 | 0 | 1 | Not enumerated → Not enumerated | 5787a767d5314d90bab0697aaaaf2e90 |
| mobile-chromium | snapshot | unsent_reload_cancel | not_received → rejected | 1 | 1 | 0 | 5 → 5 | No new saved result |
| mobile-chromium | extract | provider_in_flight | uncertain → committed | 1 | 0 | 1 | Not enumerated → Not enumerated | 2b203e1b536c4362bb557e30f1a7410a |
| mobile-chromium | extract | lookup_lost_reload | uncertain → committed | 1 | 0 | 1 | 6 → 6 | 632d39036be547b893feef704704b366 |
| mobile-chromium | candidate | validation_rejected | rejected → rejected | 1 | 0 | 0 | 0 → 0 | No new saved result |

[Desktop UI13 recording](../../ui-recordings/UI13-desktop-chromium.webm) · [Mobile UI13 recording](../../ui-recordings/UI13-mobile-chromium.webm)

Prior snapshot/extraction, candidate revision, match and evaluation records were read back unchanged. The in-flight case uses the separate authored Responses service with a bounded delayed response. Missing outcomes remain uncertain until lookup confirms them; no duplicate execution is scheduled. Only opaque operation identity is persisted in browser storage.
