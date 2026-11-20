//! Shared baseline policy for live shadow and replay. No signer or network.
use anyhow::{Context, Result, ensure};
use robin_leadlag::execution::{Amount, Config, Inventory, Observation, Side, baseline};
use serde::Deserialize;
use std::{
    collections::BTreeMap,
    io::{self, BufRead},
};
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Catalog {
    stocks: BTreeMap<String, Entry>,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Entry {
    base_token: String,
    quote_token: String,
    policy: Config,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Request {
    ticker: String,
    now_ns: u64,
    inventory: Inventory,
    observation: Observation,
}
fn main() -> Result<()> {
    let args: Vec<_> = std::env::args().collect();
    let c: Catalog = serde_json::from_slice(&std::fs::read(
        args.get(1)
            .context("usage: metric_inventory_shadow CATALOG ENV [--audit] < observations.jsonl")?,
    )?)?;
    for s in c.stocks.values() {
        s.policy.validate()?;
        ensure!(!s.policy.staging_enabled, "shadow only");
        ensure!(
            s.base_token.len() == 42 && s.quote_token.len() == 42,
            "token address"
        );
    }
    let decimals = c
        .stocks
        .iter()
        .map(|(t, s)| (t.clone(), s.policy.base_decimals))
        .collect();
    let b = baseline::load(
        &std::fs::read_to_string(args.get(2).context("inventory env path")?)?,
        &decimals,
    )?;
    if args.iter().any(|a| a == "--audit") {
        for (t, s) in &c.stocks {
            println!(
                "{}",
                serde_json::json!({"ticker":t,"decimals":s.policy.base_decimals,"baseline":b[t],"exposure_at_baseline":b[t].exposure(b[t].initial_base,Amount(0))?,"additional_long_cap_usdg_raw":s.policy.max_position_usdg,"note":"declared inventory and hedge; not verified wallet or exchange balances"})
            );
        }
        return Ok(());
    }
    for line in io::stdin().lock().lines() {
        let r: Request = serde_json::from_str(&line?)?;
        let s = c.stocks.get(&r.ticker).context("unknown ticker")?;
        let b = &b[&r.ticker];
        println!(
            "{}",
            serde_json::json!({"mode":"shadow","ticker":r.ticker,"exposure":b.exposure(r.inventory.base,Amount(0))?,"maximum_quote_quantities":baseline::quantities(&s.policy,b,&r.inventory,r.observation.ask_e8)?,"buy":baseline::decide_relative(&s.policy,b,&r.inventory,Side::Buy,&r.observation,r.now_ns)?,"sell":baseline::decide_relative(&s.policy,b,&r.inventory,Side::Sell,&r.observation,r.now_ns)?})
        );
    }
    Ok(())
}
