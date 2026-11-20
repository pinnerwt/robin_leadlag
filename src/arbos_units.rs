//! ArbOS 61 calldata-unit hook, not a complete ArbOS implementation.
//! Derived from Nitro ccc5c828d9ea22f161efc784bac4d4a6559b7e59.
use anyhow::{Context, Result, ensure};
use revm::primitives::{Address, U256};
use serde_json::Value;
use std::{io::Cursor, str::FromStr};
pub const ACCOUNT: &str = "0xa4b05fffffffffffffffffffffffffffffffffff";
pub const SLOT: &str = "0xa9f6f085d78d1d37c5819e5c16c9e03198bd14e08cd1f6f8191bc6207b9e9706";
const ROOT: &str = "0x15fed0451499512d95f3ec5a41c878b9de55f21878b5b4e190d4667ec709b4";
fn rlp(raw: &[u8], list: bool) -> Vec<u8> {
    if !list && raw.len() == 1 && raw[0] < 128 {
        return raw.to_vec();
    }
    let base = if list { 192 } else { 128 };
    let mut out = Vec::new();
    if raw.len() < 56 {
        out.push(base + raw.len() as u8);
    } else {
        let n = raw.len().to_be_bytes();
        let i = n.iter().position(|x| *x != 0).unwrap();
        out.push(base + 55 + (n.len() - i) as u8);
        out.extend(&n[i..]);
    }
    out.extend(raw);
    out
}
fn number(s: &str) -> Result<Vec<u8>> {
    let n = U256::from_str(s)?.to_be_bytes::<32>();
    let i = n.iter().position(|x| *x != 0).unwrap_or(32);
    Ok(rlp(&n[i..], false))
}
fn fake(tx: &Value) -> Result<Vec<u8>> {
    ensure!(
        tx.get("raw_transaction").is_none() && tx.get("nonce").is_none(),
        "probe mode cannot process signed feed records"
    );
    let mut body = Vec::new();
    for n in ["0x0", "0xa844cbcad86eb849", "0x39ba7d26", "0xf1aa387f"] {
        body.extend(number(n)?);
    }
    body.extend(number(&format!(
        "0x{:x}",
        tx["gas_limit"].as_u64().unwrap_or(30_000_000)
    ))?);
    body.extend(rlp(
        &hex::decode(tx["to"].as_str().unwrap_or("0x").trim_start_matches("0x"))?,
        false,
    ));
    body.extend(number(tx["value"].as_str().unwrap_or("0x0"))?);
    body.extend(rlp(
        &hex::decode(
            tx["data"]
                .as_str()
                .context("data")?
                .trim_start_matches("0x"),
        )?,
        false,
    ));
    body.extend(rlp(&[], true));
    for n in [
        "0x1ee13",
        "0xef22bddd350b943170a67d35191c27e310709a28c38b5762a152ff640108f5b2",
        "0xa9463b19d1148abedba3d6925530d4465b271ce2cc61f80b1a0a80fd73eab881",
    ] {
        body.extend(number(n)?);
    }
    let mut out = vec![2];
    out.extend(rlp(&body, true));
    Ok(out)
}
pub fn increment(tx: &Value, quality: u32, probe: bool) -> Result<u64> {
    ensure!(quality <= 11, "invalid brotli quality");
    let raw = if probe {
        fake(tx)?
    } else {
        hex::decode(
            tx["raw_transaction"]
                .as_str()
                .context("raw signed transaction required")?
                .trim_start_matches("0x"),
        )?
    };
    let params = brotli::enc::BrotliEncoderParams {
        quality: quality as i32,
        lgwin: 22,
        ..Default::default()
    };
    let mut out = Vec::new();
    brotli::BrotliCompress(&mut Cursor::new(raw), &mut out, &params)?;
    let units = (out.len() as u64).saturating_mul(16);
    Ok(if probe {
        (units + 256) * 10100 / 10000
    } else {
        units
    })
}
pub fn parameters(db: &crate::local_evm::State) -> Result<(Address, U256, u64, u32)> {
    let a = Address::from_str(ACCOUNT)?;
    let key = U256::from_str(SLOT)?;
    let get = |s: &str| -> Result<U256> {
        db.slots
            .get(&(a, U256::from_str(s)?))
            .copied()
            .context("unseeded ArbOS parameter")
    };
    ensure!(
        get(&(ROOT.to_owned() + "00"))? == U256::from(61),
        "only ArbOS 61 audited"
    );
    // Nonzero poster pricing requires a separate gas charging implementation.
    ensure!(
        get("0xa9f6f085d78d1d37c5819e5c16c9e03198bd14e08cd1f6f8191bc6207b9e9707")? == U256::ZERO,
        "nonzero L1 poster price unsupported"
    );
    Ok((
        a,
        key,
        get(SLOT)?.try_into().context("unit overflow")?,
        get(&(ROOT.to_owned() + "07"))?
            .try_into()
            .context("quality overflow")?,
    ))
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn matches_frozen_mainnet_and_independent_c_brotli_fixtures() {
        let fixtures: Value =
            serde_json::from_str(include_str!("../tests/fixtures/arbos_units.json")).unwrap();
        for row in fixtures.as_array().unwrap() {
            assert_eq!(
                increment(
                    &row["tx"],
                    row["quality"].as_u64().unwrap() as u32,
                    row["probe"].as_bool().unwrap()
                )
                .unwrap(),
                row["expected"].as_u64().unwrap()
            );
        }
    }
    #[test]
    fn signed_feed_cannot_use_estimation_padding() {
        assert!(increment(&serde_json::json!({"raw_transaction":"0x02"}), 1, true).is_err());
    }
}

pub(crate) fn subspace(parent: &[u8], name: &[u8]) -> Vec<u8> {
    use sha3::{Digest, Keccak256};
    let mut h = Keccak256::new();
    h.update(parent);
    h.update(name);
    h.finalize().to_vec()
}
pub(crate) fn slot(space: &[u8], offset: u64) -> U256 {
    let mut key = [0u8; 32];
    key[24..].copy_from_slice(&offset.to_be_bytes());
    let mut hash = subspace(space, &key[..31]);
    hash[31] = key[31];
    U256::from_be_slice(&hash)
}
/// ArbOS 61 single-dimensional constraints only; all keys must be initialized.
/// Returns writes without mutating db, so callers can apply the full transition atomically.
pub fn grow_backlog(db: &crate::local_evm::State, gas: u64) -> Result<Vec<(U256, U256)>> {
    let (a, _, _, _) = parameters(db)?;
    let read = |k: U256| -> Result<u64> {
        db.slots
            .get(&(a, k))
            .context("unseeded gas backlog")?
            .try_into()
            .context("backlog overflow")
    };
    let l2 = subspace(&[], &[1]);
    let single = subspace(&l2, &[0]);
    let multi = subspace(&l2, &[1]);
    ensure!(
        read(slot(&multi, 0))? == 0,
        "multi-resource gas constraints not implemented"
    );
    let n = read(slot(&single, 0))?;
    ensure!(n <= 1024, "invalid gas constraint count");
    let keys = if n == 0 {
        vec![slot(&l2, 4)]
    } else {
        (0..n)
            .map(|i| slot(&subspace(&single, &i.to_be_bytes()), 2))
            .collect()
    };
    keys.into_iter()
        .map(|k| Ok((k, U256::from(read(k)?.saturating_add(gas)))))
        .collect()
}

pub fn fee_recipients(db: &crate::local_evm::State, basefee: U256) -> Result<Vec<(Address, U256)>> {
    let (a, _, _, _) = parameters(db)?;
    let read = |k: U256| -> Result<U256> {
        db.slots
            .get(&(a, k))
            .copied()
            .context("unseeded fee parameter")
    };
    ensure!(
        read(U256::from_str(&(ROOT.to_owned() + "0b"))?)? == U256::ZERO,
        "tip collection unsupported"
    );
    let address = |offset: &str| -> Result<Address> {
        let raw = read(U256::from_str(&(ROOT.to_owned() + offset))?)?.to_be_bytes::<32>();
        Ok(Address::from_slice(&raw[12..]))
    };
    let network = address("03")?;
    let infra = address("06")?;
    let min_fee = read(slot(&subspace(&[], &[1]), 3))?;
    let infra_fee = if infra.is_zero() {
        U256::ZERO
    } else {
        basefee.min(min_fee)
    };
    let fees = vec![(infra, infra_fee), (network, basefee - infra_fee)];
    for (receiver, rate) in &fees {
        if *rate != U256::ZERO {
            ensure!(
                db.accounts.contains_key(receiver),
                "unseeded fee recipient {receiver}"
            );
        }
    }
    Ok(fees)
}

/// StartBlock single-constraint pricing component only. Other StartBlock hooks
/// (history storage, L1 hashes, retryable reaping, upgrades) are NOT represented.
/// Returns current header fee and the next fee/backlog writes. Never uses newHeads.
pub fn update_pricing(
    db: &crate::local_evm::State,
    elapsed: u64,
) -> Result<(U256, Vec<(U256, U256)>)> {
    let a = Address::from_str(ACCOUNT)?;
    let read = |k: U256| -> Result<U256> {
        db.slots
            .get(&(a, k))
            .copied()
            .with_context(|| format!("unseeded pricing parameter {k:#x}"))
    };
    let u64val =
        |k: U256| -> Result<u64> { read(k)?.try_into().context("pricing parameter overflow") };
    ensure!(
        read(U256::from_str(&(ROOT.to_owned() + "00"))?)? == U256::from(61),
        "only ArbOS 61 audited"
    );
    let l2 = subspace(&[], &[1]);
    let single = subspace(&l2, &[0]);
    let multi = subspace(&l2, &[1]);
    ensure!(
        u64val(slot(&multi, 0))? == 0,
        "multi-resource pricing unsupported"
    );
    let n = u64val(slot(&single, 0))?;
    ensure!(n > 0 && n <= 1024, "single-constraint pricing required");
    let current = read(slot(&l2, 2))?;
    let minimum = read(slot(&l2, 3))?;
    let mut exponent = 0i64;
    let mut writes = Vec::new();
    for i in 0..n {
        let space = subspace(&single, &i.to_be_bytes());
        let target = u64val(slot(&space, 0))?;
        let key = slot(&space, 2);
        let before = u64val(key)?;
        let after = before.saturating_sub(elapsed.saturating_mul(target));
        if before != after {
            writes.push((key, U256::from(after)));
        }
        if after > 0 {
            let window = u64val(slot(&space, 1))?;
            let divisor = window.saturating_mul(target).min(i64::MAX as u64) as i64;
            ensure!(divisor > 0, "zero pricing divisor");
            let numerator = (after.min(i64::MAX as u64) as i64).saturating_mul(10000);
            exponent = exponent.saturating_add(numerator / divisor);
        }
    }
    let x = exponent as u64;
    let mut res = 10000 + x / 4;
    for i in (1..=3).rev() {
        res = 10000u64.saturating_add(res.saturating_mul(x) / (i * 10000));
    }
    let multiplier = res.min(i64::MAX as u64);
    let next = minimum
        .checked_mul(U256::from(multiplier))
        .context("base fee overflow")?
        / U256::from(10000);
    if next != current {
        writes.push((slot(&l2, 2), next));
    }
    Ok((current, writes))
}
