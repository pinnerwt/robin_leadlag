//! Pinned ArbOS 61 deposit mint/transfer. Explicit filter witness required.
use crate::{arbos_units, local_evm::State};
use anyhow::{Context, Result, ensure};
use revm::primitives::{Address, B256, U256};
use serde_json::Value;
use sha3::{Digest, Keccak256};
use std::str::FromStr;
pub const FILTER: &str = "0xa4b0500000000000000000000000000000000001";
pub fn transaction_filtered(db: &State, hash: &str) -> Result<bool> {
    let hash = B256::from_str(hash)?;
    let mut key = [0u8; 32];
    key[..31].copy_from_slice(&Keccak256::digest(&hash[..31])[..31]);
    key[31] = hash[31];
    let value = db
        .known_storage(Address::from_str(FILTER)?, U256::from_be_bytes(key))
        .context("unseeded deposit slot / transaction filter entry")?;
    Ok(value == U256::from(1))
}
pub fn apply(db: &State, tx: &Value) -> Result<(State, bool, Address)> {
    ensure!(tx["system_kind"] == "eth_deposit", "not a deposit");
    let arb = Address::from_str(arbos_units::ACCOUNT)?;
    let get = |a, k| {
        db.known_storage(a, k)
            .with_context(|| format!("unseeded deposit slot {a} {k:#x}"))
    };
    ensure!(
        get(arb, arbos_units::slot(&[], 0))? == U256::from(61),
        "unsupported deposit ArbOS version"
    );
    let filtered = transaction_filtered(db, tx["tx"].as_str().context("deposit tx hash")?)?;
    let from = Address::from_str(tx["from"].as_str().context("deposit from")?)?;
    let mut to = Address::from_str(tx["to"].as_str().context("deposit to")?)?;
    if filtered {
        let recipient = get(arb, arbos_units::slot(&[], 10))?.to_be_bytes::<32>();
        to = Address::from_slice(&recipient[12..]);
        if to == Address::ZERO {
            let fee = get(arb, arbos_units::slot(&[], 3))?.to_be_bytes::<32>();
            to = Address::from_slice(&fee[12..]);
        }
    }
    let value = U256::from_str(tx["value"].as_str().context("deposit value")?)?;
    let from_balance = db
        .accounts
        .get(&from)
        .context("unseeded deposit sender")?
        .balance;
    from_balance
        .checked_add(value)
        .context("deposit mint overflow")?;
    let balance = db
        .accounts
        .get(&to)
        .context("unseeded deposit recipient")?
        .balance
        .checked_add(value)
        .context("deposit recipient overflow")?;
    let mut next = db.clone();
    next.accounts.get_mut(&to).unwrap().balance = balance;
    // Mint to sender then transfer: sender net unchanged unless sender==recipient.
    // No EVM call, gas charge, nonce increment, or filter deletion occurs here.
    Ok((next, filtered, to))
}
