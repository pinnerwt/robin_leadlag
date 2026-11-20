//! Observed pool balance/position reconciliation. Extension state remains approximate.
use crate::{local_evm::State, pool, pool_reduce};
use anyhow::{Context, Result, ensure};
use revm::primitives::{Address, U256};
use serde_json::Value;
fn add(v: U256, d: i128) -> Result<U256> {
    if d < 0 {
        v.checked_sub(U256::from(d.unsigned_abs()))
    } else {
        v.checked_add(U256::from(d as u128))
    }
    .context("observed balance overflow")
}
pub fn reconcile(
    before: &State,
    after: &mut State,
    address: Address,
    swap: &Value,
    logs: &[Value],
) -> Result<()> {
    let mask104: U256 = (U256::from(1) << 104) - U256::from(1);
    let mask128: U256 = (U256::from(1) << 128) - U256::from(1);
    let mut total = before
        .known_storage(address, U256::from(1))
        .context("totals")?;
    let mut bins = std::collections::HashMap::new();
    for l in logs {
        if !l["address"]
            .as_str()
            .is_some_and(|a| a.eq_ignore_ascii_case(&address.to_string()))
        {
            continue;
        }
        let Some(e) = pool::decode(l)? else { continue };
        if e["event"] != "bin_swap" {
            continue;
        }
        for row in e["bins"].as_array().context("bins")? {
            let key = pool_reduce::bin_key(row[0].as_i64().context("bin")? as i128, 4);
            let old = *bins
                .entry(key)
                .or_insert(before.known_storage(address, key).context("seeded bin")?);
            let d0 = row[1].as_str().context("d0")?.parse()?;
            let d1 = row[2].as_str().context("d1")?.parse()?;
            let n0 = add(old & mask104, d0)?;
            let n1 = add((old >> 104) & mask104, d1)?;
            ensure!(n0 <= mask104 && n1 <= mask104, "bin width");
            bins.insert(key, (old >> 208 << 208) | n0 | (n1 << 104));
            let t0 = add(total & mask128, d0)?;
            let t1 = add(total >> 128, d1)?;
            ensure!(t0 <= mask128 && t1 <= mask128, "totals width");
            total = t0 | (t1 << 128);
        }
    }
    ensure!(!bins.is_empty(), "missing observed bin transitions");
    for (k, v) in bins {
        after.slots.insert((address, k), v);
    }
    after.slots.insert((address, U256::from(1)), total);
    let data = hex::decode(
        swap["data"]
            .as_str()
            .context("swap data")?
            .trim_start_matches("0x"),
    )?;
    ensure!(data.len() == 96, "swap length");
    let details = U256::from_be_slice(&data[..32]);
    let old = before
        .known_storage(address, U256::ZERO)
        .context("position")?;
    let fields: U256 = (mask104 << 24) | (U256::from(65535) << 8);
    after.slots.insert(
        (address, U256::ZERO),
        (old & !fields)
            | ((details & mask104) << 24)
            | (((details >> 104) & U256::from(65535)) << 8),
    );
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::str::FromStr;
    #[test]
    fn captured_buy_restores_observed_balances_and_position() {
        let f: Value = serde_json::from_str(include_str!(
            "../tests/fixtures/spcx_observed_bin_reconcile.json"
        ))
        .unwrap();
        let before = State::load(&f["accounts"]).unwrap();
        let mut after = before.clone();
        let address = Address::from_str(f["address"].as_str().unwrap()).unwrap();
        // Deliberately wrong simulated totals must not accumulate into observed balances.
        after.slots.insert((address, U256::from(1)), U256::ZERO);
        reconcile(
            &before,
            &mut after,
            address,
            &f["swap"],
            f["logs"].as_array().unwrap(),
        )
        .unwrap();
        for (k, v) in f["expected"].as_object().unwrap() {
            assert_eq!(
                after.known_storage(address, U256::from_str(k).unwrap()),
                Some(U256::from_str(v.as_str().unwrap()).unwrap())
            );
        }
    }
    #[test]
    fn absent_bin_events_cannot_claim_reconciliation() {
        let f: Value = serde_json::from_str(include_str!(
            "../tests/fixtures/spcx_observed_bin_reconcile.json"
        ))
        .unwrap();
        let before = State::load(&f["accounts"]).unwrap();
        let mut after = before.clone();
        assert!(
            reconcile(
                &before,
                &mut after,
                Address::from_str(f["address"].as_str().unwrap()).unwrap(),
                &f["swap"],
                &[]
            )
            .is_err()
        );
    }
}
