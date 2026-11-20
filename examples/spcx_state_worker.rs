//! Offline state worker for two-view causal research. Never submits transactions.
#[path = "replay_spcx_scoped.rs"]
pub(crate) mod model;
#[path = "../src/pyth.rs"]
mod pyth;
#[path = "../src/v3_price.rs"]
mod v3_price;
use anyhow::{Context, Result, ensure};
use model::{local_evm, pool, pool_reduce, scoped_reconcile};
use revm::primitives::{Address, U256};
use serde_json::{Value, json};
use std::{
    io::{self, BufRead, Write},
    str::FromStr,
};
pub(crate) fn handle(db: &mut local_evm::State, p: &Value, r: &Value) -> Result<Value> {
    match r["kind"].as_str().context("kind")? {
        "debug_storage" => {
            Ok(json!({"slots":db.slots.iter().map(|((a,k),v)|json!([a.to_string().to_lowercase(),format!("{k:#x}"),format!("{v:#x}")])).collect::<Vec<_>>()}))
        }
        "v3_price" => {
            let addr=r["log"]["address"].as_str().context("V3 price address")?;
            ensure!(p["v3_price_pools"].as_array().is_some_and(|xs|xs.iter().any(|x|x.as_str().is_some_and(|x|x.eq_ignore_ascii_case(addr)))), "wrong V3 price pool");
            let a=Address::from_str(addr)?;
            ensure!(r["log"]["removed"] != true, "removed V3 price requires recovery");
            let quantity = |name: &str| -> Result<u64> {
                Ok(u64::from_str_radix(r["log"][name].as_str().context("V3 log position")?.trim_start_matches("0x"),16)?)
            };
            let cursor=(quantity("blockNumber")?,quantity("transactionIndex")?,quantity("logIndex")?);
            if db.price_cursors.get(&a).is_some_and(|old|cursor<=*old) {
                return Ok(json!({"changed":false,"ignored":"duplicate or late V3 log"}));
            }
            let old=db.known_storage(a,U256::ZERO).context("initial V3 slot0")?;
            let (mut value,write_observation)=v3_price::price_event(old,&r["log"])?;
            let mut observation_changed=false;
            if write_observation {
                let (slot,observation)=v3_price::advance_observation(old,quantity("blockTimestamp")? as u32,|key| db.known_storage(a,key))?;
                if let Some((key,obs))=observation {db.slots.insert((a,key),obs);observation_changed=true;}
                let price_mask:U256=(U256::from(1)<<184)-U256::from(1);
                value=(value & price_mask)|(slot & !price_mask);
            }
            db.slots.insert((a,U256::ZERO),value);
            db.price_cursors.insert(a,cursor);
            Ok(json!({"changed":value!=old || observation_changed}))
        }
        "source" => {
            let a = Address::from_str("0xe844701934d9c6085b292e428f41b911cc0b3872")?;
            let k =
                U256::from_str(p["source_slot"].as_str().unwrap_or(
                    "0x8dfdc825dd0453e7c80b1c1d32ae910e35d6efe9000000000000000000000054",
                ))?;
            let v = U256::from_str(r["word"].as_str().context("word")?)? & !U256::from(255);
            let old = db.known_storage(a, k).context("initial source")?;
            let mask: U256 = (U256::from(1) << 56) - U256::from(1);
            let changed = ((v >> 8) & mask) > ((old >> 8) & mask);
            if changed {
                db.slots.insert((a, k), v);
            }
            Ok(json!({"changed":changed}))
        }
        "aux_info" => {
            let mut preimage = [0u8; 64];
            preimage[..32].copy_from_slice(
                &U256::from(r["feed"].as_u64().context("feed")?).to_be_bytes::<32>(),
            );
            preimage[63] = 1;
            let k = U256::from_be_bytes(revm::primitives::keccak256(preimage).0);
            let v = db
                .known_storage(
                    Address::from_str("0x30a88bf894d1b806125a23ebf23d715496fd7102")?,
                    k,
                )
                .context("auxiliary feed slot")?;
            let packed: U256 = (v >> 96) & ((U256::from(1) << 56) - U256::from(1));
            let ms: u64 = packed.try_into()?;
            Ok(json!({"publish_ms":ms,"slot":format!("{k:#x}")}))
        }
        "aux_oracle" => {
            ensure!(
                r["transaction"]["to"].as_str().is_some_and(
                    |a| a.eq_ignore_ascii_case("0x30a88bf894d1b806125a23ebf23d715496fd7102")
                ),
                "unsupported auxiliary oracle"
            );
            let a = Address::from_str("0x30a88bf894d1b806125a23ebf23d715496fd7102")?;
            let input = r["transaction"]["data"].as_str().context("auxiliary calldata")?;
            // Verified PythOracle.register(bytes32,address,address) only touches
            // registration/blacklist entries for the supplied pool, not feeds.
            if input.starts_with("0xe5fc1f6c") {
                let bytes = hex::decode(&input[2..])?;
                ensure!(bytes.len() == 100, "invalid register length");
                ensure!(bytes[36..48].iter().all(|b| *b == 0)
                    && bytes[68..80].iter().all(|b| *b == 0), "invalid register address");
                let registered = Address::from_slice(&bytes[48..68]);
                let tracked = Address::from_str(p["pool"].as_str().context("tracked pool")?)?;
                ensure!(registered != tracked, "tracked pool registration requires replay");
                return Ok(json!({"changed":false,"ignored":"untracked pool registration"}));
            }
            let updates = pyth::decode_all(
                r["transaction"]["data"]
                    .as_str()
                    .context("auxiliary calldata")?,
            )?;
            let mut changed = 0;
            let mut tracked = vec![];
            let mut updated_feeds = vec![];
            for u in updates {
                let mut preimage = [0u8; 64];
                preimage[..32]
                    .copy_from_slice(&U256::from(u["feed"].as_u64().unwrap()).to_be_bytes::<32>());
                preimage[63] = 1;
                let k = U256::from_be_bytes(revm::primitives::keccak256(preimage).0);
                if let Some(old) = db.known_storage(a, k) {
                    let ms = u["publish_us"].as_u64().unwrap() / 1000;
                    tracked.push(json!({"feed":u["feed"],"publish_ms":ms}));
                    if U256::from(ms) > ((old >> 96) & ((U256::from(1) << 56) - U256::from(1))) {
                        let value = U256::from(u["price_e8"].as_u64().unwrap())
                            | (U256::from(u["spread_e6"].as_u64().unwrap()) << 64)
                            | (U256::from(65535) << 80)
                            | (U256::from(ms) << 96);
                        db.slots.insert((a, k), value);
                        changed += 1;
                        updated_feeds.push(u["feed"].clone());
                    }
                }
            }
            // Successfully decoded updates for feeds outside this sparse pool
            // checkpoint cannot change its known pricing state. Decode errors
            // still fail above; never infer a missing tracked feed value.
            Ok(
                json!({"changed":changed>0,"tracked":tracked,"updated_feeds":updated_feeds,"signature_validation":"assumed successful calldata"}),
            )
        }
        "patch" => {
            for row in r["patch"].as_array().context("patch")? {
                db.slots.insert(
                    (
                        Address::from_str(row[0].as_str().context("address")?)?,
                        U256::from_str(row[1].as_str().context("slot")?)?,
                    ),
                    U256::from_str(row[2].as_str().context("value")?)?,
                );
            }
            Ok(json!({"applied":true}))
        }
        "pool" => {
            let before = db.clone();
            let mut candidate = db.clone();
            let logs = r["logs"].as_array().context("logs")?;
            let mut pending = vec![];
            let mut diagnostics = vec![];
            for log in logs {
                match log["topics"][0].as_str().context("topic")? {
                    "0x0f4f965b9381ad88a8ce70d51b86e6162cbebbdfa906901cb34fe0858b30b596" => {
                        // ProtocolFeesCollected changes fee accounting/token balances,
                        // not bins, binTotals or quote settings. This worker models
                        // quote state only, not fee withdrawals or ERC20 settlement.
                        ensure!(pending.is_empty(), "interleaved fee collection");
                        ensure!(log["topics"].as_array().context("topics")?.len() == 1,
                            "invalid fee topics");
                        ensure!(hex::decode(log["data"].as_str().context("data")?
                            .trim_start_matches("0x"))?.len() == 128, "invalid fee data");
                    }
                    "0xcad09799f755048f0fd388c6b2fcc8e0cebefd15756c6903522cc2a95f661f70" => {
                        pending.push(log.clone())
                    }
                    "0x9734819749a91fc3be03ea83205f924ee08479bd3f0da48efc91d94d050cac1e" => {
                        pending.push(log.clone());
                        diagnostics.push(model::replay_swap(
                            &mut candidate,
                            &r["header"],
                            p,
                            log,
                            &pending,
                        )?);
                        pending.clear();
                    }
                    _ => {
                        ensure!(pending.is_empty(), "interleaved unsupported pool event");
                        if !pool_reduce::liquidity(&mut candidate, p, log)? {
                            ensure!(
                                pool_reduce::settings(&mut candidate, p, log)?,
                                "unknown pool event"
                            );
                        }
                    }
                }
            }
            ensure!(pending.is_empty(), "bin events without terminal swap");
            let mismatches = diagnostics
                .iter()
                .filter(|d| d["token_delta_exact"] == false)
                .count();
            let diagnostic = json!({"swap_count":diagnostics.len(),"token_delta_exact":mismatches==0,"token_mismatch_count":mismatches,"max_price_error_bps":diagnostics.iter().filter_map(|d|d["price_error_bps"].as_f64()).map(f64::abs).fold(0.0,f64::max),"swaps":diagnostics});
            let patch: Vec<_> = candidate
                .slots
                .iter()
                .filter(|(k, v)| before.slots.get(k) != Some(v))
                .map(|((a, k), v)| json!([a.to_string(), format!("{k:#x}"), format!("{v:#x}")]))
                .collect();
            *db = candidate;
            Ok(json!({"patch":patch,"diagnostic":diagnostic}))
        }
        "provider_prices" => {
            let prices = model::quote(db, &r["header"], p)?;
            Ok(json!({"prices":format!("0x{}",hex::encode(prices))}))
        }
        "quote" => {
            let mut temp = db.clone();
            let h = &r["header"];
            let prices = model::quote(&mut temp, h, p)?;
            let q = r["raw_base"]
                .as_str()
                .context("raw_base")?
                .parse::<i128>()?;
            ensure!(q > 0, "positive base amount");
            let mut amounts = vec![];
            let mut errors = vec![];
            for sell in [true, false] {
                let req = model::simulate(
                    p["pool"].as_str().unwrap(),
                    sell,
                    if sell { q } else { -q },
                    &prices,
                    "0xca11bde05977b3631167028862be2a173976ca11",
                    "0xca11bde05977b3631167028862be2a173976ca11",
                )?;
                let result = (|| -> Result<String> {
                    let outcome = temp.run(h, &req, false)?;
                    let ds = model::sim_delta(&outcome)?;
                    ensure!(ds[0] == if sell { q } else { -q }, "partial fill");
                    Ok(ds[1].unsigned_abs().to_string())
                })();
                match result {
                    Ok(amount) => { amounts.push(Some(amount)); errors.push(None); }
                    Err(e) => { amounts.push(None); errors.push(Some(e.to_string())); }
                }
            }
            Ok(json!({"bid_raw":amounts[0],"ask_raw":amounts[1],"bid_error":errors[0],"ask_error":errors[1]}))
        }
        _ => anyhow::bail!("unknown request"),
    }
}
fn main() -> Result<()> {
    let path = std::env::args().nth(1).context("checkpoint")?;
    ensure!(
        std::env::args().any(|a| a == "--source-only" || a == "--provider-full"),
        "explicit provider mode required"
    );
    let seed: Value = serde_json::from_slice(&std::fs::read(path)?)?;
    let pools = seed["pools"].as_array().context("pools")?;
    let p = if pools.len() == 1 {
        &pools[0]
    } else {
        pools
            .iter()
            .find(|p| p["binance_symbol"] == "SPCXBUSDT")
            .context("select a single pool")?
    };
    let mut db = local_evm::State::load(&seed["accounts"])?;
    let mut out = io::stdout().lock();
    for line in io::stdin().lock().lines() {
        let r: Value = serde_json::from_str(&line?)?;
        let response = match handle(&mut db, p, &r) {
            Ok(v) => json!({"result":v}),
            Err(e) => json!({"error":e.to_string()}),
        };
        writeln!(out, "{response}")?;
        out.flush()?;
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn valid_untracked_auxiliary_update_is_a_noop_but_malformed_is_not() {
        let mut db = local_evm::State::default();
        let input = include_str!("../tests/fixtures/spcx-update.hex").trim();
        let req = json!({"kind":"aux_oracle","transaction":{"to":"0x30a88bf894d1b806125a23ebf23d715496fd7102","data":input}});
        let out = handle(&mut db, &Value::Null, &req).unwrap();
        assert_eq!(out["changed"],false);
        assert!(out["tracked"].as_array().unwrap().is_empty());
        assert!(db.slots.is_empty());
        let mut malformed=req;malformed["transaction"]["data"]=json!("0x00");
        assert!(handle(&mut db,&Value::Null,&malformed).is_err());
    }
    #[test]
    fn auxiliary_update_is_monotonic_and_atomic_on_decode_error() {
        let a = Address::from_str("0x30a88bf894d1b806125a23ebf23d715496fd7102").unwrap();
        let mut preimage = [0u8; 64];
        preimage[..32].copy_from_slice(&U256::from(pyth::FEED).to_be_bytes::<32>());
        preimage[63] = 1;
        let key = U256::from_be_bytes(revm::primitives::keccak256(preimage).0);
        let mut db = local_evm::State::default();
        db.slots.insert((a, key), U256::ZERO);
        let input = include_str!("../tests/fixtures/spcx-update.hex").trim();
        let mut req = json!({"kind":"aux_oracle","transaction":{"to":a.to_string(),"data":input}});
        assert_eq!(
            handle(&mut db, &Value::Null, &req).unwrap()["changed"],
            true
        );
        let expected = U256::from(13_594_407_000u64)
            | (U256::from(2) << 64)
            | (U256::from(65535) << 80)
            | (U256::from(1_794_655_995_800u64) << 96);
        assert_eq!(db.slots[&(a, key)], expected);
        assert_eq!(
            handle(&mut db, &Value::Null, &req).unwrap()["changed"],
            false
        );
        // A newer checkpoint must never be overwritten by an older recorded update.
        let newer = expected + (U256::from(1000) << 96);
        db.slots.insert((a, key), newer);
        assert_eq!(
            handle(&mut db, &Value::Null, &req).unwrap()["changed"],
            false
        );
        req["transaction"]["data"] = json!(&input[..input.len() - 2]);
        assert!(handle(&mut db, &Value::Null, &req).is_err());
        assert_eq!(db.slots[&(a, key)], newer);
    }
    #[test]
    fn unrelated_registration_is_noop_but_tracked_or_malformed_fails() {
        let mut db = local_evm::State::default();
        let tracked = Address::from([0x11;20]);
        let other = Address::from([0x22;20]);
        let p = json!({"pool":tracked.to_string()});
        let input = format!("0xe5fc1f6c{}{}{}{}{}", "00".repeat(32), "00".repeat(12), hex::encode(other), "00".repeat(12), hex::encode(other));
        let mut r = json!({"kind":"aux_oracle","transaction":{"to":"0x30a88bf894d1b806125a23ebf23d715496fd7102","data":input}});
        assert_eq!(handle(&mut db,&p,&r).unwrap()["changed"],false);
        assert!(handle(&mut db,&json!({"pool":other.to_string()}),&r).is_err());
        r["transaction"]["data"] = json!("0xe5fc1f6c");
        assert!(handle(&mut db,&p,&r).is_err());
    }
    #[test]
    fn protocol_fee_collection_preserves_quote_storage() {
        let mut db = local_evm::State::default();
        let a = Address::from([0x11;20]);
        db.slots.insert((a,U256::ZERO),U256::from(123));
        let r = json!({"kind":"pool","logs":[{"topics":["0x0f4f965b9381ad88a8ce70d51b86e6162cbebbdfa906901cb34fe0858b30b596"],"data":format!("0x{}","00".repeat(128))}]});
        assert_eq!(handle(&mut db,&json!({"pool":a.to_string()}),&r).unwrap()["patch"],json!([]));
        assert_eq!(db.slots[&(a,U256::ZERO)],U256::from(123));
    }

}

#[cfg(test)]
mod v3_worker_tests {
    use super::*;
    #[test]
    fn freshness_projection_and_late_logs_are_monotonic() {
        let a=Address::from_str("0x52e65b17fb6e5ba00ed806f37afcd2daa50271ca").unwrap();
        let p=json!({"v3_price_pools":[a.to_string()]});
        let mut db=local_evm::State::default();
        db.slots.insert((a,U256::ZERO),U256::from(77)|(U256::from(3)<<184)|(U256::from(8)<<200)|(U256::from(8)<<216));
        let obs=(U256::from(999)<<32)|U256::from(10);
        db.slots.insert((a,U256::from(11)),obs);
        let log=json!({"address":a.to_string(),"topics":[v3_price::SWAP,"a","b"],"blockNumber":"0x2","transactionIndex":"0x0","logIndex":"0x1","blockTimestamp":"0x20","data":format!("0x{}{:064x}{}{:064x}","00".repeat(64),78,"00".repeat(32),1)});
        let request=json!({"kind":"v3_price","log":log});
        assert_eq!(handle(&mut db,&p,&request).unwrap()["changed"],true);
        assert_eq!(db.known_storage(a,U256::from(12)),Some((U256::from(1)<<248)|(U256::from(999)<<32)|U256::from(32)));
        assert_eq!(handle(&mut db,&p,&request).unwrap()["changed"],false);
        let mut older=request.clone();older["log"]["blockNumber"]=json!("0x1");
        assert_eq!(handle(&mut db,&p,&older).unwrap()["changed"],false);
        let mut removed=request;removed["log"]["removed"]=json!(true);
        assert!(handle(&mut db,&p,&removed).is_err());
    }
}
