# B89 pilot runtime

Remote root: `/home/ubuntu/robin_leadlag` on SSH host `robin`.

- `metric-trader.service`: independent Rust signer, durable wallet/nonce owner, three independent deduplicated Binance ETHUSDT streams, canonical heads, binary Unix input socket.
- `metric-observer.service`: separate pushed Nitro and all-logs subscriptions, initial sparse checkpoint, persistent local Rust EVM worker, binary quote/account/receipt IPC.
- Existing metric/equity/IEX recorder services are independent and have not been restarted for this integration.

## Inventory and permissions

Wallet `0xf145f6f5ac4fbfa726be34425ebdceb61c0607e5`.
Fixed baseline and user-declared exchange hedge: **0.058 ETH**.
Additional long cap **100 USDG**, buy-first, open **10 bps**, close **-10 bps**, slippage **1 bp**.
Execution budget is **20 ms**, with no artificial sleep before sending.

Executor: `0x3c2b334a9f9970b27d1f32deb477df59a03a8a78`.
Runtime hash: `0xfb4be43ef59ba52d16e8d7bdec21409a3345fa4cb8f194e41c7738dbc43e1efb`.
Finite setup approvals: **0.116 WETH**, **1,000 USDG**. These are turnover allowances, not position caps. New buys are blocked if remaining base allowance cannot cover closing the proposed long. Approval replenishment is cold maintenance with the trader in standby, not automatic.
Credentials remain in `/home/ubuntu/.config/robin-leadlag/trading.env`, mode 0600. Never print or copy it.

## State and latency

The confirmed state advances in pushed log order. Pool BinSwap events are grouped through the terminal Swap. V3 price/observation updates and accepted oracle calldata are applied in transaction order. A later transaction on the all-logs subscription provides the preceding transaction's completeness barrier; headers alone do not.

The decision quote overlays unconfirmed Pyth calldata onto a copy of the confirmed state, assuming successful calldata as requested. Once the accepted-log frontier passes an unaccepted update, that overlay expires. This avoids applying a delayed pool swap against a future oracle price. Unknown required state or stream discontinuities block trading and recover from a fresh checkpoint.

The quote/decision path performs no remote read RPC. Startup checkpoint/bootstrap and independent background account/receipt checks do use RPC. HTTP account checks are separate from the pushed chain endpoint and do not block quote processing. They use the primary mainnet RPC because the third-party push endpoint's 60 CU/minute limit was insufficient. Background account failure invalidates admission while preserving the reconstructed pool state.

This is a scoped projection, not a full Nitro EVM follower. B89's inspected V3 adapter uses the maintained price/tick-observation projection. Swap reconciliation aborts if observed price error exceeds 2 bps. Source/adapter upgrades or unsupported state changes require recovery/review.

## Operation

Nonsecret settings: `config/metric-trader-b89.json` and `config/metric-live-observer.json`.
The trader checks its config once per second. **Only `mode` may change without restarting**. Set `standby` to block new reservations; pending orders still require receipt reconciliation. Other config changes require a restart and may require an explicit durable-state migration.

`reports/metric-trader-status.json` reports blockers, received quotes, account syncs, submissions, ACKs, fills/reverts and pending hash. `reports/metric-observer-status.json` reports state progress, quote output and projection error. Service-active alone is not evidence of readiness.

Binary order audit: `state/metric-trader-b89/trading.bin`; decode with `scripts/tape.py`.
Durable wallet state must never be deleted to bypass pending/nonces or mismatched balances.
Cold setup journal: `state/metric-trader-b89/setup.json` (signed public transactions and canonical receipts; no private key).
Startup full executor buy/sell dry run: `reports/metric-trade-preflight.json`.

## Validation evidence

`reports/metric-live-projection-validation.json`: 150,000 historical pushed events, 22 B89 swaps, maximum error about 0.10 bps, 1,331 sampled quotes without quote errors. Local quote computation p50 about 0.93 ms, p90 about 1.13 ms; these are local replay computation measurements, not end-to-end Ohio execution latency.

Both deployed executor directions were simulated at one pinned block with 0.001 WETH, including actual owner, callback and token allowances. Those eth_call simulations did not execute trades or change balances.

## First live pilot — 2026-11-20 UTC

Completed one round trip, then explicitly returned to standby:

- Buy: 0.057826913271218652 WETH for 99.701986 USDG.
- Sell: the same quantity for 100.209143 USDG.
- Gross cash change: +0.507157 USDG; includes holding-period market movement and is not isolated lead-lag alpha.
- Six submissions, six sequencer acknowledgements, two fills, four reverts.
- Trading gas including reverts: 0.00003194343867 ETH; executor setup gas is separate.
- Observed sequencer ACK times: 34.936–132.634 ms. ACK latency is not inclusion latency; 20 ms execution has not been demonstrated.
- Historical block-end eth_call diagnostics for the first three reverts passed when only their price limit was relaxed. The implied adverse moves were about 1.22–2.27 bps, exceeding the unchanged 1 bp live limit. This is block-end diagnostic evidence, not an exact intra-block execution trace; debug_traceTransaction was unavailable.
- Final WETH: 0.058; USDG: 5188.263289; pending transaction: none.
- Trader and observer remain running in standby/connected state. Recorder PIDs remained unchanged.

Full evidence: `reports/metric-pilot-result.json` and `reports/metric-revert-limit-diagnostic.json`.

## Pilot ordering and hardening — 2026-11-20 UTC

`reports/pilot-crowding.json` contains the exact historical block/transaction ordering around the six pilot orders. No other successful B89 swap occurred within ±10 blocks of any of them. The extended roughly three-minute window contained two other successful B89 swaps and 67 ETH provider updates. This only bounds successful same-pool competition: the execution race also includes provider updates and underlying V3 price changes. Two reverted orders followed an ETH provider update in the same block (provider/order indices 1/18 and 3/10). Neither lack of same-pool swaps nor the subsequent provider-update distance proves an exploitable opportunity.

The 30 surrounding blocks averaged 13 transactions including one system transaction each, or 12 ordinary transactions. Our six blocks contained 25, 5, 35, 50, 16 and 15 total transactions. The separate 30-second header probe observed 279 height increments, approximately 107.5 ms per block; arrival p50 was 107.8 ms and p90 131.1 ms. This is an observed cadence, not a guaranteed block schedule or measured submit-to-inclusion latency.

Robinhood's official documentation currently describes first-come, first-served sequencing and explicitly excludes fee-based overtaking: https://docs.robinhood.com/chain/ . Keep priority fee zero unless a verified ordering-policy change warrants revisiting it. Arbitrum One's PGA configuration must not be assumed to apply to Robinhood.

Hardening deployed in standby:

- Durable `circuit.json` latches at three reverts in 60 seconds or before a thirteenth order attempt in 60 seconds. Restart/mode toggles do not clear the latch. Keep wallet/nonce state intact when investigating.
- Binary Unix IPC is duplex. Account/pending/inventory state is pushed from the trader; successful own swap log groups can provide canonical settlement evidence, with background receipt RPC as fallback. Cached permissions retain their original age after settlement.
- Independent submission tasks report per-endpoint ACK timing, HTTP status and RPC errors immediately. Background connection prewarming does not run on the decision path.
- Own transactions appearing in the Nitro feed produce `own_nitro_seen` audit records, enabling future submit-to-feed versus ACK/log comparisons. Historical pilot orders lack this new instrumentation.
- Stream inactivity and missing log progress trigger bounded-backoff checkpoint recovery. An independent pinned-block quote audit checks provider output and both directions at 0.001, 0.058 and 0.1 WETH every 60 seconds with 2 bps tolerance. No successful audit for 180 seconds invalidates the observer. Public RPC can lag push feeds; block availability is retried only in the background audit task.

The audit is scoped quote parity, not proof of every contract storage slot. New receipt fast-path, real-order ACK improvements and future inclusion latency still require a subsequent authorized live pilot. No new swaps were submitted during this hardening turn.

Post-deployment validation: two consecutive background audits at blocks 118844049 (`0x7156a91`) and 118844629 (`0x7156cd5`) passed all six quotes with zero difference. `reports/metric-hardening-verification.json` captures fresh quotes/account IPC, standby-only admission, no pending transaction, unchanged .058 WETH inventory and original recorder PIDs 16150/16161/16155. Rust tests: 22 library, 25 local-state and 8 trader passed; Python observer tests: 6 passed. Deliberate live socket fault injection and new live swap timing are not included in this validation.

## Calldata-first V3 price — 2026-11-20 UTC (not deployed)

`scripts/v3_feed_overlay.py` predicts each V3 price pool's spot price from Nitro feed calldata instead of waiting for pushed logs. The base is the newest Swap log; decoded feed swaps the log stream has not passed yet are folded over it in sequencer order (move to min(full move, sqrtPriceLimit); a price already past the limit is a revert). The observer passes the result to the state worker as a `v3_price` overlay on the quote copy only; confirmed storage still advances from logs. Enabled by `v3_overlay` in `config/metric-live-observer.json`; removing it restores logs-only behaviour. Taking effect requires an observer restart.

Each prediction is scored when the log stream passes its transaction (`v3_overlay` in the observer status). A mismatch, or a swap by a transaction that was not decoded, schedules one background pinned `slot0` read at the next complete block (`v3_rpc_checks`); a difference from the log-derived price turns the overlay off until a later check agrees. The public RPC trails the feed by roughly 0.5–0.9 s and rate-limits near 33 requests/s, so it is a check, never a price source on the quote path.

Replay of 15 minutes of robin tape (8,839 blocks, 1,288 with a V3a swap; `python3 scripts/v3_feed_overlay.py replay`): price error at feed arrival in swap blocks fell from mean 0.53 bps / 27% within 0.1 bps (newest log) to mean 0.085 bps / 83% within 0.1 bps. Of 2,496 transactions that swapped V3a, 1,678 were predicted (34 off by more than 0.05 bps); 818 were not decoded (mainly `0x29d8…` vault-balance amounts and later-hop aggregator routes) and are corrected by their logs as before. Liquidity is the last logged value, so moves across an initialized tick are approximate. This is a replay measurement, not a live result.
