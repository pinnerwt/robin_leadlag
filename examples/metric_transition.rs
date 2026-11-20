//! Offline Metric transition research harness. No network or log inputs.
//! Requests supply decoded swap arguments; simulateSwapAndRevert skips funding.
#[path = "../src/local_evm.rs"]
mod local_evm;
#[path = "../src/pool.rs"]
mod pool;
#[path = "../src/pool_reduce.rs"]
mod pool_reduce;
use anyhow::{Context, Result, ensure};
use revm::primitives::Address;
use serde_json::{Value, json};
use std::{
    io::{self, BufRead},
    str::FromStr,
};
fn word(n: i128) -> [u8; 32] {
    let mut w = [if n < 0 { 255 } else { 0 }; 32];
    w[16..].copy_from_slice(&n.to_be_bytes());
    w
}
fn transition(db: &mut local_evm::State, request: &Value) -> Result<Value> {
    let h = &request["header"];
    let pool = request["pool"].as_str().context("pool")?;
    let zero = request["zero"].as_bool().context("direction")?;
    let amount = request["amount"]
        .as_str()
        .context("amount string")?
        .parse::<i128>()?;
    ensure!(amount != 0, "zero swap amount");
    ensure!(
        amount > 0 || !request["commit"].as_bool().unwrap_or(false),
        "exact-output commit not enabled"
    );
    // All work is isolated until both provider and swap simulation succeed.
    let mut candidate = db.clone();
    candidate.last_quote = None;
    if let Some(addresses) = request["unavailable_accounts"].as_array() {
        for a in addresses {
            candidate
                .unavailable_accounts
                .insert(Address::from_str(a.as_str().context("upstream address")?)?);
        }
    }
    let result = candidate.run(h, &json!({"to":pool,"data":"0xec069057"}), true)?;
    ensure!(
        result.is_success(),
        "provider failed: {:?}",
        local_evm::output(&result)
    );
    let prices = candidate
        .last_quote
        .clone()
        .context("provider subcall output")?;
    ensure!(prices.len() == 96, "provider output length");
    let mut data = hex::decode("658b6cb7")?;
    for key in ["sender", "recipient"] {
        let a = Address::from_str(request[key].as_str().context(key)?)?;
        let mut w = [0u8; 32];
        w[12..].copy_from_slice(a.as_slice());
        data.extend(w);
    }
    data.extend(word(i128::from(zero)));
    data.extend(word(amount));
    let mut limit = [0u8; 32];
    limit[16..].copy_from_slice(&(if zero { 1 } else { u128::MAX }).to_be_bytes());
    data.extend(limit);
    data.extend(&prices);
    data.extend(word(288));
    data.extend(word(0));
    let simulation_call = json!({"to":pool,"data":format!("0x{}",hex::encode(data))});
    let result = candidate.run_mode(h, &simulation_call, true, true)?;
    ensure!(
        result.is_success(),
        "swap simulation failed: {:?}",
        local_evm::output(&result)
    );
    let out = result.output().context("swap output")?;
    ensure!(
        out.len() == 68 && out[..4] == [0x1f, 0x60, 0x53, 0xde],
        "simulation sentinel missing"
    );
    let d0 = i128::from_be_bytes(out[20..36].try_into()?);
    let d1 = i128::from_be_bytes(out[52..68].try_into()?);
    let filled = if amount > 0 {
        if zero { d0 } else { d1 }
    } else {
        if zero { d1 } else { d0 }
    };
    ensure!(
        filled == amount,
        "partial {} fill: requested {amount}, deltas ({d0}, {d1})",
        if amount > 0 { "input" } else { "output" }
    );
    let changes:Vec<_>=candidate.slots.iter().filter(|(k,v)|db.slots.get(k)!=Some(v)).map(|((a,k),v)|json!({"address":a.to_string(),"slot":k.to_string(),"value":v.to_string()})).collect();
    let commit = request["commit"].as_bool().unwrap_or(false);
    if commit {
        *db = candidate;
    }
    let logs:Vec<_>=result.logs().iter().map(|l|json!({"address":l.address.to_string().to_lowercase(),"topics":l.data.topics().iter().map(|x|x.to_string()).collect::<Vec<_>>(),"data":format!("0x{}",hex::encode(&l.data.data))})).collect();
    Ok(
        json!({"logs":logs,"simulation_call":simulation_call,"amount0":d0.to_string(),"amount1":d1.to_string(),"committed":commit,"storage_changes":changes,"simulation_only":true,"funding_checked":false}),
    )
}
fn oracle_update(db: &mut local_evm::State, request: &Value) -> Result<Value> {
    let tx = &request["transaction"];
    let to = tx["to"].as_str().context("oracle address")?.to_lowercase();
    ensure!(
        matches!(
            to.as_str(),
            "0xe844701934d9c6085b292e428f41b911cc0b3872"
                | "0x30a88bf894d1b806125a23ebf23d715496fd7102"
        ),
        "unsupported oracle update target"
    );
    let mut candidate = db.clone();
    let result = candidate.run(&request["header"], tx, true)?;
    ensure!(
        result.is_success(),
        "oracle update rejected: {:?}",
        local_evm::output(&result)
    );
    let changed = candidate
        .slots
        .iter()
        .filter(|(k, v)| db.slots.get(k) != Some(v))
        .count();
    let commit = request["commit"].as_bool().unwrap_or(false);
    if commit {
        *db = candidate;
    }
    Ok(
        json!({"committed":commit,"changed_slots":changed,"kind":"oracle_update","success_assumed":true}),
    )
}
fn main() -> Result<()> {
    let seed: Value = serde_json::from_slice(&std::fs::read(
        std::env::args().nth(1).context("seed path")?,
    )?)?;
    let mut accounts = seed["accounts"].clone();
    if let Some(path) = std::env::args().nth(2) {
        let scope: Value = serde_json::from_slice(&std::fs::read(path)?)?;
        let allowed = scope["accounts"].as_array().context("scope accounts")?;
        accounts
            .as_object_mut()
            .context("seed accounts")?
            .retain(|a, _| {
                allowed
                    .iter()
                    .any(|v| v.as_str().is_some_and(|s| s.eq_ignore_ascii_case(a)))
            });
    }
    let mut db = local_evm::State::load(&accounts)?;
    for line in io::stdin().lock().lines() {
        let req: Value = serde_json::from_str(&line?)?;
        let operation = match req["kind"].as_str().unwrap_or("swap") {
            "swap" => transition(&mut db, &req),
            "oracle_update" => oracle_update(&mut db, &req),
            _ => Err(anyhow::anyhow!("unsupported request kind")),
        };
        let result = match operation {
            Ok(v) => json!({"result":v}),
            Err(e) => json!({"error":format!("{e:#}")}),
        };
        println!("{result}");
    }
    Ok(())
}
