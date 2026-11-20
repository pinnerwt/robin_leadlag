//! Staged execution core with a shared-wallet multi-ticker Portfolio.
//! Admission never does network I/O; canonical evidence comes from an independent observer.
pub mod baseline;
#[path="../trading/circuit.rs"]
pub mod circuit;
pub mod codec;
pub mod metric;
pub mod portfolio;
pub mod receipt;
mod store;
pub mod transport;
use anyhow::{Context, Result, ensure};
use revm::primitives::U256;
use serde::{Deserialize, Deserializer, Serialize, Serializer};
use std::{
    fs::{File, OpenOptions},
    path::{Path, PathBuf},
};

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct Amount(pub u128);
impl Serialize for Amount {
    fn serialize<S: Serializer>(&self, s: S) -> std::result::Result<S::Ok, S::Error> {
        s.serialize_str(&self.0.to_string())
    }
}
impl<'de> Deserialize<'de> for Amount {
    fn deserialize<D: Deserializer<'de>>(d: D) -> std::result::Result<Self, D::Error> {
        String::deserialize(d)?
            .parse()
            .map(Self)
            .map_err(serde::de::Error::custom)
    }
}
#[derive(Clone, Copy, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum Side {
    Buy,
    Sell,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Config {
    pub staging_enabled: bool,
    pub router: Option<[u8; 20]>,
    pub router_selector: Option<[u8; 4]>,
    pub max_gas: u64,
    pub max_fee_per_gas: Amount,
    pub chain_id: u64,
    pub wallet: [u8; 20],
    pub pool: [u8; 20],
    pub base_decimals: u32,
    pub max_position_usdg: Amount,
    pub open_bps: i32,
    pub close_bps: i32,
    pub entry_side: Side,
    pub slippage_bps: u32,
    pub execution_budget_ns: u64,
    pub max_bbo_age_ns: u64,
    pub max_state_age_ns: u64,
    pub max_account_age_ns: u64,
    pub gas_cost_usdg: Amount,
}
impl Config {
    pub fn validate(&self) -> Result<()> {
        ensure!(self.chain_id == 4663, "chain mismatch");
        ensure!(
            self.wallet != [0; 20] && self.pool != [0; 20],
            "zero address"
        );
        ensure!(self.base_decimals <= 36, "invalid size config");
        ensure!(
            self.open_bps >= 0 && self.close_bps > -10000 && self.slippage_bps < 10000,
            "invalid thresholds"
        );
        ensure!(
            self.max_bbo_age_ns > 0 && self.max_state_age_ns > 0 && self.max_account_age_ns > 0,
            "invalid freshness config"
        );
        Ok(())
    }
}
#[derive(Clone, Debug, Default, Serialize, Deserialize, PartialEq, Eq)]
pub struct Inventory {
    pub base: Amount,
    pub cash: Amount,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Observation {
    pub pool: [u8; 20],
    pub epoch: u64,
    pub state_version: u64,
    pub state_valid: bool,
    pub state_received_ns: u64,
    pub bbo_received_ns: u64,
    pub provider_valid_until_ns: u64,
    /// USDG per whole token, scaled by 1e8. FX conversion is upstream and explicit.
    pub bid_e8: Amount,
    pub ask_e8: Amount,
    /// Exact base quantity and total pool costs/proceeds, including pool fee/impact.
    pub quantity: Amount,
    pub pool_bid_usdg: Amount,
    pub pool_ask_usdg: Amount,
}
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
pub struct Intent {
    pub side: Side,
    pub opening: bool,
    pub quantity: Amount,
    pub quote_usdg: Amount,
    /// Buy maximum input or sell minimum output; immutable after reservation.
    pub limit_usdg: Amount,
    pub signal_ns: u64,
    pub valid_until_ns: u64,
    pub epoch: u64,
    pub state_version: u64,
}
fn micro(q: u128, price: u128, decimals: u32) -> Result<u128> {
    let n = U256::from(q)
        .checked_mul(U256::from(price))
        .context("valuation overflow")?;
    let scale = U256::from(10).pow(U256::from(decimals)) * U256::from(100);
    (n / scale)
        .try_into()
        .map_err(|_| anyhow::anyhow!("valuation overflow"))
}
fn micro_ceil(q: u128, price: u128, decimals: u32) -> Result<u128> {
    let n = U256::from(q)
        .checked_mul(U256::from(price))
        .context("valuation overflow")?;
    let d = U256::from(10).pow(U256::from(decimals)) * U256::from(100);
    (n / d + U256::from(u8::from(n % d != U256::ZERO)))
        .try_into()
        .map_err(|_| anyhow::anyhow!("valuation overflow"))
}
fn ratio(n: u128, m: u128, d: u128, ceil: bool) -> Result<u128> {
    let n = U256::from(n) * U256::from(m);
    let d = U256::from(d);
    let q = n / d + U256::from(u8::from(ceil && n % d != U256::ZERO));
    q.try_into().map_err(|_| anyhow::anyhow!("ratio overflow"))
}
fn fresh(now: u64, stamp: u64, limit: u64) -> bool {
    now.checked_sub(stamp).is_some_and(|n| n <= limit)
}
/// Pure policy, shared by shadow/replay integration. No sleep for the modeled 20 ms.
pub fn decide(
    c: &Config,
    inventory: &Inventory,
    episode_open: bool,
    o: &Observation,
    now: u64,
) -> Result<Option<Intent>> {
    c.validate()?;
    ensure!(o.pool == c.pool, "wrong pool");
    if !o.state_valid
        || !fresh(now, o.state_received_ns, c.max_state_age_ns)
        || !fresh(now, o.bbo_received_ns, c.max_bbo_age_ns)
    {
        return Ok(None);
    }
    let deadline = now
        .checked_add(c.execution_budget_ns)
        .context("clock overflow")?;
    if deadline > o.provider_valid_until_ns {
        return Ok(None);
    }
    ensure!(
        o.quantity.0 > 0
            && o.bid_e8.0 > 0
            && o.ask_e8.0 >= o.bid_e8.0
            && o.pool_bid_usdg.0 > 0
            && o.pool_ask_usdg.0 >= o.pool_bid_usdg.0,
        "invalid quote"
    );
    let side = if episode_open {
        match c.entry_side {
            Side::Buy => Side::Sell,
            Side::Sell => Side::Buy,
        }
    } else {
        c.entry_side
    };
    let threshold = if episode_open {
        c.close_bps
    } else {
        c.open_bps
    };
    let (numerator, denominator, amount, limit) = match side {
        Side::Buy => {
            let total = o
                .pool_ask_usdg
                .0
                .checked_add(c.gas_cost_usdg.0)
                .context("cost overflow")?;
            let post = inventory
                .base
                .0
                .checked_add(o.quantity.0)
                .context("position overflow")?;
            if total > inventory.cash.0
                || micro_ceil(post, o.ask_e8.0, c.base_decimals)? > c.max_position_usdg.0
            {
                return Ok(None);
            }
            let limit = ratio(
                o.pool_ask_usdg.0,
                10000 + c.slippage_bps as u128,
                10000,
                false,
            )?
            .min(inventory.cash.0 - c.gas_cost_usdg.0);
            (
                micro(o.quantity.0, o.bid_e8.0, c.base_decimals)?,
                total,
                o.pool_ask_usdg.0,
                limit,
            )
        }
        Side::Sell => {
            if o.quantity.0 > inventory.base.0 || o.pool_bid_usdg.0 <= c.gas_cost_usdg.0 {
                return Ok(None);
            }
            (
                o.pool_bid_usdg.0 - c.gas_cost_usdg.0,
                micro_ceil(o.quantity.0, o.ask_e8.0, c.base_decimals)?,
                o.pool_bid_usdg.0,
                ratio(
                    o.pool_bid_usdg.0,
                    10000 - c.slippage_bps as u128,
                    10000,
                    true,
                )?,
            )
        }
    };
    if denominator == 0
        || U256::from(numerator) * U256::from(10000)
            < U256::from(denominator) * U256::from((10000i64 + threshold as i64) as u64)
    {
        return Ok(None);
    }
    Ok(Some(Intent {
        side,
        opening: !episode_open,
        quantity: o.quantity,
        quote_usdg: Amount(amount),
        limit_usdg: Amount(limit),
        signal_ns: now,
        valid_until_ns: o.provider_valid_until_ns,
        epoch: o.epoch,
        state_version: o.state_version,
    }))
}
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Pending {
    pub intent: Intent,
    pub nonce: u64,
    pub hash: [u8; 32],
    pub raw: Vec<u8>,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
struct Snapshot {
    version: u32,
    config: Config,
    next_nonce: u64,
    inventory: Inventory,
    episode_open: bool,
    pending: Option<Pending>,
}
/// Owns the file lock, reservation and nonce. A timeout or ACK never clears pending.
pub struct Engine {
    root: PathBuf,
    _lock: File,
    state: Snapshot,
    ready: Option<(u64, u64, u64)>,
    poisoned: bool,
}
impl Engine {
    pub fn open(
        root: &Path,
        config: Config,
        initial_nonce: u64,
        inventory: Inventory,
    ) -> Result<Self> {
        config.validate()?;
        std::fs::create_dir_all(root)?;
        let lock = OpenOptions::new()
            .read(true)
            .write(true)
            .create(true)
            .truncate(false)
            .open(root.join("writer.lock"))?;
        lock.try_lock().context("execution writer already active")?;
        let state = if root.join(store::NAME).exists() {
            let payload = store::read(root)?;
            ensure!(payload.len() >= 4, "short execution frame");
            ensure!(
                u32::from_le_bytes(payload[..4].try_into()?) as usize == payload.len() - 4,
                "bad execution frame"
            );
            let s: Snapshot =
                serde_json::from_value(crate::execution_journal::parse(&payload[4..])?)?;
            ensure!(
                s.version == 1
                    && serde_json::to_value(&s.config)? == serde_json::to_value(&config)?,
                "execution config mismatch"
            );
            if let Some(p) = &s.pending {
                ensure!(
                    codec::hash(&p.raw) == p.hash && p.nonce == s.next_nonce,
                    "corrupt pending transaction"
                );
            }
            s
        } else {
            Snapshot {
                version: 1,
                config,
                next_nonce: initial_nonce,
                inventory,
                episode_open: false,
                pending: None,
            }
        };
        let mut engine = Self {
            root: root.to_owned(),
            _lock: lock,
            state,
            ready: None,
            poisoned: false,
        };
        engine.persist()?;
        Ok(engine)
    }
    fn persist(&mut self) -> Result<()> {
        let result = (|| {
            store::write(
                &self.root,
                &crate::execution_journal::frame(&serde_json::to_value(&self.state)?)?,
            )
        })();
        if result.is_err() {
            self.poisoned = true;
            self.ready = None;
        }
        result
    }
    pub fn pending(&self) -> Option<&Pending> {
        self.state.pending.as_ref()
    }
    pub fn inventory(&self) -> &Inventory {
        &self.state.inventory
    }
    pub fn disconnect(&mut self) {
        self.ready = None;
    }
    /// Startup/reconnect background reconciliation: admission requires exact agreement.
    pub fn synchronize(
        &mut self,
        epoch: u64,
        state_version: u64,
        account_ns: u64,
        nonce: u64,
        inventory: &Inventory,
    ) -> Result<()> {
        self.ready = None;
        ensure!(!self.poisoned, "persistence failure requires restart");
        ensure!(
            self.state.pending.is_none(),
            "unresolved nonce requires receipt reconciliation"
        );
        ensure!(
            nonce == self.state.next_nonce && inventory == &self.state.inventory,
            "account reconciliation mismatch"
        );
        self.ready = Some((epoch, state_version, account_ns));
        Ok(())
    }
    pub fn signal(&mut self, o: &Observation, now: u64) -> Result<Option<Intent>> {
        if self.poisoned || self.state.pending.is_some() {
            return Ok(None);
        }
        let Some((epoch, version, account_ns)) = self.ready else {
            return Ok(None);
        };
        if o.epoch != epoch
            || o.state_version < version
            || !fresh(now, account_ns, self.state.config.max_account_age_ns)
        {
            return Ok(None);
        }
        self.ready = Some((epoch, o.state_version, account_ns));
        decide(
            &self.state.config,
            &self.state.inventory,
            self.state.episode_open,
            o,
            now,
        )
    }
    /// Bind a router adapter's signed bytes to a current intent. This method does not broadcast.
    /// The caller must validate the complete router payload against intent before invoking.
    pub fn reserve(
        &mut self,
        o: &Observation,
        now: u64,
        tx: &codec::Transaction,
        key: &k256::ecdsa::SigningKey,
    ) -> Result<Pending> {
        ensure!(
            self.state.config.staging_enabled,
            "signing disabled in shadow mode"
        );
        let intent = self.signal(o, now)?.context("signal not admissible")?;
        ensure!(
            Some(tx.to) == self.state.config.router
                && tx.data.get(..4)
                    == self
                        .state
                        .config
                        .router_selector
                        .as_ref()
                        .map(|s| s.as_slice()),
            "unapproved router/selector"
        );
        ensure!(
            tx.gas <= self.state.config.max_gas
                && tx.max_fee <= self.state.config.max_fee_per_gas.0,
            "gas cap exceeded"
        );
        ensure!(
            codec::wallet(key) == self.state.config.wallet,
            "wrong signer"
        );
        ensure!(
            tx.nonce == self.state.next_nonce
                && tx.value == 0
                && tx.to != [0; 20]
                && tx.data.len() >= 4,
            "invalid transaction envelope"
        );
        // Prevent accidentally signing the quote-only simulator as an order.
        ensure!(
            !matches!(
                &tx.data[..4],
                [0x65, 0x8b, 0x6c, 0xb7] | [0xec, 0x06, 0x90, 0x57]
            ),
            "simulation calldata is not a swap"
        );
        let raw = tx.sign(key)?;
        let p = Pending {
            intent,
            nonce: tx.nonce,
            hash: codec::hash(&raw),
            raw,
        };
        self.state.pending = Some(p.clone());
        self.persist()?;
        Ok(p)
    }
    /// Reconciled canonical result from the observer; not a raw log/ACK callback.
    /// Balances are at the receipt block, checked against the tracked swap by the observer.
    pub fn settle(&mut self, e: &ReceiptEvidence) -> Result<()> {
        ensure!(!self.poisoned, "persistence failure requires restart");
        let p = self
            .state
            .pending
            .as_ref()
            .context("no pending transaction")?;
        ensure!(
            e.hash == p.hash
                && e.wallet == self.state.config.wallet
                && e.pool == self.state.config.pool
                && e.nonce == p.nonce,
            "receipt identity mismatch"
        );
        ensure!(
            e.block_hash != [0; 32] && e.block_hash == e.canonical_hash && e.confirmations >= 1,
            "noncanonical or unconfirmed receipt"
        );
        let mut next = self.state.clone();
        if e.success {
            ensure!(e.matched_swap, "successful receipt lacks tracked swap");
            let inv = &self.state.inventory;
            let q = p.intent.quantity.0;
            let value = e.usdg_amount.0;
            let expected = match p.intent.side {
                Side::Buy => {
                    ensure!(value <= p.intent.limit_usdg.0, "buy limit violated");
                    Inventory {
                        base: Amount(inv.base.0.checked_add(q).context("base overflow")?),
                        cash: Amount(inv.cash.0.checked_sub(value).context("cash underflow")?),
                    }
                }
                Side::Sell => {
                    ensure!(value >= p.intent.limit_usdg.0, "sell limit violated");
                    Inventory {
                        base: Amount(inv.base.0.checked_sub(q).context("base underflow")?),
                        cash: Amount(inv.cash.0.checked_add(value).context("cash overflow")?),
                    }
                }
            };
            ensure!(
                expected == e.balances,
                "fill/balance mismatch or partial fill"
            );
            next.inventory = expected;
            next.episode_open = p.intent.opening;
        } else {
            ensure!(
                e.balances == self.state.inventory,
                "revert balance mismatch"
            );
        }
        next.next_nonce = next.next_nonce.checked_add(1).context("nonce overflow")?;
        next.pending = None;
        self.state = next;
        self.ready = None;
        self.persist()
    }
}
#[derive(Clone, Debug)]
pub struct ReceiptEvidence {
    pub hash: [u8; 32],
    pub wallet: [u8; 20],
    pub pool: [u8; 20],
    pub nonce: u64,
    pub block_hash: [u8; 32],
    pub canonical_hash: [u8; 32],
    pub confirmations: u64,
    pub success: bool,
    pub matched_swap: bool,
    pub usdg_amount: Amount,
    pub balances: Inventory,
}

#[cfg(test)]
mod tests {
    use super::*;
    use alloy_consensus::{Transaction as _, TxEnvelope};
    use alloy_eips::eip2718::Decodable2718;
    fn key() -> k256::ecdsa::SigningKey {
        k256::ecdsa::SigningKey::from_slice(&[1; 32]).unwrap()
    }
    fn config() -> Config {
        Config {
            staging_enabled: true,
            router: Some([3; 20]),
            router_selector: Some([1, 2, 3, 4]),
            max_gas: 500000,
            max_fee_per_gas: Amount(100),
            chain_id: 4663,
            wallet: codec::wallet(&key()),
            pool: [2; 20],
            base_decimals: 18,
            max_position_usdg: Amount(500_000_000),
            open_bps: 10,
            close_bps: -10,
            entry_side: Side::Buy,
            slippage_bps: 1,
            execution_budget_ns: 20_000_000,
            max_bbo_age_ns: 1_000_000_000,
            max_state_age_ns: 1_000_000_000,
            max_account_age_ns: 10_000_000_000,
            gas_cost_usdg: Amount(0),
        }
    }
    fn inventory() -> Inventory {
        Inventory {
            base: Amount(0),
            cash: Amount(500_000_000),
        }
    }
    fn quote() -> Observation {
        Observation {
            pool: [2; 20],
            epoch: 1,
            state_version: 1,
            state_valid: true,
            state_received_ns: 1_000_000_000,
            bbo_received_ns: 1_000_000_000,
            provider_valid_until_ns: 2_000_000_000,
            bid_e8: Amount(100_000_000_000),
            ask_e8: Amount(100_000_000_000),
            quantity: Amount(100_000_000_000_000_000),
            pool_bid_usdg: Amount(99_700_000),
            pool_ask_usdg: Amount(99_800_000),
        }
    }
    fn tx() -> codec::Transaction {
        codec::Transaction {
            nonce: 7,
            priority_fee: 1,
            max_fee: 10,
            gas: 100000,
            to: [3; 20],
            value: 0,
            data: vec![1, 2, 3, 4],
        }
    }
    fn root(name: &str) -> PathBuf {
        let p =
            std::env::temp_dir().join(format!("metric-execution-{}-{name}", std::process::id()));
        let _ = std::fs::remove_dir_all(&p);
        p
    }
    fn ready(root: &Path) -> Engine {
        let mut e = Engine::open(root, config(), 7, inventory()).unwrap();
        e.synchronize(1, 1, 1_000_000_000, 7, &inventory()).unwrap();
        e
    }
    fn receipt(p: &Pending, success: bool) -> ReceiptEvidence {
        ReceiptEvidence {
            hash: p.hash,
            wallet: config().wallet,
            pool: config().pool,
            nonce: 7,
            block_hash: [4; 32],
            canonical_hash: [4; 32],
            confirmations: 1,
            success,
            matched_swap: success,
            usdg_amount: Amount(99_800_000),
            balances: if success {
                Inventory {
                    base: quote().quantity,
                    cash: Amount(400_200_000),
                }
            } else {
                inventory()
            },
        }
    }
    #[test]
    fn guards_expiry_future_stale_cap_and_negative_close() {
        let c = config();
        let inv = inventory();
        let q = quote();
        assert!(
            decide(&c, &inv, false, &q, 1_000_000_000)
                .unwrap()
                .is_some()
        );
        let mut bad = q.clone();
        bad.provider_valid_until_ns = 1_019_999_999;
        assert!(
            decide(&c, &inv, false, &bad, 1_000_000_000)
                .unwrap()
                .is_none()
        );
        bad = q.clone();
        bad.bbo_received_ns += 1;
        assert!(
            decide(&c, &inv, false, &bad, 1_000_000_000)
                .unwrap()
                .is_none()
        );
        bad = q.clone();
        bad.quantity = Amount(600_000_000_000_000_000);
        assert!(
            decide(&c, &inv, false, &bad, 1_000_000_000)
                .unwrap()
                .is_none()
        );
        let inv = Inventory {
            base: q.quantity,
            cash: Amount(0),
        };
        bad = q;
        bad.pool_bid_usdg = Amount(99_900_000);
        bad.pool_ask_usdg = Amount(100_000_000);
        assert_eq!(
            decide(&c, &inv, true, &bad, 1_000_000_000)
                .unwrap()
                .unwrap()
                .side,
            Side::Sell
        );
    }
    #[test]
    fn durable_restart_never_reuses_ambiguous_nonce() {
        let path = root("restart");
        let p;
        {
            let mut e = ready(&path);
            p = e.reserve(&quote(), 1_000_000_000, &tx(), &key()).unwrap();
            assert!(e.signal(&quote(), 1_000_000_000).unwrap().is_none());
            assert!(Engine::open(&path, config(), 7, inventory()).is_err());
        }
        let mut e = Engine::open(&path, config(), 999, inventory()).unwrap();
        assert_eq!(e.pending().unwrap().raw, p.raw);
        assert!(e.synchronize(1, 1, 1_000_000_000, 7, &inventory()).is_err());
        assert!(e.signal(&quote(), 1_000_000_000).unwrap().is_none());
        let mut r = receipt(&p, true);
        r.canonical_hash = [5; 32];
        assert!(e.settle(&r).is_err());
        assert!(e.pending().is_some());
        r = receipt(&p, true);
        r.balances.base = Amount(1);
        assert!(e.settle(&r).is_err());
        assert_eq!(e.inventory(), &inventory());
        e.settle(&receipt(&p, true)).unwrap();
        assert!(e.pending().is_none());
        assert!(e.signal(&quote(), 1_000_000_000).unwrap().is_none());
        let inv = e.inventory().clone();
        assert!(e.synchronize(2, 2, 1_000_000_000, 8, &inv).is_ok());
        drop(e);
        std::fs::remove_dir_all(path).unwrap();
    }
    #[test]
    fn revert_keeps_inventory_and_consumes_nonce() {
        let path = root("revert");
        let mut e = ready(&path);
        let p = e.reserve(&quote(), 1_000_000_000, &tx(), &key()).unwrap();
        e.settle(&receipt(&p, false)).unwrap();
        assert_eq!(e.inventory(), &inventory());
        assert!(e.synchronize(1, 1, 1_000_000_000, 7, &inventory()).is_err());
        e.synchronize(1, 1, 1_000_000_000, 8, &inventory()).unwrap();
        drop(e);
        std::fs::remove_dir_all(path).unwrap();
    }
    #[test]
    fn signer_matches_independent_alloy_decoder() {
        let raw = tx().sign(&key()).unwrap();
        let mut bytes = raw.as_slice();
        let decoded = TxEnvelope::decode_2718(&mut bytes).unwrap();
        assert!(bytes.is_empty());
        assert_eq!(decoded.chain_id(), Some(4663));
        assert_eq!(decoded.nonce(), 7);
        assert_eq!(
            decoded.recover_signer().unwrap().as_slice(),
            codec::wallet(&key())
        );
        assert_eq!(decoded.input().as_ref(), tx().data);
    }
    #[test]
    fn gap_and_regressing_state_suppress_admission() {
        let path = root("gap");
        let mut e = ready(&path);
        let mut q = quote();
        q.state_version = 5;
        assert!(e.signal(&q, 1_000_000_000).unwrap().is_some());
        q.state_version = 4;
        assert!(e.signal(&q, 1_000_000_000).unwrap().is_none());
        q.state_version = 5;
        e.disconnect();
        assert!(e.signal(&q, 1_000_000_000).unwrap().is_none());
        drop(e);
        std::fs::remove_dir_all(path).unwrap();
    }
    #[test]
    fn shadow_wrong_signer_router_and_gas_cannot_reserve() {
        let path = root("blocked");
        let mut c = config();
        c.staging_enabled = false;
        let mut e = Engine::open(&path, c, 7, inventory()).unwrap();
        e.synchronize(1, 1, 1_000_000_000, 7, &inventory()).unwrap();
        assert!(e.reserve(&quote(), 1_000_000_000, &tx(), &key()).is_err());
        assert!(e.pending().is_none());
        drop(e);
        std::fs::remove_dir_all(&path).unwrap();
        let mut e = ready(&path);
        let mut t = tx();
        t.to = [6; 20];
        assert!(e.reserve(&quote(), 1_000_000_000, &t, &key()).is_err());
        t = tx();
        t.max_fee = 101;
        assert!(e.reserve(&quote(), 1_000_000_000, &t, &key()).is_err());
        drop(e);
        std::fs::remove_dir_all(path).unwrap();
    }
    #[test]
    fn persistence_error_disables_even_after_reconciliation() {
        let path = root("io-failure");
        let mut e = ready(&path);
        std::fs::remove_file(path.join(store::NAME)).unwrap();
        std::fs::create_dir(path.join(store::NAME)).unwrap();
        assert!(e.reserve(&quote(), 1_000_000_000, &tx(), &key()).is_err());
        assert!(e.signal(&quote(), 1_000_000_000).unwrap().is_none());
        assert!(e.synchronize(1, 1, 1_000_000_000, 7, &inventory()).is_err());
        drop(e);
        std::fs::remove_dir_all(path).unwrap();
    }
    #[test]
    fn u128_binary_roundtrip_has_no_float_loss() {
        let inv = Inventory {
            base: Amount(u128::MAX),
            cash: Amount(500_000_000),
        };
        let f = crate::execution_journal::frame(&serde_json::to_value(&inv).unwrap()).unwrap();
        let copy: Inventory =
            serde_json::from_value(crate::execution_journal::parse(&f[4..]).unwrap()).unwrap();
        assert_eq!(copy, inv);
    }
}
