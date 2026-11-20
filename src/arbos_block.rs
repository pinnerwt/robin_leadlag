//! Offline ArbOS 61 StartBlock for audited single-gas pricing / empty retryables.
//! All guards are evaluated before returning writes. No missing state defaults.
use crate::{
    arbos_units::{self, slot, subspace},
    local_evm::State,
};
use anyhow::{Context, Result, ensure};
use revm::primitives::{Address, B256, U256};
use std::str::FromStr;
pub type Writes = Vec<((Address, U256), U256)>;
pub fn start(
    db: &State,
    number: u64,
    timestamp: u64,
    parent_timestamp: u64,
    l1: u64,
    parent_hash: B256,
) -> Result<(U256, Writes)> {
    ensure!(
        number > 0 && timestamp >= parent_timestamp,
        "invalid block context"
    );
    let arb = Address::from_str(arbos_units::ACCOUNT)?;
    let get = |key: U256| -> Result<U256> {
        db.slots
            .get(&(arb, key))
            .copied()
            .with_context(|| format!("unseeded StartBlock slot {key:#x}"))
    };
    let queue = subspace(&subspace(&[], &[2]), &[0]);
    ensure!(
        get(slot(&queue, 0))? == get(slot(&queue, 1))?,
        "nonempty retryable queue requires full reaping semantics"
    );
    let version = get(slot(&[], 0))?;
    ensure!(version == U256::from(61), "unsupported ArbOS version");
    let upgrade = get(slot(&[], 1))?;
    let when = get(slot(&[], 2))?;
    ensure!(
        upgrade <= version || U256::from(timestamp) < when,
        "due ArbOS upgrade unsupported"
    );
    let history = Address::from_str("0x0000f90827f1c53a10cb7a02335b175320002935")?;
    let expected =
        B256::from_str("0xceef1f6ad6c0cb7eb8fb15678abf11da3ce0d3a7c7106aa900c5930e556a43ff")?;
    ensure!(
        db.accounts
            .get(&history)
            .context("unseeded history contract")?
            .code_hash
            == expected,
        "history code changed"
    );
    let (fee, pricing) = arbos_units::update_pricing(db, timestamp - parent_timestamp)?;
    let mut writes: Writes = pricing.into_iter().map(|(k, v)| ((arb, k), v)).collect();
    // The deployed Robinhood bytecode uses PUSH3 0x05ffd0 (393168), not 8191.
    writes.push((
        (history, U256::from((number - 1) % 393168)),
        U256::from_be_slice(parent_hash.as_slice()),
    ));
    let hashes = subspace(&[], &[6]);
    let mut next: u64 = get(slot(&hashes, 0))?
        .try_into()
        .context("L1 height overflow")?;
    if l1 > next {
        let last = l1 - 1;
        if next.saturating_add(256) < last {
            next = last - 256;
        }
        while next.saturating_add(1) < last {
            next += 1;
            let fill = subspace(parent_hash.as_slice(), &next.to_le_bytes());
            writes.push((
                (arb, slot(&hashes, 1 + next % 256)),
                U256::from_be_slice(&fill),
            ));
        }
        writes.push((
            (arb, slot(&hashes, 1 + last % 256)),
            U256::from_be_slice(parent_hash.as_slice()),
        ));
        writes.push(((arb, slot(&hashes, 0)), U256::from(l1)));
    }
    writes.retain(|(key, value)| db.slots.get(key) != Some(value));
    Ok((fee, writes))
}
