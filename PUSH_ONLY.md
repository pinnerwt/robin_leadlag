# Push-only capture and state-replay acceptance

The active capture is `captures/all-push-20261115-midnight-utc/`, ending at
**2026-11-15 00:00 UTC** (08:00 Taiwan). It uses `config/push.json` and
`examples/push_capture.rs`, not the legacy `ohio` recorder or SPCX-only probe.

## What is implemented

- All raw Nitro messages, including messages/transaction destinations that the
  old SPCX probe discarded. Sequence numbers, signatures, block hashes and
  calldata remain in the binary tape.
- Unfiltered chain logs plus headers: pool changes, oracle/provider events,
  extensions and newly referenced contract addresses are retained, including
  unknown events. Two `eth_subscribe` requests establish this stream. There
  are no `eth_call`, transaction, receipt, log-range or chain-ID queries.
- Eleven Binance Spot bookTicker symbols, three simultaneous connections,
  per-symbol update-ID high-water dedup. Out-of-order late copies cannot
  roll back the book. Original price/quantity decimal strings are retained.
- Monotonic and wall-clock receipt times, connection epochs, reconnect gaps,
  coverage reports, and graceful end markers. Nitro relay additionally retains
  upstream receipt timestamps. Its decompression/forwarding cost remains part
  of the implementation; this is not a measured production latency guarantee.
- Bounded reader/writer queues and a separate blocking writer. Capture queue
  failures produce a gap or terminate capture rather than silently dropping
  observations. Compression runs in another process, continuously.
- Backwards-compatible binary reader (`scripts/tape.py` or the Rust `replay`
  command), with strict truncation checks. Old positional SPCX records remain
  readable; new BBO records include symbol/sequence/timestamps/quantities.
- `scripts/state_leadlag.py`: HY at 50 ms resolution, positive = Binance leads,
  chronological walk-forward splits for K=3/5/10, and explicit hypothetical
  route adjustments. It accepts only complete/executable `state_quote` rows;
  it never promotes a swap price or oracle midpoint into a pool quote.

The universe is the **2026-11-14 12:29:16 UTC frozen Metric catalog** of 39
Robinhood pools over $10k volume. It is not dynamically refreshed over HTTP.
INDEX/USDG, NET/USDG, ORBIO/USDG and PONS/USDG have no Binance mapping in the
local exchange catalog; these pools are still captured. An inactive pool can
have zero events during a short window; that does not imply no subscription.

## One-time initialization and offline state replay

The user authorized initialization queries. `scripts/bootstrap_batch.py` pins
all calls and traces to one block and collects pool immutables, all configured
bins/shares, provider and extension dependencies. `scripts/hydrate_checkpoint.py`
closes missing dependencies using pre-anchor transaction samples, also at that
same block. These are setup-only tools, never invoked by the capture/replayer.
Current checkpoint: `captures/checkpoint.json`, block **114417008**. Its hash
must appear in the tape before replay starts. There is no full-history sync.

`src/local_evm.rs` runs contract bytecode locally. Unknown accounts/storage
fail closed; they never trigger an RPC and never silently become zero.
Nitro calldata supplies signed oracle transactions and L1 block context.
The latter matters: the guards use L1 `block.number`, not the L2 head number.
Provider calldata execution is checked against emitted FeedUpdated logs.
Pool swap simulation is checked against real deltas, BinSwapped events and
final bin/position; the explicit successful simulation-revert sentinel alone
can commit pool/extension effects. LP add/remove updates bins, total balances,
shares and empty-bin position; unsupported LP hooks invalidate the pool.
Supported pool fee/pause/provider settings are also reduced from events.

Arbitrary positive token0 sizes are accepted, e.g. `0.02,0.1`; sell uses exact
input and buy exact output. Fees, depth, provider and guard execution are used,
and partial fills are rejected. Only Carcosa pools are currently admitted as
research quotes. `state_complete` means supported observed inputs were replayed,
with `validation=observed_inputs_only`, not proof of public-stream completeness.
A failed transition permanently invalidates the affected interval.

## Remaining limitations

- This is an OFFLINE log-validated replay, not yet a live feed-only decision
  engine. It joins executed logs and headers; quote availability uses the
  latest required input arrival, not the earlier oracle/feed timestamp.
  Offline compute time is reported separately, not a measured online SLA.
- The EVM adapter is not a full Nitro node. It supports the observed contract
  execution subset, not arbitrary ArbOS, transaction gas/account effects or
  every router/extension. Observed swap amounts reconstruct simulation inputs;
  original router limits/extensionData and multi-swap transactions are not
  generally reproduced. Unsupported paths fail parity/are excluded.
- Unclassified pools have unresolved parity/provider coverage. Capturing all
  pools does not mean all have trustworthy quotes. External dependency/admin
  updates still require broader transition coverage before production use.
- Public log subscriptions cannot prove that every log arrived. Gaps/reorgs,
  removed logs and conflicting duplicates reject replay. A configurable 2 s
  trailing margin excludes unfinished live-prefix tails; it is not a proof
  that earlier blocks are complete. Reconnection does not restore authority.
- No periodic or reconnect RPC is enabled. A new checkpoint is needed after
  unrecoverable input loss. Recorded inputs remain binary+zstd; JSONL outputs
  are temporary analysis intermediates.

The old `carcosa-swap-check.json` uses previously downloaded trace state and
provider outputs. It is not evidence for this new continuous replay; consult
`reports/state-replay-summary.json` for the new checkpoint-plus-push test.

## Verified experiment

`reports/push-all-smoke-audit.json`: 119.976 seconds, 13,145 unique BBO,
1,096 Nitro push messages, 15,400 chain logs, 1,085 headers, all 11 Binance
symbols observed, 12 target pools with events, two liquidity-add events.
No observed sequence/header discontinuity or transport gap in this window.
No liquidity removal occurred in this short sample; the existing fixture test
covers add/remove decoding. Absence of an observed gap is not completeness.

Raw binary: 28,915,066 bytes; zstd: 3,056,532 bytes. At this short sample's
rate, approximately 2.05 GiB/day compressed for the full input stream;
future volume can differ. The long run streams zstd and avoids raw duplicates.

`tests/push_network_smoke.py` uses a local mock and asserts actual outbound
messages are exactly two subscriptions. Three Binance connections with
repeated/late IDs produce exactly two updates per symbol. No HTTP/JSON-RPC
read is permitted in that test.

## Replay

```sh
python3 scripts/audit_push.py captures/push-all-smoke.bin.zst
python3 scripts/tape.py captures/push-all-smoke.bin.zst
# Freeze a live tape first; raw input capture continues uninterrupted.
python3 scripts/cut_open_tape.py captures/all-push-20261115-midnight-utc/20261114T194009.317416Z.bin.zst /tmp/prefix.bin
cargo build --release --locked --example replay_state
python3 scripts/tape.py /tmp/prefix.bin | target/release/examples/replay_state captures/checkpoint.json 0.02,0.1 2000 > /tmp/state.jsonl
python3 scripts/state_leadlag.py --step-ms 50 < /tmp/state.jsonl > reports/state-hy.json
```

A validated quote row supplies `symbol`, `pool`, `size_tokens`,
`bid`, `ask`, `available_mono_ns`, `state_complete=true`, `executable=true`.
Invalid/unavailable quote rows break return intervals. Do not use triggering
feed time if the quote only became usable after execution or a log join.

For a hypothetical route where Binance arrives via Tokyo and Robinhood via
Ohio, use `--tokyo-ohio-ms X --ohio-taiwan-ms Y --tokyo-taiwan-ms 25`.
Binance is shifted by X−25 ms, Robinhood by −Y ms. Each series is re-sorted;
these are assumed one-way delays, not measured RTTs. The current analyzer
supports constant-delay scenarios, not measured jitter or order-fill PnL.
Do not apply this route model as fact to Taiwan direct subscriptions without
measuring their actual paths. Analyze sessions separately: monotonic origins
reset and gaps must not be crossed. HY contrast is not bounded Pearson
correlation, and a peak is not evidence of executable profit.
