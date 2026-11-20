# Additional AMM capture and calldata reconstruction

## Current result (2026-11-14)

The uninterrupted recorder already subscribes to **all** Nitro messages and
**all** chain logs. No socket restart or extra hot-path query was needed to
include non-Metric pools. `config/amm.json` registers a frozen public discovery
snapshot: 55 pools with >= $100k reported liquidity and >= $10k daily volume,
including 5 existing Metric pools and **50 additional pools**. Five public
GeckoTerminal pages were queried; this is not an exhaustive on-chain census.
The frozen tape audit observed 53/55 catalog pools and 124,752 matching logs.
Zero events for the other two is not evidence of missing subscriptions.

DefiLlama API snapshot: Uniswap V4 $201.70m/day, Uniswap V3 $170.47m/day,
Aero Slipstream $86.59m/day, Metric V1 $22.54m/day, Ramses CL V2 $12.33m/day.
These are protocol volumes, not pool depth. Retrieval snapshots are retained in
`reports/amm/defillama-dex-snapshot.json` and `reports/amm/gecko-page-*.json`.

Selected direct USDG candidates in the GeckoTerminal snapshot:

| Venue | Pair | Reported liquidity | 24h volume | Identifier |
|---|---|---:|---:|---|
| Uniswap V3, 0.01% | WETH/USDG | $11.73m | $138.25m | `0x52e65b17fb6e5ba00ed806f37afcd2daa50271ca` |
| Uniswap V3, 0.05% | WETH/USDG | $2.88m | $8.29m | `0x69bfaf19c9f377bb306a89aed9f6b07e2c1a8d9a` |
| Uniswap V3, 0.05% | NVDA/USDG | $1.92m | $5.30m | `0xd4eb21209c4d6093f80b5b84f5c45cc093ea14a3` |
| Uniswap V3, 0.05% | SPCX/USDG | $1.65m | $3.20m | `0xc61284332117c3fb23a2a56cceffd07f7af60029` |
| Aero Slipstream | WETH/USDG | $1.45m | $77.21m | `0x7615926023bb149f36095645c2a81dc367d39750` |

Pool identities must use token addresses. Display names are not sufficient.
V4 IDs are 32-byte IDs, not contract addresses. Native ETH requires wrapping
before use in a WETH pool. WETH-quoted stock pools need a third conversion leg
or explicit WETH inventory accounting; do not compare WETH quotes to USDG.

## What is actually verified

`scripts/bootstrap_v3.py` is an explicitly initialization-only RPC tool. At one
fixed block it seeds 11 canonical Uniswap V3 pools: fee, spacing, price, active
liquidity, **12,138 bitmap words and 5,767 initialized ticks**. Pool factory
and actual token addresses are checked. All net tick liquidity sums to zero;
net liquidity through the current tick equals reported active liquidity.

The pure-integer `scripts/v3_state.py` implements both exact input/output,
word-boundary traversal, initialized-tick crossing, fee rounding, liquidity
mint/burn and arbitrary positive token sizes. It never requests missing data.
All 44 buy/sell checks (0.02 and 0.1 base tokens) matched pinned-block QuoterV2
amounts AND end prices. Quote-only two-sided compute measured about 175–191 us
median per pool in this offline Python experiment. This excludes networking,
calldata execution, queueing and inclusion, and is not a production latency SLA.

## Calldata-only continuity is NOT complete

`scripts/v3_calldata.py` decodes standard direct V3 calls, single-hop router
calls, multicalls and supported Universal Router V3 commands. The streaming
experiment `scripts/amm_feed_state.py` updates pool math from decoded calldata.
Logs only validate/invalidate its result; their prices/liquidity are NEVER
copied back into state. Missing router semantics, transport gaps and parity
errors disable the affected pool. All emitted proposals are explicitly
`state_complete=false`, `executable=false`, `provisional=true`; these must not
be admitted to the profitable-route/HY dataset.

Real tape evidence is decisive: only 73 of 19,356 tracked transactions directly
used the two registered official routers. Major bot contracts use packed inputs
with storage-defined routes, internal calls and conditional execution. No
verified source was returned by Sourcify for the three largest inspected bots.
Their fixed-block bytecode is saved for further local execution work.

The post-bootstrap replay invalidated all 11 pools after unsupported transitions;
**there are no accepted continuous calldata-only bid/ask series yet**. The
initial quote engine works; the transaction follower is not production-ready.
Correct arbitrary transaction support requires local execution/complete semantic
adapters including router dependencies, conditional reverts, multicall ordering,
LP position changes and callbacks. More selector guessing cannot establish this.
V4 hooks, Aero dynamic fees, Ramses and other forks are currently raw-capture only.

## Artifacts and replay

- `captures/all-push-20261115-midnight-utc/amm-manifest.json`: anchor, hashes and
  link to the uninterrupted raw binary tape.
- `captures/amm-bootstrap.bin.zst`: binary catalog plus full initial checkpoint;
  round-trip checked with `scripts/tape.py`.
- `captures/amm-checkpoint.json`: editable initialization input for the engine.
- `reports/amm/calldata-replay.json`: explicit per-pool continuity failures.
- `reports/amm/router-coverage.json`: observed transaction routes/selectors.
- `reports/amm/capture-coverage.json`: registered-pool event coverage.

```sh
set -o pipefail
python3 scripts/cut_open_tape.py \
  captures/all-push-20261115-midnight-utc/20261114T194009.317416Z.bin.zst /tmp/amm.bin
python3 scripts/amm_slice.py captures/amm-checkpoint.json /tmp/amm.bin |
  target/release/examples/decode_feed --with-raw |
  python3 scripts/amm_feed_state.py captures/amm-checkpoint.json --sizes 0.02,0.1 |
  target/release/examples/push_latency encode |
  zstd -3 -o /tmp/amm-proposals.bin.zst
python3 -m unittest discover -s tests -p 'test_*.py'
```

## Route economics

For an already-updated Metric pool and the SAME token/quote unit, the round-trip
edge for q base tokens is Metric sell proceeds minus AMM exact-output buy cost,
minus gas/wrapping/other costs. Both pool quotes already include their fees.
Simulate legs in order and include the first leg's state changes. Atomic execution
can require minimum net profit and revert both legs; failed transactions still
cost gas. This recorder never submits transactions.

Buying an AMM first and waiting for a future provider update is a different,
non-atomic inventory strategy. Do not credit the predicted future Metric price
as a guaranteed exit. Competing transactions, oracle thresholds, guard rejection,
arrival-to-inclusion latency and unfinished inventory all affect realized PnL.

Sources:
- https://defillama.com/dexs/chain/robinhood-chain
- https://api.llama.fi/overview/dexs/Robinhood%20Chain?excludeTotalDataChart=true&excludeTotalDataChartBreakdown=true
- https://api.geckoterminal.com/api/v2/networks/robinhood/pools?page=1
- https://developers.uniswap.org/docs/protocols/v3/deployments/v3-robinhood-chain-deployments
- https://github.com/Uniswap/v3-core/blob/main/contracts/libraries/SwapMath.sol
- https://github.com/Uniswap/v3-core/blob/main/contracts/libraries/TickBitmap.sol

## Custom router decoding update

Two custom formats now have bytecode-verified first-swap decoders: 520/b2460c48
and c33/000000e7. They matched 10,933 first attempted calls, including 4,460
chronological held-out cases, with zero argument mismatches. The formats occur
in 47.73% of the 19,356 target-pool transaction sample; this is not continuous
state coverage. Router 29's intents were parsed and its vault-balance cap was
confirmed in synthetic bytecode probes. Full execution/callbacks remain open.
See `reports/amm/router-decoding.md` for formats, evidence and limitations.
The optional registry integration enforces identical pool/router checkpoint
anchors; existing snapshots differ and cannot be silently combined.

A coherent full-tick V3 + EVM checkpoint now exists at `0x6d33b46`. The local
storage-to-quote bridge matches all 44 pinned Quoter checks and follows new LP
tick keys via local EVM KECCAK preimages. This does not complete continuous
execution: the new checkpoint still lacks complete router/system/token dependency
hydration, and other AMM families remain outside the canonical V3 quote engine.
See `reports/amm/router-decoding.md` for exact scope and binary artifacts.
