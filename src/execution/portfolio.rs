//! One durable nonce/cash owner across all ticker baselines. No network in admission.
use super::{
    Amount, Config, Intent, Inventory, Observation, Pending, ReceiptEvidence, Side,
    baseline::{self, Baseline},
    codec, metric, store,
};
use anyhow::{Context, Result, ensure};
use serde::{Deserialize, Serialize};
use std::{
    collections::BTreeMap,
    fs::{File, OpenOptions},
    path::{Path, PathBuf},
};
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Stock {
    pub base_token: [u8; 20],
    pub policy: Config,
    pub baseline: Baseline,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Settings {
    pub wallet: [u8; 20],
    pub stocks: BTreeMap<String, Stock>,
}
impl Settings {
    pub fn validate(&self) -> Result<()> {
        ensure!(!self.stocks.is_empty(), "empty stock catalog");
        let mut tokens = std::collections::BTreeSet::new();
        let mut pools = std::collections::BTreeSet::new();
        for (t, s) in &self.stocks {
            ensure!(
                !t.is_empty()
                    && t.bytes()
                        .all(|b| b.is_ascii_uppercase() || b.is_ascii_digit()),
                "invalid ticker"
            );
            s.policy.validate()?;
            ensure!(
                s.policy.wallet == self.wallet
                    && s.base_token != [0; 20]
                    && tokens.insert(s.base_token)
                    && pools.insert(s.policy.pool),
                "wallet/token/pool catalog conflict"
            );
        }
        Ok(())
    }
}
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct WalletPending {
    pub ticker: String,
    pub pool: [u8; 20],
    pub order: Pending,
}
#[derive(Clone, Serialize, Deserialize)]
struct State {
    version: u32,
    settings: Settings,
    nonce: u64,
    cash: Amount,
    positions: BTreeMap<String, Amount>,
    pending: Option<WalletPending>,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct AccountSnapshot {
    pub nonce: u64,
    pub cash: Amount,
    pub positions: BTreeMap<String, Amount>,
    pub native: Amount,
    pub permissions: BTreeMap<String, Permissions>,
    pub observed_ns: u64,
}
/// Cached startup/background evidence. Observer must verify executor code/owner/binding and live oracle access.
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Permissions {
    pub executor_verified: bool,
    pub provider_access_verified: bool,
    pub base_allowance: Amount,
    pub quote_allowance: Amount,
}
pub struct Portfolio {
    root: PathBuf,
    _lock: File,
    state: State,
    account: Option<AccountSnapshot>,
    epoch: Option<u64>,
    versions: BTreeMap<String, u64>,
    poisoned: bool,
}
impl Portfolio {
    pub fn open(root: &Path, settings: Settings, nonce: u64, cash: Amount) -> Result<Self> {
        settings.validate()?;
        std::fs::create_dir_all(root)?;
        let lock = OpenOptions::new()
            .create(true)
            .truncate(false)
            .read(true)
            .write(true)
            .open(root.join("writer.lock"))?;
        lock.try_lock().context("wallet writer already active")?;
        let state = if root.join(store::NAME).exists() {
            let bytes = store::read(root)?;
            ensure!(
                bytes.len() >= 4
                    && u32::from_le_bytes(bytes[..4].try_into()?) as usize == bytes.len() - 4,
                "corrupt wallet frame"
            );
            let s: State = serde_json::from_value(crate::execution_journal::parse(&bytes[4..])?)?;
            ensure!(
                s.version == 2
                    && serde_json::to_value(&s.settings)? == serde_json::to_value(&settings)?,
                "wallet baseline/config changed; explicit migration required"
            );
            if let Some(p) = &s.pending {
                ensure!(
                    p.order.nonce == s.nonce
                        && codec::hash(&p.order.raw) == p.order.hash
                        && s.settings.stocks[&p.ticker].policy.pool == p.pool,
                    "invalid pending reservation"
                );
            }
            s
        } else {
            State {
                version: 2,
                positions: settings
                    .stocks
                    .iter()
                    .map(|(t, s)| (t.clone(), s.baseline.initial_base))
                    .collect(),
                settings,
                nonce,
                cash,
                pending: None,
            }
        };
        let mut p = Self {
            root: root.to_owned(),
            _lock: lock,
            state,
            account: None,
            epoch: None,
            versions: BTreeMap::new(),
            poisoned: false,
        };
        p.save()?;
        Ok(p)
    }
    fn save(&mut self) -> Result<()> {
        let result = (|| {
            store::write(
                &self.root,
                &crate::execution_journal::frame(&serde_json::to_value(&self.state)?)?,
            )
        })();
        if result.is_err() {
            self.poisoned = true;
            self.disconnect();
        }
        result
    }
    pub fn disconnect(&mut self) {
        self.account = None;
        self.epoch = None;
        self.versions.clear();
    }
    pub fn synchronize(&mut self, epoch: u64, a: AccountSnapshot) -> Result<()> {
        self.disconnect();
        ensure!(!self.poisoned, "persistence failure requires restart");
        ensure!(self.state.pending.is_none(), "pending receipt unresolved");
        ensure!(
            a.nonce == self.state.nonce
                && a.cash == self.state.cash
                && a.positions == self.state.positions,
            "account/baseline mismatch"
        );
        self.account = Some(a);
        self.epoch = Some(epoch);
        Ok(())
    }
    pub fn pending(&self) -> Option<&WalletPending> {
        self.state.pending.as_ref()
    }
    pub fn balances(&self) -> (Amount, BTreeMap<String, Amount>) {
        (self.state.cash, self.state.positions.clone())
    }
    pub fn settings(&self) -> &Settings {
        &self.state.settings
    }
    pub fn inventory(&self, ticker: &str) -> Result<Inventory> {
        Ok(Inventory {
            base: *self.state.positions.get(ticker).context("unknown ticker")?,
            cash: self.state.cash,
        })
    }
    pub fn exposure(&self, ticker: &str) -> Result<baseline::Exposure> {
        let s = self
            .state
            .settings
            .stocks
            .get(ticker)
            .context("unknown ticker")?;
        let reserved = self
            .state
            .pending
            .as_ref()
            .filter(|p| p.ticker == ticker && p.order.intent.side == Side::Sell)
            .map(|p| p.order.intent.quantity)
            .unwrap_or_default();
        s.baseline.exposure(self.inventory(ticker)?.base, reserved)
    }
    pub fn signal(
        &mut self,
        ticker: &str,
        side: Side,
        o: &Observation,
        now: u64,
    ) -> Result<Option<Intent>> {
        let s = self
            .state
            .settings
            .stocks
            .get(ticker)
            .context("unknown ticker")?;
        if self.poisoned || self.state.pending.is_some() || self.epoch != Some(o.epoch) {
            return Ok(None);
        }
        let Some(a) = &self.account else {
            return Ok(None);
        };
        if !super::fresh(now, a.observed_ns, s.policy.max_account_age_ns)
            || o.state_version < self.versions.get(ticker).copied().unwrap_or(0)
        {
            return Ok(None);
        }
        self.versions.insert(ticker.to_owned(), o.state_version);
        let intent=baseline::decide_relative(
            &s.policy,
            &s.baseline,
            &self.inventory(ticker)?,
            side,
            o,
            now,
        )?;
        // A finite base allowance must also cover closing the proposed long.
        // Never open an episode that is already known to be uncloseable.
        if intent.as_ref().is_some_and(|i| i.opening && i.side==Side::Buy
            && a.permissions.get(ticker).is_none_or(|p|p.base_allowance.0<i.quantity.0)) {
            return Ok(None);
        }
        Ok(intent)
    }
    pub fn reserve(
        &mut self,
        ticker: &str,
        side: Side,
        o: &Observation,
        now: u64,
        key: &k256::ecdsa::SigningKey,
        gas: u64,
        max_fee: u128,
        priority_fee: u128,
    ) -> Result<WalletPending> {
        let intent = self
            .signal(ticker, side, o, now)?
            .context("signal blocked")?;
        let s = &self.state.settings.stocks[ticker];
        let c = &s.policy;
        ensure!(c.staging_enabled, "signing disabled");
        ensure!(
            codec::wallet(key) == self.state.settings.wallet,
            "wrong signer"
        );
        ensure!(
            gas > 0
                && gas <= c.max_gas
                && max_fee > 0
                && max_fee <= c.max_fee_per_gas.0
                && priority_fee <= max_fee,
            "invalid gas caps"
        );
        ensure!(
            (gas as u128).checked_mul(max_fee).context("gas overflow")?
                <= self.account.as_ref().unwrap().native.0,
            "insufficient cached native gas balance"
        );
        let permission = self
            .account
            .as_ref()
            .unwrap()
            .permissions
            .get(ticker)
            .context("missing cached permission evidence")?;
        ensure!(
            permission.executor_verified && permission.provider_access_verified,
            "executor/provider access not verified"
        );
        ensure!(
            match intent.side {
                Side::Buy => permission.quote_allowance.0 >= intent.limit_usdg.0,
                Side::Sell => permission.base_allowance.0 >= intent.quantity.0,
            },
            "insufficient cached allowance"
        );
        let tx = metric::transaction(
            c.pool,
            c.router.context("executor unconfigured")?,
            &intent,
            self.state.nonce,
            gas,
            max_fee,
            priority_fee,
        )?;
        let raw = tx.sign(key)?;
        let p = WalletPending {
            ticker: ticker.to_owned(),
            pool: c.pool,
            order: Pending {
                intent,
                nonce: self.state.nonce,
                hash: codec::hash(&raw),
                raw,
            },
        };
        self.state.pending = Some(p.clone());
        self.save()?;
        Ok(p)
    }
    pub fn settle_and_resume(&mut self,e:&ReceiptEvidence,gas_bound:u128)->Result<bool>{
        let cached=self.account.clone();let epoch=self.epoch;
        let pending=self.state.pending.clone().context("no pending order")?;
        self.settle(e)?;
        if let (Some(mut a),Some(epoch))=(cached,epoch) {
            a.nonce=self.state.nonce;a.cash=self.state.cash;a.positions=self.state.positions.clone();
            a.native=Amount(a.native.0.saturating_sub(gas_bound));
            if e.success {
                if let Some(p)=a.permissions.get_mut(&pending.ticker) {
                    match pending.order.intent.side {
                        Side::Buy=>p.quote_allowance=Amount(p.quote_allowance.0.saturating_sub(e.usdg_amount.0)),
                        Side::Sell=>p.base_allowance=Amount(p.base_allowance.0.saturating_sub(pending.order.intent.quantity.0)),
                    }
                }
            }
            // Keep the original proof timestamp. Receipts don't renew cached
            // code/access/allowance evidence indefinitely.
            self.synchronize(epoch,a)?;return Ok(true)
        }
        Ok(false)
    }
    pub fn settle(&mut self, e: &ReceiptEvidence) -> Result<()> {
        ensure!(!self.poisoned, "persistence failed");
        let p = self.state.pending.as_ref().context("no pending order")?;
        ensure!(
            p.order.hash == e.hash
                && e.wallet == self.state.settings.wallet
                && e.pool == p.pool
                && e.nonce == p.order.nonce,
            "receipt identity mismatch"
        );
        ensure!(
            e.block_hash != [0; 32] && e.block_hash == e.canonical_hash && e.confirmations >= 1,
            "noncanonical receipt"
        );
        let inv = self.inventory(&p.ticker)?;
        let i = &p.order.intent;
        let expected = if e.success {
            ensure!(e.matched_swap, "missing swap proof");
            match i.side {
                Side::Buy => {
                    ensure!(
                        e.usdg_amount.0 > 0 && e.usdg_amount.0 <= i.limit_usdg.0,
                        "buy limit violated"
                    );
                    Inventory {
                        base: Amount(
                            inv.base
                                .0
                                .checked_add(i.quantity.0)
                                .context("base overflow")?,
                        ),
                        cash: Amount(
                            inv.cash
                                .0
                                .checked_sub(e.usdg_amount.0)
                                .context("insufficient cash")?,
                        ),
                    }
                }
                Side::Sell => {
                    ensure!(e.usdg_amount.0 >= i.limit_usdg.0, "sell limit violated");
                    Inventory {
                        base: Amount(inv.base.0.checked_sub(i.quantity.0).context("oversold")?),
                        cash: Amount(
                            inv.cash
                                .0
                                .checked_add(e.usdg_amount.0)
                                .context("cash overflow")?,
                        ),
                    }
                }
            }
        } else {
            inv
        };
        ensure!(
            e.balances == expected,
            "partial fill or wallet delta mismatch"
        );
        self.state.positions.insert(p.ticker.clone(), expected.base);
        self.state.cash = expected.cash;
        self.state.nonce = self.state.nonce.checked_add(1).context("nonce overflow")?;
        self.state.pending = None;
        self.disconnect();
        self.save()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn key() -> k256::ecdsa::SigningKey {
        k256::ecdsa::SigningKey::from_slice(&[1; 32]).unwrap()
    }
    fn settings() -> Settings {
        let mut c: Config =
            serde_json::from_str(include_str!("../../config/metric-execution-shadow.json"))
                .unwrap();
        c.wallet = codec::wallet(&key());
        c.staging_enabled = true;
        c.router = Some([9; 20]);
        let mut d = c.clone();
        d.pool = [8; 20];
        Settings {
            wallet: c.wallet,
            stocks: BTreeMap::from([
                (
                    "NVDA".into(),
                    Stock {
                        base_token: [1; 20],
                        policy: c,
                        baseline: Baseline {
                            initial_base: Amount(3_000_000_000_000_000_000),
                            declared_exchange_short: Amount(3_000_000_000_000_000_000),
                        },
                    },
                ),
                (
                    "META".into(),
                    Stock {
                        base_token: [2; 20],
                        policy: d,
                        baseline: Baseline {
                            initial_base: Amount(2_000_000_000_000_000_000),
                            declared_exchange_short: Amount(2_000_000_000_000_000_000),
                        },
                    },
                ),
            ]),
        }
    }
    fn observation(pool: [u8; 20]) -> Observation {
        Observation {
            pool,
            epoch: 1,
            state_version: 1,
            state_valid: true,
            state_received_ns: 1_000_000_000,
            bbo_received_ns: 1_000_000_000,
            provider_valid_until_ns: 2_000_000_000,
            bid_e8: Amount(10_000_000_000),
            ask_e8: Amount(10_000_000_000),
            quantity: Amount(1_000_000_000_000_000_000),
            pool_bid_usdg: Amount(99_700_000),
            pool_ask_usdg: Amount(99_800_000),
        }
    }
    fn account(p: &Portfolio, nonce: u64) -> AccountSnapshot {
        let (cash, positions) = p.balances();
        AccountSnapshot {
            nonce,
            cash,
            positions,
            native: Amount(1_000_000_000_000_000_000),
            permissions: p
                .settings()
                .stocks
                .keys()
                .map(|t| {
                    (
                        t.clone(),
                        Permissions {
                            executor_verified: true,
                            provider_access_verified: true,
                            base_allowance: Amount(u128::MAX),
                            quote_allowance: Amount(u128::MAX),
                        },
                    )
                })
                .collect(),
            observed_ns: 1_000_000_000,
        }
    }
    #[test]
    fn cross_ticker_cash_and_nonce_reserved_once_restart_preserves_baseline() {
        let root = std::env::temp_dir().join(format!("portfolio-test-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&root);
        let s = settings();
        let q = observation(s.stocks["NVDA"].policy.pool);
        let mut p = Portfolio::open(&root, s.clone(), 7, Amount(500_000_000)).unwrap();
        p.synchronize(1, account(&p, 7)).unwrap();
        let pending = p
            .reserve("NVDA", Side::Buy, &q, 1_000_000_000, &key(), 100000, 10, 1)
            .unwrap();
        assert!(
            p.signal(
                "META",
                Side::Buy,
                &observation(s.stocks["META"].policy.pool),
                1_000_000_000
            )
            .unwrap()
            .is_none()
        );
        drop(p);
        let mut p = Portfolio::open(&root, s.clone(), 99, Amount(0)).unwrap();
        assert_eq!(p.pending().unwrap().order.raw, pending.order.raw);
        assert!(p.synchronize(1, account(&p, 7)).is_err());
        let e = ReceiptEvidence {
            hash: pending.order.hash,
            wallet: s.wallet,
            pool: q.pool,
            nonce: 7,
            block_hash: [1; 32],
            canonical_hash: [1; 32],
            confirmations: 1,
            success: true,
            matched_swap: true,
            usdg_amount: Amount(99_800_000),
            balances: Inventory {
                base: Amount(4_000_000_000_000_000_000),
                cash: Amount(400_200_000),
            },
        };
        p.settle(&e).unwrap();
        assert_eq!(
            p.exposure("NVDA").unwrap().relative_quantity,
            Amount(1_000_000_000_000_000_000)
        );
        assert_eq!(p.inventory("META").unwrap().cash, Amount(400_200_000));
        p.synchronize(2, account(&p, 8)).unwrap();
        let mut changed = s;
        changed
            .stocks
            .get_mut("NVDA")
            .unwrap()
            .baseline
            .initial_base = Amount(4_000_000_000_000_000_000);
        drop(p);
        assert!(Portfolio::open(&root, changed, 8, Amount(400_200_000)).is_err());
        std::fs::remove_dir_all(root).unwrap();
    }
    #[test]
    fn receipt_resumes_without_rpc_but_keeps_proof_age_and_debits_allowance() {
        let root=std::env::temp_dir().join(format!("fast-settle-{}",std::process::id()));let _=std::fs::remove_dir_all(&root);
        let s=settings();let q=observation(s.stocks["NVDA"].policy.pool);
        let mut p=Portfolio::open(&root,s.clone(),7,Amount(500_000_000)).unwrap();
        let mut a=account(&p,7);a.permissions.get_mut("NVDA").unwrap().quote_allowance=Amount(200_000_000);let native=a.native.0;
        p.synchronize(1,a).unwrap();let pending=p.reserve("NVDA",Side::Buy,&q,1_000_000_000,&key(),100000,10,1).unwrap();
        let e=ReceiptEvidence{hash:pending.order.hash,wallet:s.wallet,pool:q.pool,nonce:7,block_hash:[1;32],canonical_hash:[1;32],confirmations:1,success:true,matched_swap:true,usdg_amount:Amount(99_800_000),balances:Inventory{base:Amount(4_000_000_000_000_000_000),cash:Amount(400_200_000)}};
        assert!(p.settle_and_resume(&e,1_000_000).unwrap());let a=p.account.as_ref().unwrap();assert_eq!(a.observed_ns,1_000_000_000);assert_eq!(a.nonce,8);assert_eq!(a.native.0,native-1_000_000);assert_eq!(a.permissions["NVDA"].quote_allowance.0,100_200_000);assert_eq!(p.epoch,Some(1));assert!(p.pending().is_none());
        drop(p);std::fs::remove_dir_all(root).unwrap();
    }
    #[test]
    fn missing_permissions_or_allowance_never_reserve() {
        let root = std::env::temp_dir().join(format!("permission-test-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&root);
        let settings = settings();
        let o = observation(settings.stocks["NVDA"].policy.pool);
        let mut p = Portfolio::open(&root, settings, 7, Amount(500_000_000)).unwrap();
        let mut a = account(&p, 7);
        a.permissions.clear();
        p.synchronize(1, a).unwrap();
        assert!(
            p.reserve("NVDA", Side::Buy, &o, 1_000_000_000, &key(), 100000, 10, 1)
                .is_err()
        );
        assert!(p.pending().is_none());
        let mut a = account(&p, 7);
        a.permissions.get_mut("NVDA").unwrap().quote_allowance = Amount(1);
        p.synchronize(1, a).unwrap();
        assert!(
            p.reserve("NVDA", Side::Buy, &o, 1_000_000_000, &key(), 100000, 10, 1)
                .is_err()
        );
        assert!(p.pending().is_none());
        let mut a=account(&p,7);
        a.permissions.get_mut("NVDA").unwrap().base_allowance=Amount(1);
        p.synchronize(1,a).unwrap();
        assert!(p.signal("NVDA",Side::Buy,&o,1_000_000_000).unwrap().is_none());
        assert!(p.pending().is_none());
        drop(p);
        std::fs::remove_dir_all(root).unwrap();
    }
    #[test]
    fn short_closes_only_to_baseline_and_no_selling_nonexistent_stock() {
        let s = settings();
        let st = &s.stocks["NVDA"];
        let mut q = observation(st.policy.pool);
        q.pool_bid_usdg = Amount(100_200_000);
        q.pool_ask_usdg = Amount(100_300_000);
        let inv = Inventory {
            base: Amount(3_000_000_000_000_000_000),
            cash: Amount(500_000_000),
        };
        assert!(
            baseline::decide_relative(
                &st.policy,
                &st.baseline,
                &inv,
                Side::Sell,
                &q,
                1_000_000_000
            )
            .unwrap()
            .is_some()
        );
        let short = Inventory {
            base: Amount(2_000_000_000_000_000_000),
            cash: Amount(600_000_000),
        };
        assert!(
            baseline::decide_relative(
                &st.policy,
                &st.baseline,
                &short,
                Side::Sell,
                &q,
                1_000_000_000
            )
            .unwrap()
            .is_none()
        );
        q.pool_ask_usdg = Amount(100_050_000);
        q.pool_bid_usdg = Amount(100_000_000);
        assert!(
            baseline::decide_relative(
                &st.policy,
                &st.baseline,
                &short,
                Side::Buy,
                &q,
                1_000_000_000
            )
            .unwrap()
            .is_some()
        );
        q.quantity = Amount(2_000_000_000_000_000_000);
        assert!(
            baseline::decide_relative(
                &st.policy,
                &st.baseline,
                &short,
                Side::Buy,
                &q,
                1_000_000_000
            )
            .unwrap()
            .is_none()
        );
        let z = Inventory {
            base: Amount(0),
            cash: Amount(500_000_000),
        };
        assert!(
            baseline::decide_relative(&st.policy, &st.baseline, &z, Side::Sell, &q, 1_000_000_000)
                .unwrap()
                .is_none()
        );
    }
}
