# Full-state path for continuous push-only quotes

Status checked 2026-11-14: the sparse REVM follower is an experiment, not a
production-complete state replica. Router-specific decoding and finite parity
fixtures do not establish complete future execution coverage.

2026-11-15 correction: a full node is an alternative, not a demonstrated
prerequisite for a useful bounded pool follower. The user authorized continuing
startup-only RPC discovery. We are testing a fixed-anchor checkpoint enriched
with pre-anchor execution traces, proxy references and explicitly queried fixed
storage slots, followed by strictly RPC-free held-out execution. Do not interpret
the resource discussion below as proof that this approach cannot work. Its
coverage must be measured; unknown dependencies must still stop trust.

## Why the pool checkpoint is insufficient

The coherent checkpoint at block `0x6d369e9` contained 21,570 accounts and 35,966
explicit storage slots. Its first following transaction read an uninitialized
EIP-1967 implementation slot. That pointer can be initialized, but implementation
code may then read other mappings, balances, allowances, external contracts, or
newly introduced dependencies. Calldata carries inputs, not all their initial
state values. Unknown slots cannot safely be interpreted as zero.

Adding observed dependencies remains useful for controlled replay experiments.
It is not evidence that uninterrupted arbitrary future transactions can execute.
The report is `reports/amm/coherent-replay-summary.json`.

## Architecture retaining zero request/response on the decision path

1. Bootstrap a complete, coherent Nitro execution database, from a verified
   snapshot or genesis sync. Initial state acquisition is outside the hot path.
2. Consume sequencer messages in order using the native, version-pinned Nitro
   execution engine, including system transactions and all enabled precompiles.
3. Add an in-process observer at transaction/block commit. Copy the relevant
   pool/provider writes from the executed local state and push versioned binary
   records to the quote reducer. No remote RPC, polling, or local eth_call per
   quote. Do not open a live node's database with an unrelated unsafe writer.
4. Keep arbitrary-size quote state locally. A provider update invalidates and
   recomputes affected quotes immediately. Include LP changes and settings.
5. Record sequence/hash, arrival time, local execution completion, quote completion
   and Binance arrival time separately. Measure latency instead of assuming native
   execution is fast enough. Test all selected venue types, not only the 11 V3 pools.
6. Reject discontinuities. Keep confirmed/reorg status distinct from the earliest
   speculative quote; never repair a quote by substituting a swap log's price.

Background node synchronization can use L1 execution/beacon endpoints. It must
not become a per-signal remote request before making a trading decision. Any
snapshot must be compatible with the running Nitro/ArbOS version and independently
checked before trusted quote production starts.

## Resource finding and unresolved inputs

This workstation: 62 GiB RAM, 39 GiB free on the project filesystem at inspection.
A subsequent full mount inventory found about 1.1 TiB free on `/mnt`, 946 GiB on
`/`, 306 GiB on `/y`, and 115 GiB on another mounted partition. The earlier 39 GiB
statement was not a machine-wide capacity total. These capacities do not establish
that a current snapshot plus restore/sync overhead fits; snapshot size is still
unverified. No disk was formatted, unmounted, allocated, or written for a node.
Docker is installed;
daemon permissions, remote hosts and L1 credentials have not been assumed. No
running Nitro process or database at the standard `~/.arbitrum` / `~/rh` locations
was found; that is not an exhaustive claim about all user files.

Robinhood's official node guide specifies 64 GB RAM (128 GB recommended), 8+
CPU cores and NVMe storage of `(2 x current chain size) + 20%`, described as several
TB. It requires both L1 execution and beacon endpoints. It lists pruned full-node
snapshots; the linked snapshot explorer returned only an empty directory index
during this inspection. No usable download URL or measured snapshot size has
been verified. Do not start a multi-TB sync on this workstation.

Needed: an existing synced database/node, or a suitable host with storage and L1
access. The user has been asked for an available path/host. No server was purchased,
no full sync was launched, and the ongoing market recorder was not restarted.

Sources checked:
- https://docs.robinhood.com/chain/run-a-full-node/
- https://docs.robinhood.com/chain/connecting/
- https://snapshot-explorer.arbitrum.io/?chain=Robinhood+Chain

## Remaining completion gates

- Complete starting execution state and compatible native execution implementation.
- Continuous mainnet replay, independent state/quote parity and gap/reorg handling.
- Metric/provider updates and every selected AMM implementation, including LP changes.
- Arbitrary-size bid/ask replay from binary records; no substituted log prices.
- All relevant Binance symbols and chain venues actually captured and covered.
- Measured end-to-end latency, Taiwan-to-Ohio timing adjustments and HY analysis
  based only on causally available, trustworthy quotes.

Passing a finite fixture, decoding every feed message, or initializing full V3
tick data alone does not satisfy these gates.

## Latest measured boundary (V9, 2026-11-15)

Startup-only RPC discovery was tested through V9. Complete proof-verified storage for the native filter (1,492 leaves) and shared token manager (193 leaves) works; finite deposit execution matches its real balance diff. V9 initialized 35,445 accounts / 730,796 explicit slots, attached both same-anchor complete domains, then stopped after one committed transaction on an existing sender with nonce 106 absent from every pre-anchor input. There were no selected pool writes before stopping.

Both blockmachine and the official mainnet RPC reject debug_accountRange/debug_storageRangeAt. Full account coverage remains unavailable. A compatible full initial account state source is needed to make this strict whole-transaction executor continuous without runtime requests. This is not a claim that all possible bounded pool-specific approaches require a full node; it is the measured limit of the current implementation and available data. No complete-production or lead-lag claim is made. See reports/amm/continuous-state-blocker.json.
