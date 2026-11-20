//! Verify decoded retryable hashes against transaction identities in recorded push logs.
#[path = "../src/journal.rs"]
mod journal;
#[path = "../src/nitro.rs"]
mod nitro;
use anyhow::{Result, ensure};
use serde_json::{Value, json};
use std::{
    collections::{HashMap, HashSet},
    io::Read,
};
fn main() -> Result<()> {
    let mut input = std::io::BufReader::new(std::io::stdin().lock());
    let mut magic = [0; 8];
    input.read_exact(&mut magic)?;
    ensure!(&magic == journal::MAGIC, "magic");
    let mut submissions = HashMap::new();
    let mut seen = HashSet::new();
    let mut logs = HashMap::<String, HashSet<String>>::new();
    let mut errors = vec![];
    let mut fixture = None;
    loop {
        let mut h = [0; 4];
        if input.read(&mut h[..1])? == 0 {
            break;
        }
        input.read_exact(&mut h[1..])?;
        let n = u32::from_le_bytes(h) as usize;
        journal::valid_size(n)?;
        let mut b = vec![0; n];
        input.read_exact(&mut b)?;
        let r = journal::parse(&b)?;
        if r["kind"] == "chain_log" {
            let l = &r["payload"];
            if let (Some(tx), Some(a)) = (l["transactionHash"].as_str(), l["address"].as_str()) {
                logs.entry(tx.into()).or_default().insert(a.to_lowercase());
            }
        }
        if r["kind"] != "nitro_push" {
            continue;
        }
        let Some(items) = r["payload"]["messages"].as_array() else { continue };
        if !items
            .iter()
            .any(|i| i["message"]["message"]["header"]["kind"] == 9)
        {
            continue;
        }
        let mut only = r.clone();
        only["payload"]["messages"] = Value::Array(
            items
                .iter()
                .filter(|i| i["message"]["message"]["header"]["kind"] == 9)
                .cloned()
                .collect(),
        );
        if fixture.is_none() {
            fixture = Some(only.clone());
        }
        match nitro::transactions_without_sender(&only) {
            Ok(ts) => {
                for t in ts {
                    let hash = t["tx"].as_str().unwrap().to_owned();
                    if seen.insert(hash.clone()) {
                        submissions.insert(hash, t);
                    }
                }
            }
            Err(e) => errors.push(json!({"error":e.to_string(),"mono_ns":r["mono_ns"]})),
        }
    }
    let mut out = vec![];
    for (hash, t) in submissions {
        out.push(json!({"transaction":t,"matched_recorded_logs":logs.contains_key(&hash),"log_addresses":logs.get(&hash)}));
    }
    out.sort_by_key(|r| r["transaction"]["sequence"].as_u64().unwrap_or(0));
    if let Some(f) = fixture {
        std::fs::write(
            "tests/fixtures/nitro_submit_retryable.json",
            serde_json::to_vec(&f)?,
        )?;
    }
    println!("{}", json!({"retryables":out,"errors":errors}));
    Ok(())
}
