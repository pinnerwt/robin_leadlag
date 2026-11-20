//! Convert same-host relay receipt stamps into the recorder monotonic domain.
use anyhow::{Context, Result, ensure};
use serde_json::{Value, json};
use std::{
    collections::HashMap,
    io::{self, BufRead},
};
fn main() -> Result<()> {
    let path = std::env::args().nth(1).context("events JSONL")?;
    let mut events: Vec<Value> = std::fs::read_to_string(path)?
        .lines()
        .map(serde_json::from_str)
        .collect::<Result<_, _>>()?;
    let mut times = HashMap::new();
    let mut delays = vec![];
    for l in io::stdin().lock().lines() {
        let r: Value = serde_json::from_str(&l?)?;
        if r["kind"] != "nitro_push" {
            continue;
        }
        let Some(relay) = r["relay_recv_ns"].as_u64() else {
            continue;
        };
        let captured = r["recv_ns"].as_u64().context("capture wall")?;
        ensure!(captured >= relay, "same-host clock inversion");
        let delay = captured - relay;
        let mono = r["mono_ns"]
            .as_u64()
            .context("capture mono")?
            .checked_sub(delay)
            .context("negative mono")?;
        delays.push(delay);
        for msg in r["payload"]["messages"].as_array().into_iter().flatten() {
            let h = msg["blockHash"].as_str().context("hash")?;
            let e = times.entry(h.to_owned()).or_insert(mono);
            *e = (*e).min(mono);
        }
    }
    let mut changed = 0;
    for r in &mut events {
        if r["kind"] == "session" {
            continue;
        }
        let h = if r["kind"] == "pool_transaction" {
            r["logs"][0]["blockHash"].as_str()
        } else {
            r["block_hash"].as_str()
        }
        .context("event hash")?;
        let mono = times.get(h).context("missing relay arrival")?;
        r["recorder_mono_ns"] = r["mono_ns"].clone();
        r["mono_ns"] = json!(mono);
        r["ingress_clock"] = json!("same-host relay receipt mapped to capture monotonic");
        changed += 1;
    }
    delays.sort();
    let q = |p: f64| delays[((delays.len() - 1) as f64 * p) as usize] as f64 / 1e6;
    eprintln!(
        "{}",
        json!({"events_adjusted":changed,"relay_samples":delays.len(),"relay_to_recorder_ms":{"p50":q(0.5),"p90":q(0.9),"p99":q(0.99),"max":q(1.0)}})
    );
    for r in events {
        println!("{r}");
    }
    Ok(())
}
