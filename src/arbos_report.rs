//! ArbOS-61 batch report V2, offline and atomic. Pinned Nitro ccc5c828.
//! Unknown storage/accounts and unsupported error paths fail closed.
use crate::{
    arbos_units::{self, slot, subspace},
    local_evm::State,
};
use anyhow::{Context, Result, ensure};
use num_bigint::{BigInt, Sign};
use num_integer::Integer;
use num_traits::{ToPrimitive, Zero};
use revm::primitives::{Address, U256};
use serde_json::Value;
use std::str::FromStr;
fn big(v: U256) -> BigInt {
    BigInt::from_bytes_be(Sign::Plus, &v.to_be_bytes::<32>())
}
fn uint(v: &BigInt) -> Result<U256> {
    ensure!(v >= &BigInt::zero() && v.bits() <= 256, "uint256 overflow");
    Ok(U256::from_be_slice(&v.to_bytes_be().1))
}
struct Work {
    db: State,
    arb: Address,
}
impl Work {
    fn get(&self, space: &[u8], key: u64, signed: bool) -> Result<BigInt> {
        let value = *self
            .db
            .slots
            .get(&(self.arb, slot(space, key)))
            .with_context(|| format!("unseeded report slot {:#x}", slot(space, key)))?;
        let mut n = big(value);
        if signed && value.bit(255) {
            n -= BigInt::from(1u8) << 256;
        }
        Ok(n)
    }
    fn set(&mut self, space: &[u8], key: u64, mut n: BigInt, signed: bool) -> Result<()> {
        if signed {
            let limit = BigInt::from(1u8) << 255;
            n = n.max(-&limit).min(&limit - 1);
            if n.sign() == Sign::Minus {
                n += BigInt::from(1u8) << 256;
            }
        }
        self.db
            .slots
            .insert((self.arb, slot(space, key)), uint(&n)?);
        Ok(())
    }
    fn due(&mut self, table: &[u8], poster: &[u8], n: BigInt) -> Result<()> {
        let old = self.get(poster, 0, true)?;
        let total = self.get(table, 0, true)?;
        self.set(table, 0, total + &n - old, true)?;
        self.set(poster, 0, n, true)
    }
    fn checked_signed(&mut self, space: &[u8], key: u64, n: BigInt) -> Result<()> {
        let limit = BigInt::from(1u8) << 255;
        ensure!(n >= -&limit && n < limit, "signed report storage overflow");
        self.set(space, key, n, true)
    }
    fn transfer(&mut self, to: Address, amount: &BigInt) -> Result<()> {
        ensure!(amount >= &BigInt::zero(), "negative report transfer");
        if amount.is_zero() {
            return Ok(());
        }
        let from = Address::from_str("0xa4b00000000000000000000000000000000000f6")?;
        let source = self
            .db
            .accounts
            .get(&from)
            .context("unseeded L1 funds account")?
            .balance;
        let dest = self
            .db
            .accounts
            .get(&to)
            .context("unseeded report payee")?
            .balance;
        let n = uint(amount)?;
        ensure!(source >= n, "insufficient L1 funds");
        if to != from {
            self.db.accounts.get_mut(&from).unwrap().balance = source - n;
            self.db.accounts.get_mut(&to).unwrap().balance =
                dest.checked_add(n).context("payee balance overflow")?;
        }
        Ok(())
    }
}
fn addr(n: BigInt) -> Result<Address> {
    Ok(Address::from_slice(&uint(&n)?.to_be_bytes::<32>()[12..]))
}
pub fn apply(db: &State, report: &Value, current_time: u64) -> Result<State> {
    ensure!(
        report["system_kind"] == "batch_posting_report_v2",
        "unsupported report type"
    );
    let mut w = Work {
        db: db.clone(),
        arb: Address::from_str(arbos_units::ACCOUNT)?,
    };
    ensure!(
        w.get(&[], 0, false)? == BigInt::from(61),
        "unsupported report ArbOS version"
    );
    let l1 = subspace(&[], &[0]);
    let table = subspace(&l1, &[0]);
    let poster_address = Address::from_str(report["batch_poster"].as_str().context("poster")?)?;
    let poster = subspace(&subspace(&table, &[1]), poster_address.as_slice());
    let members = subspace(&table, &[0]);
    let indexes = subspace(&members, &[0]);
    let raw = U256::from_be_slice(poster_address.as_slice()).to_be_bytes::<32>();
    let mut key = subspace(&indexes, &raw[..31]);
    key[31] = raw[31];
    let key = U256::from_be_slice(&key);
    let member = *w
        .db
        .slots
        .get(&(w.arb, key))
        .context("unseeded batch poster membership")?;
    // New poster initialization is explicit; absent mapping is never assumed zero.
    if member.is_zero() {
        let size = w
            .get(&members, 0, false)?
            .to_u64()
            .context("poster set size")?;
        let next = size.checked_add(1).context("poster set overflow")?;
        w.set(&poster, 0, BigInt::zero(), true)?;
        w.set(
            &poster,
            1,
            big(U256::from_be_slice(poster_address.as_slice())),
            false,
        )?;
        w.db.slots.insert((w.arb, key), U256::from(next));
        w.set(
            &members,
            next,
            big(U256::from_be_slice(poster_address.as_slice())),
            false,
        )?;
        w.set(&members, 0, BigInt::from(next), false)?;
    }
    let length = report["calldata_length"].as_u64().context("batch length")?;
    let nonzero = report["calldata_nonzeros"]
        .as_u64()
        .context("batch nonzeros")?;
    ensure!(nonzero <= length, "invalid batch stats");
    let extra = report["extra_gas"].as_u64().context("extra gas")?;
    let mut gas = 4u64
        .wrapping_mul(length - nonzero)
        .wrapping_add(16u64.wrapping_mul(nonzero))
        .wrapping_add(30)
        .wrapping_add(6u64.wrapping_mul(length.wrapping_add(31) / 32))
        .wrapping_add(40000);
    gas = gas.saturating_add(extra);
    let per_batch = w.get(&l1, 9, false)?.to_u64().context("per-batch gas")? as i64;
    gas = gas.saturating_add(per_batch.max(0) as u64);
    let floor = w.get(&l1, 12, false)?.to_u64().context("gas floor")?;
    gas = gas.max(
        floor
            .wrapping_mul(
                length
                    .wrapping_add(nonzero.wrapping_mul(3))
                    .wrapping_add(172),
            )
            .wrapping_add(21000),
    );
    let base = big(U256::from_str(
        report["l1_base_fee"].as_str().context("L1 base fee")?,
    )?);
    let mut spent = &base * gas;
    let update = U256::from_str(
        report["batch_timestamp"]
            .as_str()
            .context("batch timestamp")?,
    )?
    .as_limbs()[0];
    let mut last = w.get(&l1, 4, false)?.to_u64().context("last report time")?;
    if last == 0 && update > 0 {
        last = update - 1;
    }
    ensure!(
        update <= current_time && update >= last,
        "invalid report time; partial-error path unsupported"
    );
    let mut numerator = update - last;
    let mut denominator = current_time - last;
    if denominator == 0 {
        numerator = 1;
        denominator = 1;
    }
    let units = w.get(&l1, 6, false)?.to_u64().context("calldata units")?;
    let allocated = units.saturating_mul(numerator) / denominator;
    w.set(&l1, 6, BigInt::from(units - allocated), false)?;
    let cap = w.get(&l1, 10, false)?.to_u64().context("cost cap")?;
    if cap > 0 {
        spent = spent.min((&base * allocated * cap.min(i64::MAX as u64)) / 10000);
    }
    let old_due = w.get(&poster, 0, true)?;
    w.due(&table, &poster, old_due + spent)?;
    let reward = w.get(&l1, 3, false)?.to_u64().context("unit reward")?;
    let mut rewards = w.get(&l1, 5, true)? + BigInt::from(allocated) * reward;
    w.checked_signed(&l1, 5, rewards.clone())?;
    let mut available = w.get(&l1, 11, false)?;
    let payment = (BigInt::from(allocated) * reward).min(available.clone());
    rewards -= &payment;
    w.checked_signed(&l1, 5, rewards)?;
    let payee = addr(w.get(&l1, 0, false)?)?;
    w.transfer(payee, &payment)?;
    available -= &payment;
    w.set(&l1, 11, available.clone(), false)?;
    let due = w.get(&poster, 0, true)?;
    let payment = due.clone().min(available.clone());
    if payment > BigInt::zero() {
        let payee = addr(w.get(&poster, 1, false)?)?;
        w.transfer(payee, &payment)?;
        available -= &payment;
        w.set(&l1, 11, available.clone(), false)?;
        w.due(&table, &poster, due - payment)?;
    }
    w.set(&l1, 4, BigInt::from(update), false)?;
    if allocated > 0 {
        let surplus = available - w.get(&table, 0, true)? - w.get(&l1, 5, true)?;
        let inertia = w.get(&l1, 2, false)?;
        let equil = w.get(&l1, 1, false)?;
        ensure!(
            inertia > BigInt::zero() && equil > BigInt::zero(),
            "invalid pricing denominator"
        );
        let inertia_units = equil.div_floor(&inertia);
        let old = w.get(&l1, 8, true)?;
        let desired = (-&surplus).div_floor(&equil);
        let actual = (&surplus - old).div_floor(&BigInt::from(allocated));
        let change = ((desired - actual) * allocated).div_floor(&(inertia_units + allocated));
        let price = (w.get(&l1, 7, false)? + change).max(BigInt::zero());
        w.set(&l1, 8, surplus, true)?;
        w.set(&l1, 7, price, false)?;
    }
    Ok(w.db)
}
