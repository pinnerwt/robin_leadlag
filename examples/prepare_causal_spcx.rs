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
    let mut pool_logs: HashMap<String, Vec<Value>> = HashMap::new();
    let mut metadata = HashMap::new();
    let mut heads = HashMap::new();
    let mut clock = Value::Null;
    let mut txs = HashMap::new();
    let mut accepted = HashMap::new();
    let mut seen = HashSet::new();
    let book: Vec<u64> =
        serde_json::from_str(include_str!("../scripts/metric_spread_codebook.json"))?;
    for l in io::stdin().lock().lines() {
        let r: Value = serde_json::from_str(&l?)?;
        if r["kind"] == "session" {
            clock = r.clone();
        }
        if r["kind"] == "head" {
            heads.insert(
                r["payload"]["hash"].as_str().unwrap().to_owned(),
                r["payload"]["number"].clone(),
            );
        }
        if r["kind"] == "chain_log" {
            let l = &r["payload"];
            if l["address"].as_str().is_some_and(|a| {
                a.eq_ignore_ascii_case("0xa94e5130a57c48b0b2f266709634a45be7ae8171")
            }) {
                let mut log = l.clone();
                log["arrival_ns"] = r["mono_ns"].clone();
                pool_logs
                    .entry(l["transactionHash"].as_str().unwrap().to_owned())
                    .or_default()
                    .push(log);
            }
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
            if let Some(hash) = t["tx"].as_str() {
                metadata.entry(hash.to_owned()).or_insert_with(||json!({"mono_ns":t["mono_ns"],"header":{"timestamp":format!("0x{:x}",t["timestamp"].as_u64().unwrap_or(0)),"l1BlockNumber":format!("0x{:x}",t["l1_block"].as_u64().unwrap_or(0))},"block_hash":t["block_hash"]}));
            }
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
            // Preserve stalled updates: the quote model will reject them.
            let raw = u32::from_be_bytes(w[..4].try_into()?);
            let price = ((raw & ((1 << 27) - 1)) as f64) * 2f64.powi((raw >> 27) as i32) / 1e8;
            txs.insert(hash,json!({"kind":"oracle_candidate","word":format!("0x{}",hex::encode(w)),"from":t["from"],"header":{"timestamp":format!("0x{:x}",t["timestamp"].as_u64().unwrap()),"l1BlockNumber":format!("0x{:x}",t["l1_block"].as_u64().unwrap())},"mono_ns":t["mono_ns"],"block_hash":t["block_hash"],"bid":price*(1.0-book[w[4]as usize]as f64/1e6),"ask":price*(1.0+book[w[5]as usize]as f64/1e6),"mid":price}));
        }
    }
    let mut rows = vec![clock];
    for (hash, mut r) in txs {
        r["tx"] = json!(hash);
        r["block_number"] = heads
            .get(r["block_hash"].as_str().unwrap())
            .cloned()
            .unwrap_or(Value::Null);
        if let Some(log_ns) = accepted.get(&hash) {
            r["accepted_log_ns"] = log_ns.clone();
        }
        rows.push(r);
    }
    for (hash, mut logs) in pool_logs {
        logs.sort_by_key(|l| {
            u64::from_str_radix(l["logIndex"].as_str().unwrap().trim_start_matches("0x"), 16)
                .unwrap()
        });
        logs.dedup_by(|a, b| a["logIndex"] == b["logIndex"]);
        let m = metadata
            .get(&hash)
            .context("tracked pool transaction missing Nitro metadata")?;
        let arrival = logs
            .iter()
            .map(|l| l["arrival_ns"].as_u64().unwrap())
            .max()
            .unwrap();
        rows.push(json!({"kind":"pool_transaction","tx":hash,"mono_ns":m["mono_ns"],"log_mono_ns":arrival,"header":m["header"],"block_number":logs[0]["blockNumber"],"logs":logs}));
    }
    rows.sort_by_key(|r| r["mono_ns"].as_u64().unwrap_or(0));
    for r in rows {
        println!("{r}");
    }
    Ok(())
}
