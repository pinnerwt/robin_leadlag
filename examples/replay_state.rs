//! Offline pinned-checkpoint + pushed-log/calldata experiment. No networking.
#[path = "../src/local_evm.rs"]
mod local_evm;
#[path = "../src/nitro.rs"]
mod nitro;
#[path = "../src/pool.rs"]
mod pool;
#[path = "../src/pool_reduce.rs"]
mod pool_reduce;
use anyhow::{Context, Result, ensure};
use revm::primitives::{Address, ExecutionResult, U256};
use serde_json::{Value, json};
use std::{
    collections::{BTreeMap, HashMap, HashSet},
    io::{self, BufRead},
    str::FromStr,
};
const FEED: &str = "0x29e088dffd7bf6815d088137a59f364d6747163baa7ff4bc47f316a1ad1b9586";
const SWAP: &str = "0x9734819749a91fc3be03ea83205f924ee08479bd3f0da48efc91d94d050cac1e";
const BIN: &str = "0xcad09799f755048f0fd388c6b2fcc8e0cebefd15756c6903522cc2a95f661f70";
fn hexnum(v: &Value) -> Result<u64> {
    Ok(u64::from_str_radix(
        v.as_str().context("hex quantity")?.trim_start_matches("0x"),
        16,
    )?)
}
fn address(v: &Value) -> Result<Address> {
    Ok(Address::from_str(v.as_str().context("address")?)?)
}
fn bytes(v: &Value) -> Result<Vec<u8>> {
    Ok(hex::decode(
        v.as_str().context("hex bytes")?.trim_start_matches("0x"),
    )?)
}
fn abi(n: i128) -> [u8; 32] {
    let mut w = [if n < 0 { 255 } else { 0 }; 32];
    w[16..].copy_from_slice(&n.to_be_bytes());
    w
}
fn quote(db: &mut local_evm::State, h: &Value, p: &Value) -> Result<Vec<u8>> {
    let result = db.run(h, &json!({"to":p["pool"],"data":"0xec069057"}), true)?;
    ensure!(
        result.is_success(),
        "provider reverted: {:?}",
        local_evm::output(&result)
    );
    let out = db.last_quote.clone().context("provider subcall output")?;
    ensure!(out.len() == 96, "provider output size");
    Ok(out)
}
fn simulate(
    pool: &str,
    sell: bool,
    amount: i128,
    prices: &[u8],
    sender: &str,
    recipient: &str,
) -> Result<Value> {
    let mut data = hex::decode("658b6cb7")?;
    for a in [sender, recipient] {
        let mut word = [0; 32];
        word[12..].copy_from_slice(Address::from_str(a)?.as_slice());
        data.extend(word);
    }
    data.extend(abi(i128::from(sell)));
    data.extend(abi(amount));
    data.extend(
        if sell {
            U256::from(1)
        } else {
            U256::from(u128::MAX)
        }
        .to_be_bytes::<32>(),
    );
    data.extend(prices);
    data.extend(abi(288));
    data.extend(abi(0));
    Ok(json!({"to":pool,"data":format!("0x{}",hex::encode(data))}))
}
fn emitted(result: &ExecutionResult, topic: Option<&str>) -> Vec<Value> {
    result.logs().iter().filter(|l|topic.is_none_or(|t|l.data.topics().first().is_some_and(|x|x.to_string()==t))).map(|l|json!({"address":l.address.to_string().to_lowercase(),"topics":l.data.topics().iter().map(|x|x.to_string()).collect::<Vec<_>>(),"data":format!("0x{}",hex::encode(&l.data.data))})).collect()
}
fn normalized(log: &Value) -> Value {
    json!({"address":log["address"].as_str().unwrap().to_lowercase(),"topics":log["topics"],"data":log["data"]})
}
fn expected_delta(log: &Value) -> Result<[i128; 2]> {
    let d = bytes(&log["data"])?;
    ensure!(d.len() == 96, "swap log size");
    Ok([
        i128::from_be_bytes(d[32..48].try_into()?),
        i128::from_be_bytes(d[48..64].try_into()?),
    ])
}
fn sim_delta(r: &ExecutionResult) -> Result<[i128; 2]> {
    let d = r.output().context("simulation output")?;
    ensure!(
        d.len() == 68 && d[..4] == [0x1f, 0x60, 0x53, 0xde],
        "simulation rejected: {:?}",
        local_evm::output(r)
    );
    Ok([
        i128::from_be_bytes(d[20..36].try_into()?),
        i128::from_be_bytes(d[52..68].try_into()?),
    ])
}
fn replay_swap(
    db: &mut local_evm::State,
    h: &Value,
    p: &Value,
    log: &Value,
    logs: &[Value],
) -> Result<()> {
    let prices = quote(db, h, p)?;
    let delta = expected_delta(log)?;
    let sell = delta[0] > 0;
    let details = U256::from_be_slice(&bytes(&log["data"])?[..32]);
    let exact = details.bit(120);
    let amount = if exact {
        if sell { delta[0] } else { delta[1] }
    } else {
        if sell { delta[1] } else { delta[0] }
    };
    let sender = format!("0x{}", &log["topics"][1].as_str().context("sender")?[26..]);
    let recipient = format!(
        "0x{}",
        &log["topics"][2].as_str().context("recipient")?[26..]
    );
    let request = simulate(
        p["pool"].as_str().unwrap(),
        sell,
        amount,
        &prices,
        &sender,
        &recipient,
    )?;
    let result = db.run_mode(h, &request, true, true)?;
    ensure!(
        result.is_success(),
        "simulation did not commit: {:?}",
        local_evm::output(&result)
    );
    ensure!(
        sim_delta(&result)? == delta,
        "swap token delta mismatch: simulated {:?}, observed {:?}",
        sim_delta(&result)?,
        delta
    );
    let expected: Vec<_> = logs
        .iter()
        .filter(|l| {
            l["topics"][0] == BIN && address(&l["address"]).ok() == address(&p["pool"]).ok()
        })
        .map(normalized)
        .collect();
    ensure!(
        emitted(&result, Some(BIN)) == expected,
        "BinSwapped logs differ"
    );
    let slot = db
        .slots
        .get(&(address(&p["pool"])?, U256::ZERO))
        .context("slot0")?;
    let mask104 = (U256::from(1) << 104) - U256::from(1);
    let reconstructed = ((*slot >> 24) & mask104) | (((*slot >> 8) & U256::from(65535)) << 104);
    let mask = (U256::from(1) << 120) - U256::from(1);
    ensure!(
        reconstructed == details & mask,
        "final bin/position mismatch: simulated {reconstructed:#x}, observed {:#x}",
        details & mask
    );
    Ok(())
}
fn size_raw(s: &str, decimals: u64) -> Result<i128> {
    let pieces: Vec<_> = s.split('.').collect();
    ensure!(pieces.len() <= 2, "size format");
    let frac = pieces.get(1).copied().unwrap_or("");
    ensure!(frac.len() <= decimals as usize, "size precision");
    ensure!(
        !pieces[0].is_empty()
            && pieces[0].bytes().all(|c| c.is_ascii_digit())
            && frac.bytes().all(|c| c.is_ascii_digit()),
        "unsigned decimal size required"
    );
    let scale = 10i128
        .checked_pow(decimals.try_into()?)
        .context("decimal scale overflow")?;
    let whole = pieces[0]
        .parse::<i128>()?
        .checked_mul(scale)
        .context("size overflow")?;
    let fraction = if frac.is_empty() {
        0
    } else {
        frac.parse::<i128>()?
            .checked_mul(
                10i128
                    .checked_pow((decimals - frac.len() as u64).try_into()?)
                    .context("decimal scale overflow")?,
            )
            .context("size overflow")?
    };
    let n = whole.checked_add(fraction).context("size overflow")?;
    ensure!(n > 0, "size must be positive");
    Ok(n)
}
fn quotes(
    db: &local_evm::State,
    h: &Value,
    p: &Value,
    sizes: &[String],
    available: u64,
    block: u64,
) -> Vec<Value> {
    let mut rows = Vec::new();
    if p["curator"] != "Carcosa" {
        return sizes.iter().map(|size|json!({"kind":"state_quote","symbol":p["binance_symbol"],"pool":p["pool"],"size_tokens":size,"available_mono_ns":available,"block":block,"state_complete":false,"executable":false,"reason":"provider dependency coverage not validated"})).collect();
    }
    for size in sizes {
        let start = std::time::Instant::now();
        let mut temp = db.clone();
        let result = (|| -> Result<(f64, f64)> {
            let prices = quote(&mut temp, h, p)?;
            let slot = temp
                .slots
                .get(&(address(&p["pool"])?, U256::ZERO))
                .context("pool slot0")?;
            ensure!((*slot & U256::from(255)) == U256::ZERO, "pool paused");
            let raw = size_raw(size, p["decimals"][0].as_u64().context("decimals")?)?;
            let mut outcomes = Vec::new();
            for sell in [true, false] {
                let request = simulate(
                    p["pool"].as_str().unwrap(),
                    sell,
                    if sell { raw } else { -raw },
                    &prices,
                    "0x0000000000000000000000000000000000000000",
                    "0x0000000000000000000000000000000000000000",
                )?;
                let result = temp.run(h, &request, false)?;
                let deltas = sim_delta(&result)?;
                ensure!(deltas[0] == if sell { raw } else { -raw }, "partial fill");
                outcomes.push(
                    deltas[1].unsigned_abs() as f64
                        / (10f64.powi(p["decimals"][1].as_u64().unwrap() as i32))
                        / size.parse::<f64>()?,
                );
            }
            Ok((outcomes[0], outcomes[1]))
        })();
        rows.push(match result{Ok((bid,ask))=>json!({"kind":"state_quote","symbol":p["binance_symbol"],"pool":p["pool"],"size_tokens":size,"bid":bid,"ask":ask,"available_mono_ns":available,"block":block,"state_complete":true,"executable":true,"validation":"observed_inputs_only","compute_us":start.elapsed().as_micros() as u64}),Err(e)=>json!({"kind":"state_quote","symbol":p["binance_symbol"],"pool":p["pool"],"size_tokens":size,"available_mono_ns":available,"block":block,"state_complete":false,"executable":false,"reason":e.to_string()})});
    }
    rows
}
fn is_oracle(tx: &Value) -> bool {
    matches!(
        tx["to"]
            .as_str()
            .unwrap_or("")
            .to_ascii_lowercase()
            .as_str(),
        "0xe844701934d9c6085b292e428f41b911cc0b3872" | "0x30a88bf894d1b806125a23ebf23d715496fd7102"
    )
}
fn main() -> Result<()> {
    let args: Vec<_> = std::env::args().collect();
    let seed: Value = serde_json::from_slice(&std::fs::read(args.get(1).context("checkpoint")?)?)?;
    let sizes = args
        .get(2)
        .map(String::as_str)
        .unwrap_or("0.02,0.1")
        .split(',')
        .map(str::to_owned)
        .collect::<Vec<_>>();
    let mut db = local_evm::State::load(&seed["accounts"])?;
    let anchor = hexnum(&seed["anchor"]["number"])?;
    let mut heads = BTreeMap::<u64, Value>::new();
    let mut logs = HashMap::<String, Vec<Value>>::new();
    let mut txs = HashMap::<String, Value>::new();
    let mut tx_order = HashMap::<String, Vec<String>>::new();
    let mut bbo = Vec::new();
    let mut gaps = Vec::new();
    let mut feed_headers = HashMap::<String, Value>::new();
    let mut seen_logs = HashMap::<(String, String), Value>::new();
    let mut tape_end_ns = 0u64;
    // A frozen live prefix can end between a head and its log notifications.
    // This settling margin is not a cryptographic completeness guarantee.
    let settle_ns = args
        .get(3)
        .map(|s| s.parse::<u64>())
        .transpose()?
        .unwrap_or(2000)
        * 1_000_000;
    for line in io::stdin().lock().lines() {
        let row: Value = serde_json::from_str(&line?)?;
        tape_end_ns = tape_end_ns.max(row["mono_ns"].as_u64().unwrap_or(0));
        match row["kind"].as_str() {
            Some("head") => {
                heads.insert(hexnum(&row["payload"]["number"])?, row);
            }
            Some("chain_log") => {
                let mut l = row["payload"].clone();
                ensure!(
                    l["removed"] != true,
                    "removed log: replay requires a new canonical checkpoint"
                );
                let key = (
                    l["blockHash"].as_str().context("blockHash")?.to_owned(),
                    l["logIndex"].as_str().context("logIndex")?.to_owned(),
                );
                if let Some(old) = seen_logs.get(&key) {
                    ensure!(old == &l, "conflicting duplicate log");
                    continue;
                }
                seen_logs.insert(key, l.clone());
                l["available_ns"] = row["mono_ns"].clone();
                logs.entry(l["blockHash"].as_str().context("blockHash")?.to_owned())
                    .or_default()
                    .push(l);
            }
            Some("nitro_push") => {
                for item in row["payload"]["messages"].as_array().into_iter().flatten() {
                    if let Some(hash) = item["blockHash"].as_str() {
                        feed_headers.insert(
                            hash.to_owned(),
                            item["message"]["message"]["header"].clone(),
                        );
                    }
                }
                for tx in nitro::transactions(&row)? {
                    let hash = tx["tx"].as_str().context("tx hash")?.to_owned();
                    if !txs.contains_key(&hash) {
                        tx_order
                            .entry(
                                tx["block_hash"]
                                    .as_str()
                                    .context("feed block hash")?
                                    .to_owned(),
                            )
                            .or_default()
                            .push(hash.clone());
                        txs.insert(hash, tx);
                    }
                }
            }
            Some("gap") => gaps.push(row),
            Some("bbo") => bbo.push(row),
            _ => {}
        }
    }
    ensure!(
        heads
            .get(&anchor)
            .is_some_and(|h| h["payload"]["hash"] == seed["anchor"]["hash"]),
        "tape does not contain checkpoint anchor"
    );
    let pools = seed["pools"].as_array().context("pools")?;
    let mut invalid = HashMap::<Address, String>::new();
    let mut previous = seed["anchor"].clone();
    let mut updates = 0;
    let mut oracle_no_events = 0;
    let mut swaps = 0;
    let mut failed_swaps = 0;
    let mut failed_updates = 0;
    let mut verified_pools = HashMap::<String, u64>::new();
    let mut lp_events = 0;
    let mut state_ready = 0u64;
    let start_ns = heads[&anchor]["mono_ns"].as_u64().unwrap();
    state_ready = state_ready.max(start_ns);
    let mut output = Vec::new();
    for (&block, row) in heads.range((anchor + 1)..) {
        if row["mono_ns"].as_u64().unwrap_or(u64::MAX) > tape_end_ns.saturating_sub(settle_ns) {
            break;
        }
        let mut header = row["payload"].clone();
        let feed_header = feed_headers
            .get(header["hash"].as_str().context("head hash")?)
            .context("missing pushed block context")?;
        header["l1BlockNumber"] = json!(format!(
            "0x{:x}",
            feed_header["blockNumber"]
                .as_u64()
                .context("feed L1 height")?
        ));
        let h = &header;
        ensure!(
            hexnum(&previous["number"])? + 1 == block && h["parentHash"] == previous["hash"],
            "head gap/reorg at {block}"
        );
        previous = h.clone();
        let now = row["mono_ns"].as_u64().unwrap();
        if gaps.iter().any(|g| {
            g["mono_ns"]
                .as_u64()
                .is_some_and(|t| start_ns < t && t <= now)
                && g["stream"] != "binance"
        }) {
            for p in pools {
                invalid.insert(address(&p["pool"])?, "transport gap".into());
            }
        }
        let mut block_logs = logs.remove(h["hash"].as_str().unwrap()).unwrap_or_default();
        block_logs.sort_by_key(|l| {
            (
                hexnum(&l["transactionIndex"]).unwrap_or(0),
                hexnum(&l["logIndex"]).unwrap_or(0),
            )
        });
        let mut groups = BTreeMap::<u64, Vec<Value>>::new();
        for l in block_logs {
            groups
                .entry(hexnum(&l["transactionIndex"])?)
                .or_default()
                .push(l);
        }
        let mut by_hash: HashMap<String, (u64, Vec<Value>)> = groups
            .into_iter()
            .map(|(i, ls)| {
                (
                    ls[0]["transactionHash"].as_str().unwrap().to_owned(),
                    (i, ls),
                )
            })
            .collect();
        let mut ordered = Vec::new();
        let mut last_index = None;
        for hash in tx_order
            .get(h["hash"].as_str().unwrap())
            .into_iter()
            .flatten()
        {
            if let Some((index, ls)) = by_hash.remove(hash) {
                ensure!(
                    last_index.is_none_or(|old| index > old),
                    "feed/executed tx order mismatch"
                );
                last_index = Some(index);
                ordered.push(ls);
            } else if is_oracle(&txs[hash]) {
                ordered.push(vec![json!({"transactionHash":hash,"available_ns":txs[hash]["mono_ns"],"topics":[],"address":"0x0000000000000000000000000000000000000000"})]);
            }
        }
        for (_, ls) in by_hash.values() {
            if ls.iter().any(|l| {
                l["topics"][0] == FEED
                    || pools
                        .iter()
                        .any(|p| address(&p["pool"]).ok() == address(&l["address"]).ok())
            }) {
                for p in pools {
                    invalid.insert(
                        address(&p["pool"])?,
                        "tracked transaction missing from pushed calldata".into(),
                    );
                }
            }
        }
        for ls in ordered {
            let hash = ls[0]["transactionHash"].as_str().unwrap();
            let available = ls
                .iter()
                .filter_map(|l| l["available_ns"].as_u64())
                .max()
                .unwrap_or(now)
                .max(
                    txs.get(hash)
                        .and_then(|t| t["mono_ns"].as_u64())
                        .unwrap_or(0),
                );
            let available = available.max(now).max(state_ready);
            state_ready = available;
            let feed_logs: Vec<_> = ls.iter().filter(|l| l["topics"][0] == FEED).collect();
            let oracle_transaction = txs.get(hash).is_some_and(is_oracle);
            if !feed_logs.is_empty() || oracle_transaction {
                let mut candidate = db.clone();
                let result = (|| -> Result<()> {
                    let tx = txs.get(hash).context("accepted update missing calldata")?;
                    let result = candidate.run(h, tx, true)?;
                    ensure!(
                        feed_logs.is_empty() || result.is_success(),
                        "accepted update reverted locally"
                    );
                    let expected = feed_logs.iter().map(|l| normalized(l)).collect::<Vec<_>>();
                    ensure!(
                        emitted(&result, Some(FEED)) == expected,
                        "feed update logs mismatch"
                    );
                    Ok(())
                })();
                match result {
                    Ok(()) => {
                        db = candidate;
                        if feed_logs.is_empty() {
                            oracle_no_events += 1;
                        } else {
                            updates += 1;
                        }
                    }
                    Err(e) => {
                        failed_updates += 1;
                        for p in pools {
                            invalid.insert(address(&p["pool"])?, format!("oracle update: {e}"));
                        }
                        output.push(json!({"kind":"update_failure","tx":hash,"reason":e.to_string(),"available_mono_ns":available}));
                    }
                }
            }
            let mut affected = HashSet::new();
            for p in pools {
                let a = address(&p["pool"])?;
                let own: Vec<_> = ls
                    .iter()
                    .filter(|l| address(&l["address"]).ok() == Some(a))
                    .collect();
                if own.is_empty() {
                    continue;
                }
                affected.insert(a);
                let swaplogs: Vec<_> = own.iter().filter(|l| l["topics"][0] == SWAP).collect();
                if swaplogs.len() == 1 && !invalid.contains_key(&a) {
                    let mut candidate = db.clone();
                    match replay_swap(&mut candidate, h, p, swaplogs[0], &ls) {
                        Ok(()) => {
                            db = candidate;
                            swaps += 1;
                            *verified_pools
                                .entry(p["pool"].as_str().unwrap().to_owned())
                                .or_default() += 1;
                        }
                        Err(e) => {
                            failed_swaps += 1;
                            invalid.insert(a, format!("swap parity: {e}"));
                            output.push(json!({"kind":"swap_failure","pool":p["pool"],"tx":hash,"reason":e.to_string(),"available_mono_ns":available}));
                        }
                    }
                } else if !invalid.contains_key(&a) {
                    let mut candidate = db.clone();
                    let mut all_lp = !own.is_empty();
                    let mut applied_lp = 0;
                    let mut reason = String::new();
                    for log in &own {
                        match pool_reduce::liquidity(&mut candidate, p, log) {
                            Ok(true) => {
                                applied_lp += 1;
                            }
                            Ok(false) => {
                                if pool_reduce::settings(&mut candidate, p, log)? {
                                    continue;
                                }
                                all_lp = false;
                                reason = "unhandled pool event or multiple swaps".into();
                                break;
                            }
                            Err(e) => {
                                all_lp = false;
                                reason = e.to_string();
                                break;
                            }
                        }
                    }
                    if all_lp {
                        db = candidate;
                        lp_events += applied_lp;
                    } else {
                        invalid.insert(a, reason);
                    }
                }
            }
            if !feed_logs.is_empty() || !affected.is_empty() {
                for p in pools {
                    if p["binance_symbol"].is_null() {
                        continue;
                    }
                    if let Some(reason) = invalid.get(&address(&p["pool"])?) {
                        for size in &sizes {
                            output.push(json!({"kind":"state_quote","symbol":p["binance_symbol"],"pool":p["pool"],"size_tokens":size,"available_mono_ns":available,"block":block,"state_complete":false,"executable":false,"reason":reason}));
                        }
                    } else {
                        output.extend(quotes(&db, h, p, &sizes, available, block));
                    }
                }
            }
        }
        state_ready = state_ready.max(now);
        for p in pools {
            if p["binance_symbol"].is_null() {
                continue;
            }
            if let Some(reason) = invalid.get(&address(&p["pool"])?) {
                for size in &sizes {
                    output.push(json!({"kind":"state_quote","symbol":p["binance_symbol"],"pool":p["pool"],"size_tokens":size,"available_mono_ns":state_ready,"block":block,"state_complete":false,"executable":false,"reason":reason,"stage":"block_end"}));
                }
            } else {
                for mut quote in quotes(&db, h, p, &sizes, state_ready, block) {
                    quote["stage"] = json!("block_end");
                    output.push(quote);
                }
            }
        }
    }
    output.extend(
        gaps.into_iter()
            .filter(|r| r["mono_ns"].as_u64().is_some_and(|t| t >= start_ns)),
    );
    for row in bbo
        .into_iter()
        .filter(|r| r["mono_ns"].as_u64().is_some_and(|t| t >= start_ns))
    {
        output.push(row);
    }
    output.sort_by_key(|r| {
        r["available_mono_ns"]
            .as_u64()
            .or(r["mono_ns"].as_u64())
            .unwrap_or(0)
    });
    for row in output {
        println!("{row}");
    }
    eprintln!(
        "{}",
        json!({"updates_verified":updates,"oracle_transactions_without_events":oracle_no_events,"updates_failed":failed_updates,"swaps_verified":swaps,"swaps_failed":failed_swaps,"invalid_pools":invalid.len(),"swaps_verified_by_pool":verified_pools,"liquidity_events_applied":lp_events,"anchor":anchor,"last_processed_block":previous["number"],"tail_settle_ms":settle_ns/1_000_000})
    );
    Ok(())
}

#[cfg(test)]
mod quote_size_tests {
    use super::*;
    #[test]
    fn sizes_are_exact_positive_decimals() {
        assert_eq!(size_raw("0.02", 18).unwrap(), 20_000_000_000_000_000);
        for value in ["-0.1", "+1", "0", "1e-2", "0.001"] {
            assert!(size_raw(value, 2).is_err());
        }
        assert!(size_raw("99999999999999999999999999999", 18).is_err());
    }
}
