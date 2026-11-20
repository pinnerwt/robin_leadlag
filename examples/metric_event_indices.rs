//! Attach observed transaction order for retrospective execution truth only.
#[path = "../src/journal.rs"]
mod journal;
use anyhow::{Context, Result, ensure};
use serde_json::{Value, json};
use std::{
    collections::{HashMap, HashSet},
    fs,
    io::{self, Read},
};
fn main() -> Result<()> {
    let dir = std::env::args().nth(1).context("dir")?;
    let manifest: Vec<Value> = serde_json::from_slice(&fs::read(format!("{dir}/manifest.json"))?)?;
    let mut tapes = vec![];
    let mut wanted = HashSet::new();
    for m in &manifest {
        let path = format!("{dir}/{}-events.jsonl", m["symbol"].as_str().unwrap());
        let rows: Vec<Value> = fs::read_to_string(&path)?
            .lines()
            .map(serde_json::from_str)
            .collect::<Result<_, _>>()?;
        for r in &rows {
            if let Some(tx) = r["tx"].as_str() {
                wanted.insert(tx.to_owned());
            }
        }
        tapes.push((path, rows));
    }
    let mut indices = HashMap::new();
    let mut input = io::BufReader::new(io::stdin().lock());
    let mut magic = [0; 8];
    input.read_exact(&mut magic)?;
    ensure!(&magic == journal::MAGIC, "magic");
    loop {
        let mut len = [0; 4];
        if input.read(&mut len[..1])? == 0 {
            break;
        }
        input.read_exact(&mut len[1..])?;
        let n = u32::from_le_bytes(len) as usize;
        journal::valid_size(n)?;
        let mut raw = vec![0; n];
        input.read_exact(&mut raw)?;
        if raw.first().is_some_and(|t| *t == 9 || *t == 10) {
            continue;
        }
        let r = journal::parse(&raw)?;
        if r["kind"] != "chain_log" {
            continue;
        }
        let l = &r["payload"];
        if let Some(tx) = l["transactionHash"].as_str() {
            if wanted.contains(tx) {
                indices.insert(tx.to_owned(), l["transactionIndex"].clone());
            }
        }
    }
    for (path, mut rows) in tapes {
        let mut missing = 0;
        for r in &mut rows {
            if let Some(tx) = r["tx"].as_str() {
                if let Some(i) = indices.get(tx) {
                    r["transaction_index"] = i.clone();
                } else if r["kind"] == "pool_transaction" || r.get("accepted_log_ns").is_some() {
                    missing += 1;
                }
            }
        }
        ensure!(missing == 0, "missing accepted execution indices: {path}");
        fs::write(
            path,
            rows.iter()
                .map(|r| r.to_string() + "\n")
                .collect::<String>(),
        )?;
    }
    eprintln!("{}", json!({"transaction_indices":indices.len()}));
    Ok(())
}
