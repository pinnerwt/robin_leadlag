# Robinhood / Binance lead–lag recorder

**Staged trading components:** [EXECUTION.md](EXECUTION.md) documents the Rust execution core, offline shadow command, validation and remaining Metric-specific integration. Signing is disabled in the example configuration.

**Additional AMM pools:** [AMM_CAPTURE.md](AMM_CAPTURE.md) records the new catalog,
verified V3 initialization/quotes, and the unresolved custom-router calldata coverage.

**Current experiment:** [OPTIMISTIC_POOL.md](OPTIMISTIC_POOL.md) implements
pool-scoped optimistic V3 calldata updates and background fixed-block RPC
reconciliation. The hot-path reducer makes no RPC requests. This replaces the
requirement to execute unrelated senders; Metric/provider and custom-router
coverage are still incomplete. Original quotes and corrections are separate
binary records. [PUSH_ONLY.md](PUSH_ONLY.md) documents the earlier strict-EVM
experiment and raw capture path.

The commands below document **legacy RPC-assisted modes**, not the current
push-only recorder. Do not use `ohio` or `block_quotes` for the zero-request path.


The Robinhood process subscribes to the 39 Robinhood pools in the checked-in
Metric volume snapshot. The Binance sender records 11 Binance Spot pairs by default. Both write
versioned, length-prefixed binary journals. Use a new file per run.

```sh
cargo build --release --locked
BINANCE_LISTEN=127.0.0.1:19481,127.0.0.1:19482 \
  target/release/robin-leadlag tokyo > binance.bin
```

In a second terminal:

```sh
ROBIN_WS_URLS=wss://rpc-robinhood.blockmachine.io \
ROBIN_RPC_URL=https://rpc.mainnet.chain.robinhood.com \
BINANCE_RELAY_ADDRS=127.0.0.1:19481,127.0.0.1:19482 \
  target/release/robin-leadlag ohio > combined.bin
```

Set `CAPTURE_SECS=7200` for a timed run. `BINANCE_WS_URLS` accepts a
comma-separated list of raw or combined bookTicker URLs. Set `BINANCE_SYMBOLS` to override the default symbols. The sender defaults to
three connections. Sender and receiver each deduplicate by symbol and Binance update ID
within a bounded recent-update window. Every relay gets the same binary frame.
Ohio retains the earliest received copy and records its relay link and arrival
time. Use trusted networks or separate authenticated tunnels for remote links.
Multiple sockets on the same route share the underlying network path.

```sh
target/release/robin-leadlag replay combined.bin
zstd -q combined.bin
zstd -dc combined.bin.zst | target/release/robin-leadlag replay -
```

Replay emits structured JSONL in recorded arrival order. Numerical timestamps
are UTC epoch nanoseconds. Large exact token deltas are decimal strings.
Liquidity updates contain signed bin balance changes and LP shares. Swap and
BinSwapped rows carry token deltas, final position or fees. Unknown contract
events retain topics and data. Headers retain height, hash, parent and time.

Robinhood reads fixed-height snapshots via `getImmutables()` and
`extsload(bytes32[])` after subscription establishment and every
`ROBIN_SYNC_SECS` seconds (default 300). Snapshots check the sum of bin
balances against the pool totals and verify the block hash before installation.
They reconcile previous observed bin deltas, emit comparison counts and
replace the balance baseline. Gap and removed-log records invalidate that
baseline. A successful reconnect requests a fresh snapshot. Gaps remain
visible in the journal. Checkpoints detect net balance differences, so matching
checkpoints alone do not prove every intervening event was received.

The local balance reducer follows add, remove and swap events. Replay exports
the checkpoints and changes needed to apply them in chain order. Oracle calldata
lookups run in the background for the SPCX Pyth feed when `ROBIN_RPC_URL` is
set. Binance Spot bookTicker has no exchange event time. Compare arrival times
on the recorder host and keep clock offset measurements for remote runs.

Fixed-size executable bid/ask still requires reconstructing the custom quote
source and guard state. The current journal supports oracle lead–lag and
historical pool activity analysis.

Leave `ROBIN_RPC_URL` unset for WebSocket-only capture. Set
`ROBIN_WS_URLS` to the executed-head/log endpoint and optionally
`ROBIN_QUOTE_WS_URL` to a separate WebSocket JSON-RPC endpoint, ideally on the
same local Nitro follower. The quote worker checks the header bloom before
requesting logs by exact block hash and joining accepted updates to calldata.
Each Carcosa SPCX `block_quote` carries its head arrival and quote availability
timestamps. Warm-up, staleness and failed lookups are explicit statuses.

The quoted edges are the compressed source's bid/ask. Full provider settings,
extensions and fixed-size bin execution still need to be applied. Public
WebSocket RPC requests add network round trips on update blocks. For a
low-latency deployment, measure against a local Nitro follower and validate
state recovery and quote parity before using the journal for execution.

The bounded push latency probe is `cargo run --example push_latency -- 42`.
Set `ROBIN_FEED_URL` to a local Nitro relay when the upstream requires
permessage-deflate. `examples/push_ws_relay.py` is the temporary relay used
for the measurement (requires Python websockets). The probe subscribes once
to executed oracle logs, matches pushed calldata by transaction and block
hash, and never requests historical data. It decodes Pyth and checks the
compressed packet shape and slot. Its timing ends at the probe's join and
decode, before full pool state application or executable quote calculation.

Set `ROBIN_PROBE_BINANCE=1` to include SPCXB/USDT BBO on the same monotonic
clock as the sequencer/feed-log join. Pipe the probe's JSONL to
`python3 scripts/push_leadlag.py` to compare Binance mid to the same
hash-matched oracle updates at feed arrival, log arrival, and decode time.
Positive lag means Binance leads. The analysis is for oracle prices and does
not include a fixed-size swap quote.

The Binance BBO records in the binary journal use positional fields with
the original decimal strings. The current reader also reads earlier records
that stored each field name. Update both ends of a binary relay together.
The push latency probe now writes the same binary journal to stdout:

```sh
target/debug/examples/push_latency 305 > capture.bin
target/debug/robin-leadlag replay capture.bin | python3 scripts/push_leadlag.py
zstd -q capture.bin
zstd -dc capture.bin.zst | target/debug/robin-leadlag replay - | python3 scripts/push_leadlag.py
```

For the current Metric raw capture supervisor and reconnect checkpoints, see
[CHECKPOINT_RECOVERY.md](CHECKPOINT_RECOVERY.md). Recovery markers and checkpoint
generations are recorded in the binary journal; live quote catch-up is separate.
