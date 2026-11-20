# Metric inventory execution preparation

Status: staged executor, multi-ticker inventory engine, offline replay/shadow input, signing/outbox/submit components and read-only startup preflight. **Not a deployed trader.** No wallet key was loaded, no approval/order/deployment was sent, no exchange short was opened, and recorder services were not restarted. Live push-state/receipt observer wiring is still required; the current recorder does not automatically trade.

## Inventory baseline

Fill `.env` using the keys in `.env.inventory.example`. Values are exact **token quantities**, not USDG notional:

```dotenv
INITIAL_STOCKS_NVDA=3.25
INITIAL_EXCHANGE_SHORT_NVDA=3.25
```

The keys cover AAPL, GOOGL, INTC, META, MU, NVDA, QQQ, SPCX, SPY and TSLA. Blank/missing keys block loading; use explicit `0` for an unfunded ticker or an unhedged position. The parser ignores unrelated credentials and never evaluates shell expressions. Exchange short is a user declaration, not verified exchange balance. Tokenized stock versus exchange share equivalence, corporate actions, funding/borrow and venue basis remain separate economic risks.

- Relative position = actual on-chain base quantity minus fixed `INITIAL_STOCKS` quantity. Market-price changes never redefine zero.
- Available to sell = actual on-chain quantity minus pending sell reservations.
- Maximum relative short quantity = initial base quantity, reached when actual base balance is zero. There is no on-chain borrowing.
- Declared hedged net = actual on-chain quantity minus declared exchange short. Changing that hedge is not performed by this module.
- `max_position_usdg` in the inventory policy means **additional long exposure above baseline**, default 500 USDG per ticker. Set 0 for sell-and-buy-back only. Each wallet also needs free USDG to buy above baseline; pre-funded stocks alone do not provide it.
- At baseline, both buy/open and sell/open are eligible. Above baseline only sell/close; below baseline only buy/close. Close quantity cannot cross zero; a new opposite episode requires a subsequent signal. Open/close bps are separately configurable, including negative close thresholds.

The shared Rust baseline policy is used by the shadow/replay entry point. Existing historical Python reports predate this policy and have **not** been relabeled as baseline-hedged portfolio results.

```sh
cargo run --offline --example metric_inventory_shadow -- \
  config/metric-inventory-shadow.json .env --audit
# One Request JSON per line: ticker, now_ns, inventory, observation.
cargo run --offline --example metric_inventory_shadow -- \
  config/metric-inventory-shadow.json .env < observations.jsonl
```

Audit shows declared initial positions, not RPC-verified balances. Shadow takes explicit observed inventory and emits both eligible intents and maximum sizing requests; it does not invent fills. Quote exact chosen quantities from local EVM, including pool fees/impact. The proposed maximum buy size uses reference ask and may need reducing when exact pool cost/slippage exceeds cash.

## Execution and account ownership

`src/execution/portfolio.rs` owns one wallet's nonce, shared USDG, every ticker baseline, and a single unresolved transaction across all tickers. A persisted baseline/config cannot silently change on restart. Cached startup balances must match persisted balances; reconnect never clears a pending reservation. External wallet activity requires explicit reconciliation, not automatic baseline reset. Use one state directory/process per wallet; directory locks cannot protect a second unrelated directory.

Admission, exact integer sizing, baseline checks, signing and ABI encoding have no RPC reads. They require fresh local market/account state, dependency-derived provider expiry and current epoch/version. The default 20 ms is an expiry budget, not a delay or demonstrated inclusion guarantee. Native gas balance, verified executor/provider permissions and input-token allowance are required cached evidence before signing.

`metric.rs` encodes `trade(pool,buy,baseQuantity,usdgLimit,deadline)` from the immutable Intent; arbitrary opaque router calldata is not accepted by the Portfolio path. The older single-pool `Engine`/shadow example remains for policy parity and is not the recommended multi-ticker runtime.

`store.rs` persists a checksum-protected dual-slot binary outbox before submission; restart preserves raw bytes, nonce and inventory. `transport.rs` fans out identical bytes to bounded endpoints using only `eth_sendRawTransaction`, with reusable async clients. ACK/timeouts never count as fills. No automatic nonce replacement or pending release is implemented.

`receipt.rs` checks transaction identity, independently supplied canonical block hash, executor `Executed`, packed pool `Swap` deltas and stock/USDG wallet `Transfer` totals. `Portfolio::settle` additionally checks exact size/slippage/balance results. Reverts consume nonce without changing token balances. Settlement disables admission until reconciliation. One confirmation is not finality; post-settlement reorg rollback still requires an external observer/recovery workflow. The caller must not fabricate canonical evidence from the receipt itself.

## Minimal executor, without the public Metric router

`contracts/metric-executor/src/MetricInventoryExecutor.sol` calls the pool directly and implements `metricOmmSwapCallback`. An EOA cannot implement the payment callback merely by knowing pool state. This owner-only executor fixes the recipient to owner, pays from owner allowance, binds pool/token order/code hash, requires exact base amount, and atomically checks limits and actual owner balance deltas. Buy = exact base output/max USDG input; sell = exact base input/min USDG output. Partial fills revert. Inventory remains in the owner's wallet.

ABI verified against archived pool execution and public [Metric pool source](https://github.com/Metricxyz/pool-contracts). Callback signature is `metricOmmSwapCallback(int256,int256,bytes)`. No public Metric router or Permit2 is required for this adapter; token approval is to this executor. Deploy/configure/approve remain unperformed. The executable's owner immutable must be the intended wallet; pin its deployed runtime code hash in startup config.

## Startup/background preflight

```sh
# Supply real wallet/router addresses in a copy of the catalog,
# plus top-level executor_codehash. Read-only; no transaction is sent.
python3 scripts/check_executor_startup.py --config configured-live-catalog.json \
  --rpc RPC_URL --output startup-evidence.json
```

All account/code/pool reads use one block; chain ID, executor owner/code hash, pool binding/token order, native/token balances, allowances, pending nonce and anchor hash are checked. A nonzero-owner `getSellAndBuyPrices()` call exercises provider pool registration/blacklist checks that zero-origin quote simulations skip. This does not replace exact-size local swap simulation or exchange hedge verification. Catch up pushed events after the anchor before admitting signals; the preflight report is not an indefinitely valid account snapshot.

The [oracle source](https://github.com/Metricxyz/oracle-contracts/blob/main/contracts/oracles/providers/OracleBase.sol) skips some access checks when `tx.origin == 0`. Archived quote-only seeds therefore lacked pool blacklist/registration storage. These must be seeded from actual startup reads/traces, not defaulted in production. The startup preflight verifies access but does not automatically merge those trace slots into the current recorder checkpoint.

## Verification and limits

- Rust tests cover fixed-unit parsing, long/short baseline behavior, global cash/nonce reservation, restart/config binding, missing permissions/allowances, exact EIP-1559 signing, binary persistence, stale state/expiry, and settlement gates.
- `python3 scripts/check_inventory_policy.py`: replay/shadow boundary tests for both entry directions, smaller/negative close threshold, no close crossing zero, no oversell and blank baseline rejection.
- `python3 scripts/check_execution_policy_parity.py`: existing 400-case pure-policy parity with Python, not full portfolio PnL parity.
- `SVM_HOME=/tmp/metric-svm forge test --root contracts/metric-executor`: eight contract tests including 256 fuzz cases, reversed token order, partial fill/slippage rollback, callback and allowance checks.
- `reports/metric-execution/archived-executor-probes.json`: AAPL/META/NVDA/QQQ/SPCX real archived pool/provider bytecode, injected executor and **synthetic ERC20 balances/code/allowances plus explicitly assumed valid oracle pool permissions**. Buy/sell succeed; receipt decoder matches resulting balances and rejects missing transfers/noncanonical hashes. These are conditional local integration tests, not funded live transactions. The other five stock pools do not yet have this archived swap proof.

Remaining before live operation: production feed-to-exact-size observation bridge, pinned startup trace integration, independent canonical receipt/account observer with reorg recovery, binary lifecycle audit stream/runtime supervision, deployed/configured executor and approvals, actual quantities/hedge verification, and a separately authorized small funded end-to-end test. No live switch or funded test has been enabled in this work.

## Pool comparison research (2026-11-19)

`reports/ohio-pool-ranking-20261119/RESULTS.md` contains a two-window,
20 ms fixed-baseline experiment. `scripts/baseline_policy.py::best_pool` is an
offline route-selection prototype: routes for the same token share inventory
and a baseline/cap; a close may use another pool. This does not add multi-route
signing to the Rust Portfolio, which still binds one pool per configured stock.
No live router-selection rollout or actual trade was performed.

Pool HY quote clocks now observe local state updates and independent expiry
timers, without reference-BBO freshness gating. Quote-only export is separate
from policy backtests; reference ticks cannot determine pool observation time.
