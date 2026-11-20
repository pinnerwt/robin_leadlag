//! Offline multi-pool binary tape extraction. No network or acceptance-based signals.
#[path = "../src/journal.rs"]
mod journal;
#[path = "../src/nitro.rs"]
mod nitro;
use anyhow::{Context, Result, ensure};
use alloy_consensus::TxEnvelope;
use alloy_eips::eip2718::Decodable2718;
use serde_json::{Value, json};
use std::{
    collections::{HashMap, HashSet},
    fs::File,
    io::{self, BufWriter, Read, Write},
};
fn retain_canonical_logs(logs: &mut Vec<Value>, hashes: &HashSet<String>, heights: &HashSet<String>) -> Result<()> {
    for l in logs.iter() {
        let hash=l["blockHash"].as_str().context("log hash")?;
        let height=l["blockNumber"].as_str().context("log height")?;
        ensure!(hashes.contains(hash)||heights.contains(height), "unresolved pool log branch");
    }
    logs.retain(|l| hashes.contains(l["blockHash"].as_str().unwrap()));
    ensure!(logs.iter().all(|l|l["removed"]!=true), "canonical removed log requires reorg replay");
    Ok(())
}
fn feed_bindings(manifest: &[Value]) -> Result<(HashMap<String, Vec<usize>>, HashMap<u8, Vec<usize>>)> {
    let mut feeds: HashMap<String, Vec<usize>> = HashMap::new();
    let mut ids: HashMap<u8, Vec<usize>> = HashMap::new();
    for (i, p) in manifest.iter().enumerate() {
        if let Some(feed) = p["feed_topic"].as_str() { feeds.entry(feed.to_owned()).or_default().push(i); }
        if let Some(id) = p["word_id"].as_u64() { ids.entry(u8::try_from(id)?).or_default().push(i); }
    }
    Ok((feeds, ids))
}
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
    let (feeds, ids) = feed_bindings(&manifest)?;
    let symbols: HashMap<String, usize> = manifest
        .iter()
        .enumerate()
        .map(|(i, p)| (p["symbol"].as_str().unwrap().to_owned(), i))
        .collect();
    let checkpoint: Value = serde_json::from_reader(File::open(format!("{dir}/checkpoint.json"))?)?;
    let anchor = u64::from_str_radix(
        checkpoint["anchor"]["number"]
            .as_str()
            .unwrap()
            .trim_start_matches("0x"),
        16,
    )?;
    let mut failures = Vec::<Value>::new();
    let mut bbo: Vec<_> = manifest
        .iter()
        .map(|p| {
            File::create(format!("{dir}/{}-bbo.jsonl", p["symbol"].as_str().unwrap()))
                .map(BufWriter::new)
        })
        .collect::<Result<_, _>>()?;
    let mut price_logs = Vec::<(usize, Value)>::new();
    let mut logs: HashMap<(usize, String), Vec<Value>> = HashMap::new();
    let mut accepted = HashMap::new();
    let mut aux_receipts: HashMap<String, Vec<Value>> = HashMap::new();
    let mut indices = HashMap::new();
    let mut heads = HashMap::new();
    let mut canonical_hashes = HashSet::new();
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
                if u64::from_str_radix(
                    l["blockNumber"]
                        .as_str()
                        .context("block")?
                        .trim_start_matches("0x"),
                    16,
                )? <= anchor
                {
                    continue;
                }

                let address = l["address"].as_str().context("address")?.to_lowercase();
                let tx = l["transactionHash"].as_str().context("tx")?.to_owned();
                indices.insert((tx.clone(), l["blockHash"].as_str().context("log hash")?.to_owned()), l["transactionIndex"].clone());
                if address == "0x30a88bf894d1b806125a23ebf23d715496fd7102"
                    && l["topics"][0]
                        == "0x29e088dffd7bf6815d088137a59f364d6747163baa7ff4bc47f316a1ad1b9586"
                {
                    aux_receipts
                        .entry(tx.clone())
                        .or_default()
                        .push(json!({"feed":l["topics"][1],"mono_ns":r["mono_ns"],"block_hash":l["blockHash"],"removed":l["removed"]}));
                }
                for (i,p) in manifest.iter().enumerate() {
                    if p["v3_price_pools"].as_array().is_some_and(|xs|xs.iter().any(|x|x.as_str()==Some(address.as_str()))) && l["topics"][0].as_str().is_some_and(|t|["0xc42079f94a6350d7e6235f29174924f928cc2ac818eb64fed8004e115fbcca67","0x7a53080ba414158be7ec69b987b5fb7d07dee101fe85488f0853ae16239d0bde","0x0c396cd989a39f4459b5fa1aed6a9a8dcdbc45908acfd67e028cd568da98982c","0xac49e518f90a358f652e4400164f05a5d8f7e35e7747279bc3a93dbf584e125a"].contains(&t)) {
                        let mut l=l.clone(); l["arrival_ns"]=r["mono_ns"].clone();price_logs.push((i,l));
                    }
                }
                if let Some(&i) = pools.get(&address) {
                    let mut l = l.clone();
                    l["arrival_ns"] = r["mono_ns"].clone();
                    logs.entry((i, tx.clone())).or_default().push(l);
                }
                if address == "0xe844701934d9c6085b292e428f41b911cc0b3872"
                    && l["topics"][0]
                        == "0x29e088dffd7bf6815d088137a59f364d6747163baa7ff4bc47f316a1ad1b9586"
                {
                    if let Some(pool_ids) = l["topics"][1].as_str().and_then(|t| feeds.get(t)) {
                        for &i in pool_ids {
                            if l["removed"] != true { accepted.entry((i, tx.clone(), l["blockHash"].as_str().context("log hash")?.to_owned())).or_insert(r["mono_ns"].clone()); }
                        }
                    }
                }
            }
            "nitro_push" => {
                if let Some(messages) = r["payload"]["messages"].as_array() {
                    for m in messages { if let Some(h) = m["blockHash"].as_str() { canonical_hashes.insert(h.to_owned()); } }
                }
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
                let txs = match nitro::transactions_without_sender(&r) {
                    Ok(t) => t,
                    Err(e) => {
                        failures.push(json!({"kind":"decode_failure","mono_ns":r["mono_ns"],"error":e.to_string()}));
                        continue;
                    }
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
                    if t["to"].as_str().is_some_and(|a| {
                        a.eq_ignore_ascii_case("0x30a88bf894d1b806125a23ebf23d715496fd7102")
                    }) {
                        for rs in &mut rows {
                            rs.push(json!({"kind":"aux_oracle","transaction":{"to":t["to"],"data":t["data"]},"tx":hash,"header":h,"mono_ns":t["mono_ns"],"block_hash":t["block_hash"]}));
                        }
                    }
                    if !t["to"].as_str().is_some_and(|a| {
                        a.eq_ignore_ascii_case("0xe844701934d9c6085b292e428f41b911cc0b3872")
                    }) {
                        continue;
                    }
                    // Word IDs are scoped to a writer namespace, never global.
                    // Recover only relevant oracle transactions; replay learns delegated
                    // writers causally from their matching pushed FeedUpdated logs.
                    let raw = hex::decode(t["raw_transaction"].as_str().context("signed oracle transaction")?.trim_start_matches("0x"))?;
                    let signed = TxEnvelope::decode_2718(&mut raw.as_slice())?;
                    let sender = signed.recover_signer()?.to_string();
                    let d =
                        hex::decode(t["data"].as_str().context("data")?.trim_start_matches("0x"))?;
                    if d.first() != Some(&0) || (d.len() - 1) % 32 != 0 {
                        continue;
                    }
                    let mut words: HashMap<usize, &[u8]> = HashMap::new();
                    for w in d[1..].chunks_exact(32) {
                        if let Some(pool_ids) = ids.get(&w[31]) {
                            for &i in pool_ids {
                                let old = words.entry(i).or_insert(w);
                                if w[24..31] > old[24..31] { *old = w; }
                            }
                        }
                    }
                    for (i, w) in words {
                        rows[i].push(json!({"kind":"oracle_candidate","word":format!("0x{}",hex::encode(w)),"tx":hash,"from":sender,"sender_recovered":true,"header":h,"mono_ns":t["mono_ns"],"block_hash":t["block_hash"]}));
                    }
                }
            }
            _ => {}
        }
    }
    for receipts in aux_receipts.values_mut() {
        receipts.retain(|r| r["block_hash"].as_str().is_some_and(|h| canonical_hashes.contains(h)) && r["removed"] != true);
    }
    let canonical_heights: HashSet<String> = canonical_hashes.iter().filter_map(|h| heads.get(h).and_then(Value::as_str).map(str::to_owned)).collect();
    let mut price_seen=HashSet::new();
    for (i,l) in price_logs {
        let mut ls=vec![l]; retain_canonical_logs(&mut ls,&canonical_hashes,&canonical_heights)?;
        let Some(l)=ls.pop() else {continue};
        let tx=l["transactionHash"].as_str().context("price tx")?;
        if !price_seen.insert((i,l["blockHash"].to_string(),l["logIndex"].to_string())) {continue;}
        let m=metadata.get(tx).context("missing V3 price transaction")?;
        ensure!(l["blockHash"]==m["block_hash"],"V3 price branch mismatch");
        // The scoped pool reducer consumes a whole Metric transaction. Refuse
        // interleaved downstream/upstream swaps rather than apply a future price.
        if let Some(pool_logs)=logs.get(&(i,tx.to_owned())) {
            let n=u64::from_str_radix(l["logIndex"].as_str().unwrap().trim_start_matches("0x"),16)?;
            let positions=pool_logs.iter().map(|p|u64::from_str_radix(p["logIndex"].as_str().unwrap().trim_start_matches("0x"),16)).collect::<Result<Vec<_>,_>>()?;
            ensure!(positions.iter().all(|j|*j>n)||positions.iter().all(|j|*j<n), "interleaved V3/Metric transaction requires ordered replay");
        }
        rows[i].push(json!({"kind":"v3_price","tx":tx,"mono_ns":m["mono_ns"],"log_mono_ns":l["arrival_ns"],"header":m["header"],"block_number":l["blockNumber"],"block_hash":m["block_hash"],"log":l}));
    }
    for ((i, hash), mut ls) in logs {
        retain_canonical_logs(&mut ls, &canonical_hashes, &canonical_heights)?;
        if ls.is_empty() { continue; }
        if let Some(m) = metadata.get(&hash) { ls.retain(|l| l["blockHash"] == m["block_hash"]); }
        if ls.is_empty() { continue; }
        ls.sort_by_key(|l| {
            u64::from_str_radix(l["logIndex"].as_str().unwrap().trim_start_matches("0x"), 16)
                .unwrap()
        });
        ls.dedup_by(|a, b| a["logIndex"] == b["logIndex"]);
        let Some(m) = metadata.get(&hash) else {
            failures.push(json!({"kind":"missing_pool_tx","symbol":manifest[i]["symbol"],"mono_ns":ls[0]["arrival_ns"],"tx":hash}));
            continue;
        };
        let arrival = ls
            .iter()
            .map(|l| l["arrival_ns"].as_u64().unwrap())
            .max()
            .unwrap();
        rows[i].push(json!({"kind":"pool_transaction","tx":hash,"mono_ns":m["mono_ns"],"log_mono_ns":arrival,"header":m["header"],"block_number":ls[0]["blockNumber"],"block_hash":m["block_hash"],"logs":ls}));
    }
    serde_json::to_writer_pretty(
        File::create(format!("{dir}/extraction-audit.json"))?,
        &failures,
    )?;
    serde_json::to_writer_pretty(
        File::create(format!("{dir}/auxiliary-receipts.json"))?,
        &aux_receipts,
    )?;
    for (i, rs) in rows.iter_mut().enumerate() {
        for r in rs.iter_mut() {
            if let Some(index) = r["tx"].as_str().and_then(|tx| indices.get(&(tx.to_owned(), r["block_hash"].as_str().unwrap_or("").to_owned()))) {
                r["transaction_index"] = index.clone();
            }
            if r["kind"] == "aux_oracle" {
                r["block_number"] = heads
                    .get(r["block_hash"].as_str().unwrap())
                    .cloned()
                    .unwrap_or(Value::Null);
            }
            if r["kind"] == "oracle_candidate" {
                r["block_number"] = heads
                    .get(r["block_hash"].as_str().unwrap())
                    .cloned()
                    .unwrap_or(Value::Null);
                if let Some(ns) = accepted.get(&(i, r["tx"].as_str().unwrap().to_owned(), r["block_hash"].as_str().unwrap().to_owned())) {
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

#[cfg(test)]
mod branch_tests {
 use super::*;
 #[test]
 fn shared_feed_fans_out_to_every_pool_without_inventing_missing_bindings() {
  let manifest=vec![json!({"feed_topic":"feed","word_id":42}),json!({"feed_topic":"feed","word_id":42}),json!({})];
  let (feeds, ids)=feed_bindings(&manifest).unwrap();
  assert_eq!(feeds["feed"],vec![0,1]);assert_eq!(ids[&42],vec![0,1]);
  assert!(feed_bindings(&[json!({"word_id":256})]).is_err());
 }
 #[test]
 fn excludes_proven_sibling_but_rejects_unknown_or_removed_canonical() {
  let hashes=HashSet::from(["canonical".to_owned()]);let heights=HashSet::from(["0xa".to_owned()]);
  let mut logs=vec![json!({"blockHash":"sibling","blockNumber":"0xa"}),json!({"blockHash":"canonical","blockNumber":"0xa"})];
  retain_canonical_logs(&mut logs,&hashes,&heights).unwrap();assert_eq!(logs.len(),1);assert_eq!(logs[0]["blockHash"],"canonical");
  assert!(retain_canonical_logs(&mut vec![json!({"blockHash":"unknown","blockNumber":"0xb"})],&hashes,&heights).is_err());
  logs[0]["removed"]=json!(true);assert!(retain_canonical_logs(&mut logs,&hashes,&heights).is_err());
 }
}
