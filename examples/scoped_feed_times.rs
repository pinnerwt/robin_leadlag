//! Retrospectively attribute direct SPCX compressed updates; preserve original arrival time.
#[path = "../src/nitro.rs"]
mod nitro;
use anyhow::{Context, Result};
use serde_json::{Value, json};
use std::{
    collections::{HashMap, HashSet},
    io::{self, BufRead},
};
fn main() -> Result<()> {
    let mut txs = HashMap::new();
    let mut accepted = HashMap::new();
    let mut seen = HashSet::new();
    let book: Vec<u64> =
        serde_json::from_str(include_str!("../scripts/metric_spread_codebook.json"))?;
    for l in io::stdin().lock().lines() {
        let r: Value = serde_json::from_str(&l?)?;
        if r["kind"] == "chain_log" {
            let l = &r["payload"];
            if l["address"].as_str().is_some_and(|a| {
                a.eq_ignore_ascii_case("0xe844701934d9c6085b292e428f41b911cc0b3872")
            }) && l["topics"][0]
                == "0x29e088dffd7bf6815d088137a59f364d6747163baa7ff4bc47f316a1ad1b9586"
                && l["topics"][1]
                    == "0x8dfdc825dd0453e7c80b1c1d32ae910e35d6efe9000000000000000012375400"
                && l["removed"] != true
            {
                accepted
                    .entry(l["transactionHash"].as_str().context("hash")?.to_owned())
                    .or_insert(r["mono_ns"].clone());
            }
        }
        if r["kind"] != "nitro_push" {
            continue;
        }
        let Ok(ts) = nitro::transactions(&r) else {
            continue;
        };
        for t in ts {
            if !t["to"].as_str().is_some_and(|a| {
                a.eq_ignore_ascii_case("0xe844701934d9c6085b292e428f41b911cc0b3872")
            }) {
                continue;
            }
            let hash = t["tx"].as_str().context("hash")?.to_owned();
            if !seen.insert(hash.clone()) {
                continue;
            }
            let d = hex::decode(t["data"].as_str().context("data")?.trim_start_matches("0x"))?;
            if d.first() != Some(&0) || (d.len() - 1) % 32 != 0 {
                continue;
            }
            let Some(w) = d[1..]
                .chunks_exact(32)
                .filter(|w| w[31] == 0x54)
                .max_by_key(|w| &w[24..31])
            else {
                continue;
            };
            if w[4..6] == [255, 255] {
                continue;
            }
            let raw = u32::from_be_bytes(w[..4].try_into()?);
            let price = ((raw & ((1 << 27) - 1)) as f64) * 2f64.powi((raw >> 27) as i32) / 1e8;
            txs.insert(hash,json!({"kind":"provider_source","mono_ns":t["mono_ns"],"block_hash":t["block_hash"],"bid":price*(1.0-book[w[4]as usize]as f64/1e6),"ask":price*(1.0+book[w[5]as usize]as f64/1e6),"mid":price}));
        }
    }
    let mut rows = vec![];
    for (hash, log_ns) in accepted {
        if let Some(mut r) = txs.remove(&hash) {
            r["tx"] = json!(hash);
            r["log_mono_ns"] = log_ns;
            rows.push(r);
        }
    }
    rows.sort_by_key(|r| r["mono_ns"].as_u64().unwrap_or(0));
    for r in rows {
        println!("{r}");
    }
    Ok(())
}
