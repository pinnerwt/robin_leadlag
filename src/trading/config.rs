use anyhow::{Context, Result, ensure};
use robin_leadlag::execution::{
    Amount, Config as Policy, Side, baseline, codec,
    portfolio::{Settings, Stock},
};
use serde::{Deserialize, Serialize};
use std::{collections::BTreeMap, os::unix::fs::PermissionsExt, path::Path};
pub const POOL: &str = "0xb89fd35ebc48b791339520af812b70f71d823cc5";
pub const BASE: &str = "0x0bd7d308f8e1639fab988df18a8011f41eacad73";
pub const QUOTE: &str = "0x5fc5360d0400a0fd4f2af552add042d716f1d168";
pub fn address(s: &str) -> Result<[u8; 20]> {
    hex::decode(s.strip_prefix("0x").context("address prefix")?)?
        .try_into()
        .map_err(|_| anyhow::anyhow!("address length"))
}
#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Config {
    #[serde(default)]
    pub circuit: robin_leadlag::execution::circuit::Limits,
    #[serde(skip)]
    pub source_path: Option<std::path::PathBuf>,
    pub mode: Mode,
    pub credentials_file: String,
    pub executor: Option<String>,
    pub executor_codehash: Option<String>,
    pub input_socket: String,
    pub state_directory: String,
    pub status_file: String,
    pub audit_file: String,
    pub chain_ws_url: String,
    pub binance_ws_url: String,
    pub binance_connections: usize,
    pub rotate_seconds: u64,
    pub submit_urls: Vec<String>,
    pub additional_long_usdg: String,
    pub initial_cash_usdg: String,
    pub open_bps: i32,
    pub close_bps: i32,
    pub slippage_bps: u32,
    pub execution_budget_ms: u64,
    pub max_bbo_age_ms: u64,
    pub max_state_age_ms: u64,
    pub max_account_age_ms: u64,
    pub max_head_age_ms: u64,
    pub gas_limit: u64,
    pub max_fee_per_gas: String,
    pub priority_fee_per_gas: String,
    pub order_ttl_ms: u64,
}
#[derive(Clone, Copy, Deserialize, Serialize, PartialEq, Debug)]
#[serde(rename_all = "snake_case")]
pub enum Mode {
    Standby,
    Live,
}
impl Config {
    pub fn load(p: &Path) -> Result<Self> {
        let mut c: Self = serde_json::from_slice(&std::fs::read(p)?)?;
        c.validate()?;
        c.source_path=Some(p.to_path_buf());
        Ok(c)
    }
    pub fn reload_mode(&self) -> Result<Mode> {
        let Some(path)=&self.source_path else {return Ok(self.mode)};
        let new=Self::load(path)?;
        let mut old_value=serde_json::to_value(self)?;
        let mut new_value=serde_json::to_value(&new)?;
        old_value.as_object_mut().unwrap().remove("mode");
        new_value.as_object_mut().unwrap().remove("mode");
        ensure!(old_value==new_value,"non-mode config changes require restart");
        Ok(new.mode)
    }
    pub fn validate(&self) -> Result<()> {
        ensure!((1..=3600).contains(&self.circuit.window_seconds) && self.circuit.max_orders>0 && self.circuit.max_orders<=100 && self.circuit.max_reverts>0 && self.circuit.max_reverts<=10,"invalid circuit limits");
        ensure!(
            (1..=4).contains(&self.binance_connections) && self.rotate_seconds >= 60,
            "invalid connection settings"
        );
        ensure!(
            baseline::parse_quantity(&self.additional_long_usdg, 6)?.0 == 100_000_000,
            "B89 pilot additional cap must be 100 USDG"
        );
        ensure!(
            baseline::parse_quantity(&self.initial_cash_usdg, 6)?.0 == 100_000_000,
            "B89 pilot cash budget must be 100 USDG"
        );
        ensure!(
            self.open_bps >= 0 && self.close_bps > -10000 && self.slippage_bps < 10000,
            "invalid threshold"
        );
        ensure!(
            self.execution_budget_ms > 0
                && self.execution_budget_ms < self.order_ttl_ms
                && self.order_ttl_ms <= 5000,
            "invalid deadline"
        );
        ensure!(
            [
                self.max_head_age_ms,
                self.max_account_age_ms,
                self.max_state_age_ms,
                self.max_bbo_age_ms
            ]
            .iter()
            .all(|v| *v > 0 && *v <= 60000),
            "invalid freshness"
        );
        ensure!(
            !self.submit_urls.is_empty() && self.submit_urls.len() <= 8,
            "submit endpoints"
        );
        ensure!(
            self.gas_limit > 0 && self.gas_limit <= 1_000_000,
            "gas limit"
        );
        let max: u128 = self.max_fee_per_gas.parse()?;
        let tip: u128 = self.priority_fee_per_gas.parse()?;
        ensure!(max > 0 && tip <= max, "fees");
        for p in [
            &self.input_socket,
            &self.state_directory,
            &self.status_file,
            &self.audit_file,
        ] {
            ensure!(!p.is_empty(), "empty path");
        }
        if let Some(a) = &self.executor {
            ensure!(address(a)? != [0; 20], "zero executor");
        }
        Ok(())
    }
    pub fn credentials(&self) -> Result<Credentials> {
        let meta = std::fs::metadata(&self.credentials_file)?;
        ensure!(
            meta.permissions().mode() & 0o077 == 0,
            "credentials must be mode 0600"
        );
        let text = std::fs::read_to_string(&self.credentials_file)?;
        let bases = baseline::load(&text, &BTreeMap::from([("ETH".into(), 18)]))?;
        let base = bases["ETH"].clone();
        ensure!(
            base.initial_base.0 > 0 && base.initial_base == base.declared_exchange_short,
            "baseline and declared hedge must match and be positive"
        );
        let mut private = None;
        for l in text.lines() {
            if let Some((k, v)) = l.trim().split_once('=') {
                if k.trim() == "TRADING_PRIVATE_KEY" {
                    ensure!(private.is_none(), "duplicate private key setting");
                    private = Some(v.trim().trim_matches('"').trim_matches('\''));
                }
            }
        }
        let private = private.context("missing private key setting")?;
        let key = if private.is_empty() {
            None
        } else {
            let raw = hex::decode(private.trim_start_matches("0x"))
                .map_err(|_| anyhow::anyhow!("invalid private key encoding"))?;
            Some(
                k256::ecdsa::SigningKey::from_slice(&raw)
                    .map_err(|_| anyhow::anyhow!("invalid private key"))?,
            )
        };
        Ok(Credentials {
            key,
            baseline: base,
        })
    }
    pub fn settings(&self, credentials: &Credentials) -> Result<Settings> {
        let key = credentials
            .key
            .as_ref()
            .context("private key not configured")?;
        let executor = address(
            self.executor
                .as_deref()
                .context("executor not configured")?,
        )?;
        let hash = hex::decode(
            self.executor_codehash
                .as_deref()
                .context("executor codehash not configured")?
                .trim_start_matches("0x"),
        )?;
        ensure!(hash.len() == 32, "executor codehash length");
        let wallet = codec::wallet(key);
        let policy = Policy {
            staging_enabled: true,
            router: Some(executor),
            router_selector: Some(robin_leadlag::execution::metric::selector()),
            max_gas: self.gas_limit,
            max_fee_per_gas: Amount(self.max_fee_per_gas.parse()?),
            chain_id: 4663,
            wallet,
            pool: address(POOL)?,
            base_decimals: 18,
            max_position_usdg: baseline::parse_quantity(&self.additional_long_usdg, 6)?,
            open_bps: self.open_bps,
            close_bps: self.close_bps,
            entry_side: Side::Buy,
            slippage_bps: self.slippage_bps,
            execution_budget_ns: self.execution_budget_ms * 1_000_000,
            max_bbo_age_ns: self.max_bbo_age_ms * 1_000_000,
            max_state_age_ns: self.max_state_age_ms * 1_000_000,
            max_account_age_ns: self.max_account_age_ms * 1_000_000,
            gas_cost_usdg: Amount(0),
        };
        let s = Settings {
            wallet,
            stocks: BTreeMap::from([(
                "ETH".into(),
                Stock {
                    base_token: address(BASE)?,
                    policy,
                    baseline: credentials.baseline.clone(),
                },
            )]),
        };
        s.validate()?;
        Ok(s)
    }
}
pub struct Credentials {
    pub key: Option<k256::ecdsa::SigningKey>,
    pub baseline: baseline::Baseline,
}

#[cfg(test)]
mod reload_tests {
 use super::*;
 #[test]
 fn only_mode_can_be_reloaded() {
  let p=std::env::temp_dir().join(format!("metric-mode-{}.json",std::process::id()));
  std::fs::write(&p,include_str!("../../config/metric-trader-b89.json")).unwrap();
  let c=Config::load(&p).unwrap();let mut new=c.clone();new.mode=Mode::Live;
  std::fs::write(&p,serde_json::to_vec(&new).unwrap()).unwrap();
  assert_eq!(c.reload_mode().unwrap(),Mode::Live);
  new.open_bps+=1;
  std::fs::write(&p,serde_json::to_vec(&new).unwrap()).unwrap();
  assert!(c.reload_mode().is_err());std::fs::remove_file(p).unwrap();
 }
}
