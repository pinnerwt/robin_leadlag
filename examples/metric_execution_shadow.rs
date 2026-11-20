//! Offline shadow adapter: JSON observation in, unsigned intent out. No key or network.
use anyhow::{Context, Result, ensure};
use robin_leadlag::execution::{Config, Inventory, Observation, decide};
use serde::Deserialize;
use std::io::{self, BufRead};
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Request {
    now_ns: u64,
    episode_open: bool,
    inventory: Inventory,
    observation: Observation,
}
fn main() -> Result<()> {
    let path = std::env::args()
        .nth(1)
        .context("usage: metric_execution_shadow CONFIG < observations.jsonl")?;
    let c: Config = serde_json::from_slice(&std::fs::read(path)?)?;
    c.validate()?;
    ensure!(!c.staging_enabled, "shadow configuration required");
    for l in io::stdin().lock().lines() {
        let r: Request = serde_json::from_str(&l?)?;
        let result = decide(&c, &r.inventory, r.episode_open, &r.observation, r.now_ns);
        println!(
            "{}",
            match result {
                Ok(intent) => serde_json::json!({"mode":"shadow","intent":intent}),
                Err(e) => serde_json::json!({"mode":"shadow","error":e.to_string()}),
            }
        );
    }
    Ok(())
}
