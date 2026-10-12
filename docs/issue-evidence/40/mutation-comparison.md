# Mutation recovery — measured browser verification

Source: [GitHub Actions run](https://github.com/newdarwindev/JobIntelAI/actions/runs/38312031669) · tested commit `dfca80099bb64af736db436556546f9f08de1493`.
Source content SHA-256: `2df4acda6f4e4b1fca56f2c5397f11f01efd23ac54976934c809bfbd7bc5c59d`. [Machine-readable observations](mutation-comparison.json).

authored fixture replay and Responses emulator; actual API/DB operations; no paid calls.

Each row comes from the passing UI13 attempt, observed browser requests, saved operation lookup and readable API history/catalogues. Before-delivery loss sends two browser POSTs with one identity; after-commit loss recovers with a read. The conflicting-body probe is a separate test API POST and returns 409. Completed keyed handler executions are recorded by the server; they do not measure model quality or internal provider retries.

Snapshot/extraction/registry/revision/evaluation counts come from their actual API catalogues. Matching has no catalogue, so its row count is explicitly not enumerated; its exact saved match ID and immutable response are verified instead. PostgreSQL/SQLite integration tests additionally count all mutation records directly. Unsent cancellation and validation rejection start zero handlers. Display/status-read recovery adds no POST or saved run.

| Viewport | Mutation | Interrupted boundary | Observed outcome | Browser POSTs | Conflicting test POSTs | Completed handler executions | Saved records before → after | Exact saved identity |
| --- | --- | --- | --- | ---: | ---: | ---: | --- | --- |
| desktop-chromium | registry | before_delivery | not_received → committed | 2 | 1 | 1 | 1 → 2 | No new saved result |
| desktop-chromium | snapshot | before_delivery | not_received → committed | 2 | 1 | 1 | 1 → 2 | d452cc75bbac4a6cadc041912b44826f |
| desktop-chromium | candidate | before_delivery | not_received → committed | 2 | 1 | 1 | 0 → 1 | 527ba5aaff574942beac317cb0c302c6 |
| desktop-chromium | extract | before_delivery | not_received → committed | 2 | 1 | 1 | 1 → 2 | 792486fcad9a4e9fa1158fb675ce753b |
| desktop-chromium | match | before_delivery | not_received → committed | 2 | 1 | 1 | Not enumerated → Not enumerated | d813d4e89ae0444bb7c4860ffe96f75d |
| desktop-chromium | evaluate | before_delivery | not_received → committed | 2 | 1 | 1 | 1 → 2 | 3d1f7361744b418685740a4943e0aa85 |
| desktop-chromium | fetch | before_delivery | not_received → committed | 2 | 1 | 1 | 2 → 3 | 4aed4be204c44f0e8e953ac3578568c8 |
| desktop-chromium | registry | after_commit | committed → committed | 1 | 1 | 1 | 2 → 3 | No new saved result |
| desktop-chromium | snapshot | after_commit | committed → committed | 1 | 1 | 1 | 3 → 4 | e6d701b82b3346d9b3094252c3c7752a |
| desktop-chromium | candidate | after_commit | committed → committed | 1 | 1 | 1 | 0 → 1 | dd6495ebd4b94ed5b3ea9739b0dbf5b9 |
| desktop-chromium | extract | after_commit | committed → committed | 1 | 1 | 1 | 2 → 3 | abda179136ac4c00acb0831b0f8a7a45 |
| desktop-chromium | match | after_commit | committed → committed | 1 | 1 | 1 | Not enumerated → Not enumerated | f81c76d6bd5049e19f1163308d588c87 |
| desktop-chromium | evaluate | after_commit | committed → committed | 1 | 1 | 1 | 2 → 3 | b828df322dbf4c5e8c0974aa0ce766ce |
| desktop-chromium | fetch | after_commit | committed → committed | 1 | 1 | 1 | 4 → 5 | c8f73b61362a45ca907ef539dab89a63 |
| desktop-chromium | extract | display_read_lost | committed/display_pending → committed | 1 | 0 | 1 | Not enumerated → Not enumerated | deeb5db5e99749f3b028b53f011020cd |
| desktop-chromium | snapshot | unsent_reload_cancel | not_received → rejected | 1 | 1 | 0 | 5 → 5 | No new saved result |
| desktop-chromium | extract | provider_in_flight | uncertain → committed | 1 | 0 | 1 | Not enumerated → Not enumerated | 1186cfbb5cde4c3fa1412345b95363c6 |
| desktop-chromium | extract | lookup_lost_reload | uncertain → committed | 1 | 0 | 1 | 6 → 6 | 8a98a15da8a540498160807698ef3d03 |
| desktop-chromium | candidate | validation_rejected | rejected → rejected | 1 | 0 | 0 | 0 → 0 | No new saved result |
| mobile-chromium | registry | before_delivery | not_received → committed | 2 | 1 | 1 | 1 → 2 | No new saved result |
| mobile-chromium | snapshot | before_delivery | not_received → committed | 2 | 1 | 1 | 1 → 2 | ac695b7827bd48438373533204766c8f |
| mobile-chromium | candidate | before_delivery | not_received → committed | 2 | 1 | 1 | 0 → 1 | c7084b1a67304ca0a15e84af251410a4 |
| mobile-chromium | extract | before_delivery | not_received → committed | 2 | 1 | 1 | 1 → 2 | 3d90a5dc57014229981779641c24937c |
| mobile-chromium | match | before_delivery | not_received → committed | 2 | 1 | 1 | Not enumerated → Not enumerated | a528879e1f494f13a17edfd4977cf152 |
| mobile-chromium | evaluate | before_delivery | not_received → committed | 2 | 1 | 1 | 1 → 2 | 46f3b7a3f894481db4f6b21e2f81132f |
| mobile-chromium | fetch | before_delivery | not_received → committed | 2 | 1 | 1 | 2 → 3 | 26c96100968f463f8e1967830c3adb52 |
| mobile-chromium | registry | after_commit | committed → committed | 1 | 1 | 1 | 2 → 3 | No new saved result |
| mobile-chromium | snapshot | after_commit | committed → committed | 1 | 1 | 1 | 3 → 4 | 17bba7a1e30e4910a56081fcf3916661 |
| mobile-chromium | candidate | after_commit | committed → committed | 1 | 1 | 1 | 0 → 1 | 865fd2987d2e41c48d7a4709c87ae0b5 |
| mobile-chromium | extract | after_commit | committed → committed | 1 | 1 | 1 | 2 → 3 | 35f33e29d407459ca222cba3b03220f5 |
| mobile-chromium | match | after_commit | committed → committed | 1 | 1 | 1 | Not enumerated → Not enumerated | 304d54a883af40338fdcd72d7af59ddb |
| mobile-chromium | evaluate | after_commit | committed → committed | 1 | 1 | 1 | 2 → 3 | 000b7581e06e404987f81c53a3ca4718 |
| mobile-chromium | fetch | after_commit | committed → committed | 1 | 1 | 1 | 4 → 5 | d64fce55c0e74ab196bd131381c8981a |
| mobile-chromium | extract | display_read_lost | committed/display_pending → committed | 1 | 0 | 1 | Not enumerated → Not enumerated | fdb238edafdc42f48cef5483037d1e00 |
| mobile-chromium | snapshot | unsent_reload_cancel | not_received → rejected | 1 | 1 | 0 | 5 → 5 | No new saved result |
| mobile-chromium | extract | provider_in_flight | uncertain → committed | 1 | 0 | 1 | Not enumerated → Not enumerated | 7d1d4a5683cd401cbc22ff1c677dfd81 |
| mobile-chromium | extract | lookup_lost_reload | uncertain → committed | 1 | 0 | 1 | 6 → 6 | e255b10eb98e4c10b81e9772de81a9ff |
| mobile-chromium | candidate | validation_rejected | rejected → rejected | 1 | 0 | 0 | 0 → 0 | No new saved result |

[Desktop UI13 recording](../../ui-recordings/UI13-desktop-chromium.webm) · [Mobile UI13 recording](../../ui-recordings/UI13-mobile-chromium.webm)

Prior snapshot/extraction, candidate revision, match and evaluation records were read back unchanged. The in-flight case uses the separate authored Responses service with a bounded delayed response. Missing outcomes remain uncertain until lookup confirms them; no duplicate execution is scheduled. Only opaque operation identity is persisted in browser storage.
