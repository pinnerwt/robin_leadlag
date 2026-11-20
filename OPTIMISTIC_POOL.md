# Optimistic pool follower

The current experiment assumes decoded transactions succeed. Sender accounts,
nonces, allowances, and the full-chain EVM are not prerequisites. This does not
make unknown calldata decodable or prove a quote executable.

`scripts/optimistic_pool.py` consumes `decode_feed --with-raw --optimistic` JSONL
and writes an append-only RLLBIN journal. It uses the existing integer V3 engine
for swaps, direct mint/burn, and arbitrary-size bids/asks. Router slippage guards
are skipped under the explicit success assumption; impossible local arithmetic,
missing tick state, and partial exact-output transitions still invalidate only
the pools touched by that proposal. Unrelated unknown transactions produce
coverage records, without globally stopping supported updates.

A background subprocess runs the fixed-block V3 bootstrap. No network requests
occur in the reducer. On completion the owner thread locates that exact block
hash in its bounded contiguous feed buffer, checks the anchor block is complete,
replays transactions after it, then atomically replaces the book. A gap clears
the buffer and requests a new snapshot. Old or unobserved anchors cannot install.
Every installed checkpoint and correction quote is appended; earlier quotes
are never changed. Initial capture must start before the background snapshot.
The sample config deliberately starts a fresh sync immediately, since its seed
is historical.

The sample config uses `registry_template` only as a list of known router
indexes; its old mapping values are never installed. The worker refreshes it at
the new pool snapshot block. Optionally set `registry` to an already-pinned
initial registry matching the initial seed. The background worker checks
router bytecode and reads its already-known indexes at the new snapshot block.
Unknown indexes remain unsupported. Do not reuse a registry at another anchor.

## Run

Start the existing timestamped Nitro relay on the port in `config/push.json`,
then run from the repository root (output must not already exist):

```sh
set -o pipefail
target/release/examples/push_capture config/push.json 300 |
  python3 -u scripts/tape.py - |
  target/release/examples/decode_feed --with-raw --optimistic |
  python3 scripts/optimistic_pool.py config/optimistic-v3.json
```

The new decoder option retains undecodable Nitro messages and emits a gap;
strict `--with-raw` without `--optimistic` still fails on them. Binance, chain
logs and other input rows are retained inside `optimistic_input`; logs do not
update the book. The original capture includes all configured Binance symbols.
Input queue backpressure and disk writes can add latency; this Python experiment
has not been certified as the final low-latency production implementation.

Read the binary journal or recompute other sizes without any RPC:

```sh
python3 scripts/tape.py captures/optimistic-v3.bin
python3 scripts/replay_optimistic.py captures/optimistic-v3.bin \
  --sizes 0.02,0.1,1 --output captures/recomputed-v3.bin
zstd captures/optimistic-v3.bin
```

Recomputed rows explicitly lack observed availability timestamps. Use original
recorded quotes for arrival-time studies. Quote `source_mono_ns` is feed receipt;
`available_mono_ns` is host-monotonic local quote completion. These clocks have
different origins: do not subtract them. Use `available_ns - recv_ns` for
wall-clock pipeline delay (subject to wall-clock adjustment). Sync correction quotes have their
own current arrival time, not the historical timestamp of the RPC block.

## Coverage and evidence

This implementation covers the 11 initialized canonical V3 pools, **not Metric
provider/pool state or all custom routers**. Full snapshot reads include tick
bitmaps and initialized ticks, so an LP change missed by calldata is corrected
at sync. In between, a missed transaction or revert can bias local state.
`state_complete=false`, `provisional=true`, `executable=false` remain explicit.
The presence of a bid is not proof of full transition coverage.

Tests cover replay-after-anchor, duplicate suppression, unrelated transactions,
gap recovery, incomplete anchors, and binary round trips. The archived mainnet
smoke report is `reports/amm/optimistic-v9-smoke.json`; it is an offline decoder
coverage test, not live latency or profitability evidence. Its initial run
used standard routers only and stopped at a kind-9 message in strict decoding.

## Live smoke results, 2026-11-15

Two finite read-only runs completed; no transactions were sent.

- Standard-router run (240 seconds): two post-startup checkpoint installs, all
  11 Binance tickers observed, 8 calldata-triggered quote rows. Target Swap-log
  audit found 3 decoded pool intents out of 1,232 post-sync target swaps.
- Packed-router run (300 seconds): two checkpoint installs with refreshed
  mappings. The target-log audit found 345 decoded intents out of 704 post-sync
  target swaps (273 via `520/b2460c48`, 72 via `c33/000000e7`). Remaining 359
  target swaps had no supported pool intent. These denominators exclude startup
  swaps without a post-sync feed transaction and are not full-chain coverage.
- Packed run produced 44 reconciliation quote rows: 16 priced, 28 unavailable
  due to `calldata simulation rejected: price limit`. It produced **zero live
  calldata-triggered quote rows**: buffered replay had already invalidated the
  affected pools. There is no live latency percentile to report from this run.

Thus removing sender execution prerequisites works, and asynchronous sync is
operational, but sparse router coverage still causes state drift. Success
assumption cannot reconstruct missing pool operations. This is not yet continuous
production bid/ask. `29/9c909e3f`, `9e9e/00000000`, and `278d/a00597a0` are leading
remaining routes in the packed-run target audit.

See `reports/amm/optimistic-live-smoke.json`,
`reports/amm/optimistic-packed-live-smoke.json`, and
`reports/amm/optimistic-packed-live-coverage.json`. Journals are retained as
`captures/optimistic-{live,packed-live}-smoke.bin.zst` and can be replayed offline.
The final reducer additionally emits unavailable quote rows immediately when a
pool first becomes invalid; the live runs preceded that small reporting fix.

### Decoder extension update

[Router extension evidence](reports/amm/router-extensions.md) documents newly
supported 9e, 278, and non-balance-capped single-record 29 calls. The default
config now refreshes `config/optimistic-router-template.json`. Known unrecorded
pool operations are ignored; mixed supported multicalls retain tracked swaps.
Same-window retrospective tracked-pool coverage improves from 345/704 to
501/704. This is decoder coverage, not proof that continuous state is repaired.

The next extension supports 29/164cb8f5 mixed multi-record transactions under an
explicit per-subcall success assumption. Tracked-pool intent coverage is now
514/704 (73.0%); 190 tracked swaps remain unresolved. See the continuation in
[router extension evidence](reports/amm/router-extensions.md).

769/b7bee4b6 first-swap decoding is now wired in with explicit unresolved-callback
coverage notes. Same-window intent coverage is 524/704, including 10 partial
callback cases. `calldata_partial_decode` and quote-level partial counters must
remain visible to analysis; this is not complete-transaction/state coverage.

426/32038e4b parallel V3 splits are supported with per-leg fixed amounts and
nested code/config checks during background sync. Current retrospective intent
coverage: 532/704 (75.6%), including 10 partial callback cases; 172 tracked swaps
remain unresolved. See `reports/amm/router426-validation.json` for exact input
matches and the successful fresh-anchor two-leg read-only trace.

7dec 89-byte memory-word commands 0x2f/0x31 are supported, with strict STOP
continuation and write-bound checks. 29 real argument/log-bound matches and 32
synthetic bytecode variants pass. Current retrospective intent coverage is
540/704 (76.7%); 164 tracked swaps remain unresolved, including cc1a research
paths. Ten covered intents still have unresolved callbacks. See the extension
report for cc1a sender-keyed flag branch evidence; no sender account bootstrap
or hot-path RPC was introduced. Continuous calldata-only state parity remains
incomplete.

c9/bad401db exact-output callbacks are now decoded with explicit upstream
settlement uncertainty. Five real callback/Swap quantity matches pass; four
fall in the post-sync audit window. Latest retrospective intent coverage is
544/704 (77.3%), including 14 unresolved settlement/callback intents; 160 are
still missing. These are argument counts, not complete-state or execution proof.

Added pinned `204f-permit-v3-v1` for the observed Permit2 + single V3 exact-output
sequence. The archived bytecode pool call and historical output amount match.
Other command sequences, dynamic balance amounts and nonempty callbacks remain
rejected. Same-window intent coverage is now 545/704 (77.4%), including 14 partial
callback/settlement intents; 159 remain missing. This is argument coverage, not
continuous-state parity. See `reports/amm/universal-permit-validation.json`.

The 204f profile also accepts verified fixed-input V3 -> unwrap -> native sweep,
with explicit partial native-settlement status. Current intent audit: 546/704,
158 missing and 15 unresolved callback/settlement intents. The remaining balance-
derived/V4 command sequences are still rejected.

Optional shared Aqua reducer: `optimistic_pool.Follower` now selects `AquaBook`
when the V3 checkpoint contains an `aqua` object (same `anchor_hash`, strategies
and C9 router inventory as the research bridge). It requires pinned C9 proxy,
router777, SwapVM and hub bytecode. C7/router777 share the follower's ordinary V3
state dictionary, so decoded third-party V3 changes remain visible. Unknown or
partial other transactions invalidate the Aqua side until a fresh checkpoint.
The default capture config has not been enabled for this path, and background
bootstrap does not yet generate Aqua snapshots. This is tested integration
plumbing, not a production/continuous-replay completion claim.

Background Aqua snapshot support is now implemented: set `aqua_template` to
`config/aqua-template.json` and use `config/aqua-router-template.json` for the
registry template to opt in. It reads both packed hub allocations and C9 token
balances at the V3 snapshot's fixed block, rechecks the block hash, and validates
book construction before install. These are background requests only. Default
configuration remains unchanged; live continuous-state coverage is unproven.
