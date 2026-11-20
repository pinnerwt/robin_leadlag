//! Offline multi-pool binary tape extraction. No network or acceptance-based signals.
#[path = "../src/journal.rs"]
mod journal;
#[path = "../src/nitro.rs"]
mod nitro;
use anyhow::{Context, Result, ensure};
use serde_json::{Value, json};
use std::{
    collections::{HashMap, HashSet},
    fs::File,
    io::{self, BufWriter, Read, Write},
};
fn main() -> Result<()> {
    let dir = std::env::args()
        .nth(1)
        .context("output directory with manifest.json")?;
    let cutoff = std::env::args()
        .nth(2)
        .map(|x| x.parse::<u64>())
        .transpose()?
        .unwrap_or(u64::MAX);
    let manifest: Vec<Value> =
        serde_json::from_reader(File::open(format!("{dir}/manifest.json"))?)?;
    let pools: HashMap<String, usize> = manifest
        .iter()
        .enumerate()
        .map(|(i, p)| (p["pool"].as_str().unwrap().to_owned(), i))
        .collect();
    let feeds: HashMap<String, usize> = manifest
        .iter()
        .enumerate()
        .map(|(i, p)| (p["feed_topic"].as_str().unwrap().to_owned(), i))
        .collect();
    let ids: HashMap<u8, usize> = manifest
        .iter()
        .enumerate()
        .map(|(i, p)| (p["word_id"].as_u64().unwrap() as u8, i))
        .collect();
    let symbols: HashMap<String, usize> = manifest
        .iter()
        .enumerate()
        .map(|(i, p)| (p["symbol"].as_str().unwrap().to_owned(), i))
        .collect();
    let mut bbo: Vec<_> = manifest
        .iter()
        .map(|p| {
            File::create(format!("{dir}/{}-bbo.jsonl", p["symbol"].as_str().unwrap()))
                .map(BufWriter::new)
        })
        .collect::<Result<_, _>>()?;
    let mut logs: HashMap<(usize, String), Vec<Value>> = HashMap::new();
    let mut accepted = HashMap::new();
    let mut indices = HashMap::new();
    let mut heads = HashMap::new();
    let mut metadata = HashMap::new();
    let mut rows = vec![vec![]; manifest.len()];
    let mut seen = HashSet::new();
    let mut session = Value::Null;
    let mut counts = vec![0u64; manifest.len()];
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
        let mut r = journal::parse(&raw)?;
        if r["mono_ns"].as_u64().is_some_and(|t| t > cutoff) {
            break;
        }
        match r["kind"].as_str().unwrap_or("") {
            "session" => session = r.clone(),
            "bbo" => {
                if let Some(&i) = r["symbol"].as_str().and_then(|s| symbols.get(s)) {
                    serde_json::to_writer(&mut bbo[i], &r)?;
                    writeln!(bbo[i])?;
                    counts[i] += 1;
                }
            }
            "head" => {
                heads.insert(
                    r["payload"]["hash"]
                        .as_str()
                        .context("head hash")?
                        .to_owned(),
                    r["payload"]["number"].clone(),
                );
            }
            "chain_log" => {
                let l = &r["payload"];
                ensure!(l["removed"] != true, "removed log requires reorg replay");
                let address = l["address"].as_str().context("address")?.to_lowercase();
                let tx = l["transactionHash"].as_str().context("tx")?.to_owned();
                indices.insert(tx.clone(), l["transactionIndex"].clone());
                if let Some(&i) = pools.get(&address) {
                    let mut l = l.clone();
                    l["arrival_ns"] = r["mono_ns"].clone();
                    logs.entry((i, tx.clone())).or_default().push(l);
                }
                if address == "0xe844701934d9c6085b292e428f41b911cc0b3872"
                    && l["topics"][0]
                        == "0x29e088dffd7bf6815d088137a59f364d6747163baa7ff4bc47f316a1ad1b9586"
                {
                    if let Some(&i) = l["topics"][1].as_str().and_then(|t| feeds.get(t)) {
                        accepted.entry((i, tx)).or_insert(r["mono_ns"].clone());
                    }
                }
            }
            "nitro_push" => {
                if let Some(relay) = r["relay_recv_ns"].as_u64() {
                    let delay = r["recv_ns"]
                        .as_u64()
                        .context("recv")?
                        .checked_sub(relay)
                        .context("relay clock inversion")?;
                    r["mono_ns"] = json!(
                        r["mono_ns"]
                            .as_u64()
                            .context("mono")?
                            .checked_sub(delay)
                            .context("mono underflow")?
                    );
                }
                let Ok(txs) = nitro::transactions_without_sender(&r) else {
                    continue;
                };
                for t in txs {
                    let Some(hash) = t["tx"].as_str().map(str::to_owned) else {
                        continue;
                    };
                    if !seen.insert(hash.clone()) {
                        continue;
                    }
                    let h = json!({"timestamp":format!("0x{:x}",t["timestamp"].as_u64().unwrap_or(0)),"l1BlockNumber":format!("0x{:x}",t["l1_block"].as_u64().unwrap_or(0))});
                    metadata.insert(
                        hash.clone(),
                        json!({"mono_ns":t["mono_ns"],"header":h,"block_hash":t["block_hash"]}),
                    );
                    if !t["to"].as_str().is_some_and(|a| {
                        a.eq_ignore_ascii_case("0xe844701934d9c6085b292e428f41b911cc0b3872")
                    }) {
                        continue;
                    }
                    let d =
                        hex::decode(t["data"].as_str().context("data")?.trim_start_matches("0x"))?;
                    if d.first() != Some(&0) || (d.len() - 1) % 32 != 0 {
                        continue;
                    }
                    let mut words: HashMap<usize, &[u8]> = HashMap::new();
                    for w in d[1..].chunks_exact(32) {
                        if let Some(&i) = ids.get(&w[31]) {
                            let old = words.entry(i).or_insert(w);
                            if w[24..31] > old[24..31] {
                                *old = w;
                            }
                        }
                    }
                    for (i, w) in words {
                        rows[i].push(json!({"kind":"oracle_candidate","word":format!("0x{}",hex::encode(w)),"tx":hash,"from":t["from"],"sender_recovered":false,"header":h,"mono_ns":t["mono_ns"],"block_hash":t["block_hash"]}));
                    }
                }
            }
            _ => {}
        }
    }
    for ((i, hash), mut ls) in logs {
        ls.sort_by_key(|l| {
            u64::from_str_radix(l["logIndex"].as_str().unwrap().trim_start_matches("0x"), 16)
                .unwrap()
        });
        ls.dedup_by(|a, b| a["logIndex"] == b["logIndex"]);
        let m = metadata
            .get(&hash)
            .context("pool tx missing Nitro metadata")?;
        let arrival = ls
            .iter()
            .map(|l| l["arrival_ns"].as_u64().unwrap())
            .max()
            .unwrap();
        rows[i].push(json!({"kind":"pool_transaction","tx":hash,"mono_ns":m["mono_ns"],"log_mono_ns":arrival,"header":m["header"],"block_number":ls[0]["blockNumber"],"logs":ls}));
    }
    for (i, rs) in rows.iter_mut().enumerate() {
        for r in rs.iter_mut() {
            if let Some(index) = r["tx"].as_str().and_then(|tx| indices.get(tx)) {
                r["transaction_index"] = index.clone();
            }
            if r["kind"] == "oracle_candidate" {
                r["block_number"] = heads
                    .get(r["block_hash"].as_str().unwrap())
                    .cloned()
                    .unwrap_or(Value::Null);
                if let Some(ns) = accepted.get(&(i, r["tx"].as_str().unwrap().to_owned())) {
                    r["accepted_log_ns"] = ns.clone();
                }
            }
        }
        rs.push(session.clone());
        rs.sort_by_key(|r| r["mono_ns"].as_u64().unwrap_or(0));
        let mut out = BufWriter::new(File::create(format!(
            "{dir}/{}-events.jsonl",
            manifest[i]["symbol"].as_str().unwrap()
        ))?);
        for r in rs.iter() {
            serde_json::to_writer(&mut out, r)?;
            writeln!(out)?;
        }
        eprintln!(
            "{} events={} bbo={}",
            manifest[i]["symbol"],
            rs.len(),
            counts[i]
        );
    }
    Ok(())
}
