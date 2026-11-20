//! Quote-relevant pool storage reducer for LP events with no configured LP hooks.
use crate::{local_evm::State, pool};
use anyhow::{Context, Result, ensure};
use revm::primitives::{Address, U256, keccak256};
use serde_json::Value;
use std::str::FromStr;
fn abi(n: i128) -> [u8; 32] {
    let mut w = [if n < 0 { 255 } else { 0 }; 32];
    w[16..].copy_from_slice(&n.to_be_bytes());
    w
}
pub fn bin_key(bin: i128, slot: u8) -> U256 {
    let mut data = abi(bin).to_vec();
    data.extend(U256::from(slot).to_be_bytes::<32>());
    U256::from_be_bytes(keccak256(data).0)
}
fn signed_add(value: U256, delta: i128) -> Result<U256> {
    if delta < 0 {
        value.checked_sub(U256::from(delta.unsigned_abs()))
    } else {
        value.checked_add(U256::from(delta as u128))
    }
    .context("pool balance overflow/underflow")
}
pub fn liquidity(db: &mut State, p: &Value, log: &Value) -> Result<bool> {
    let Some(event) = pool::decode(log)? else {
        return Ok(false);
    };
    let remove = event["event"] == "liquidity_remove";
    if !remove && event["event"] != "liquidity_add" {
        return Ok(false);
    }
    let imm = hex::decode(
        p["immutables"]
            .as_str()
            .context("immutables")?
            .trim_start_matches("0x"),
    )?;
    let order = if remove { 20 } else { 18 };
    ensure!(
        imm[order * 32..(order + 2) * 32].iter().all(|b| *b == 0),
        "LP extensions need explicit replay"
    );
    let address = Address::from_str(p["pool"].as_str().context("pool")?)?;
    let mask104: U256 = (U256::from(1) << 104) - U256::from(1);
    let mask128: U256 = (U256::from(1) << 128) - U256::from(1);
    let mut total = *db
        .slots
        .get(&(address, U256::from(1)))
        .context("bin totals missing")?;
    let mut slot0 = *db
        .slots
        .get(&(address, U256::ZERO))
        .context("slot0 missing")?;
    let current = ((slot0 >> 8usize) & U256::from(65535)).to::<u16>() as i16;
    for row in event["bins"].as_array().context("bin deltas")? {
        let bin = row[0].as_i64().context("bin index")? as i128;
        let key = bin_key(bin, 4);
        let share_key = bin_key(bin, 5);
        let old = *db.slots.get(&(address, key)).context("unseeded bin")?;
        let d0 = row[1].as_str().context("delta0")?.parse::<i128>()?;
        let d1 = row[2].as_str().context("delta1")?.parse::<i128>()?;
        let n0 = signed_add(old & mask104, d0)?;
        let n1 = signed_add((old >> 104) & mask104, d1)?;
        ensure!(n0 <= mask104 && n1 <= mask104, "bin balance width");
        db.slots
            .insert((address, key), (old >> 208 << 208) | n0 | (n1 << 104));
        let total0 = signed_add(total & mask128, d0)?;
        let total1 = signed_add(total >> 128, d1)?;
        ensure!(total0 <= mask128 && total1 <= mask128, "bin total width");
        total = total0 | (total1 << 128);
        let share_delta = U256::from_str(row[3].as_str().context("shares")?)?;
        let shares = *db
            .slots
            .get(&(address, share_key))
            .context("unseeded shares")?;
        let new_shares = if remove {
            shares.checked_sub(share_delta)
        } else {
            shares.checked_add(share_delta)
        }
        .context("share overflow/underflow")?;
        db.slots.insert((address, share_key), new_shares);
        if remove && bin == i128::from(current) && new_shares == U256::ZERO {
            slot0 = (slot0 & !(mask104 << 24usize))
                | ((if current < 0 { mask104 } else { U256::ZERO }) << 24);
        }
    }
    db.slots.insert((address, U256::from(1)), total);
    db.slots.insert((address, U256::ZERO), slot0);
    Ok(true)
}

pub fn settings(db: &mut State, p: &Value, log: &Value) -> Result<bool> {
    let topic = log["topics"][0].as_str().unwrap_or("");
    let sig = |s: &str| keccak256(s.as_bytes()).to_string();
    let data = hex::decode(
        log["data"]
            .as_str()
            .context("event data")?
            .trim_start_matches("0x"),
    )?;
    let read = |offset: usize| -> Result<U256> {
        Ok(U256::from_be_slice(
            data.get(offset..offset + 32)
                .context("truncated settings")?,
        ))
    };
    let address = Address::from_str(p["pool"].as_str().context("pool")?)?;
    let field = if topic == sig("SpreadFeeUpdated(uint24)") {
        Some((152usize, 24usize, read(0)?))
    } else if topic == sig("NotionalFeeUpdated(uint24)") {
        Some((176, 24, read(0)?))
    } else if topic == sig("BidAskRefAsymmetryUpdated(uint16)") {
        Some((200, 16, read(0)?))
    } else if topic == sig("PauseLevelUpdated(uint8,uint8)") {
        Some((0, 8, read(32)?))
    } else {
        None
    };
    if let Some((offset, width, value)) = field {
        let mask = (U256::from(1) << width) - U256::from(1);
        ensure!(value <= mask, "settings width");
        let old = *db
            .slots
            .get(&(address, U256::ZERO))
            .context("slot0 missing")?;
        db.slots.insert(
            (address, U256::ZERO),
            (old & !(mask << offset)) | (value << offset),
        );
        return Ok(true);
    }
    if topic == sig("BinAdditionalFeesUpdated(int16,uint16,uint16)") {
        let raw = U256::from_str(log["topics"][1].as_str().context("bin")?)?;
        let bin = (raw & U256::from(65535)).to::<u16>() as i16;
        let buy = read(0)?;
        let sell = read(32)?;
        ensure!(
            buy <= U256::from(65535) && sell <= U256::from(65535),
            "fee width"
        );
        let key = bin_key(i128::from(bin), 4);
        let old = *db.slots.get(&(address, key)).context("unseeded bin")?;
        let low224 = (U256::from(1) << 224) - U256::from(1);
        db.slots.insert(
            (address, key),
            (old & low224) | (buy << 224) | (sell << 240),
        );
        return Ok(true);
    }
    if topic == sig("PriceProviderUpdated(address)") {
        let value = U256::from_str(log["topics"][1].as_str().context("provider")?)?;
        ensure!(value >> (160usize) == U256::ZERO, "provider width");
        db.slots.insert((address, U256::from(3)), value);
        return Ok(true);
    }
    Ok(false)
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;
    fn event(remove: bool, bin: i128, d0: i128, d1: i128, shares: i128) -> Value {
        let words = [96, 160, 256, 1, bin, 1, d0, d1, 1, shares];
        json!({"topics":[if remove{"0xf53d04bdbda6d88dd536895ec533833d3e09d0cbe2474fae32a368c5f83fc610"}else{"0xa55772434bee2a347743b1e8086fa44bac69a060e124ec92ab6b9cc7fc5268af"},"0x00","0x00"],"data":format!("0x{}",hex::encode(words.into_iter().flat_map(abi).collect::<Vec<_>>()))})
    }
    #[test]
    fn lp_balances_shares_totals_and_empty_position() {
        for bin in [0i128, -1] {
            let a = Address::from([0x11; 20]);
            let p = json!({"pool":a.to_string(),"immutables":format!("0x{}","00".repeat(768))});
            let mut db = State::default();
            let position = U256::from(123);
            let packed_bin = U256::from(bin as i16 as u16);
            db.slots
                .insert((a, U256::ZERO), (packed_bin << 8) | (position << 24));
            db.slots.insert(
                (a, U256::from(1)),
                U256::from(100) | (U256::from(200) << 128),
            );
            db.slots.insert(
                (a, bin_key(bin, 4)),
                U256::from(100) | (U256::from(200) << 104) | (U256::from(7) << 208),
            );
            db.slots.insert((a, bin_key(bin, 5)), U256::from(100));
            assert!(liquidity(&mut db, &p, &event(false, bin, 20, 30, 15)).unwrap());
            assert_eq!(db.slots[&(a, bin_key(bin, 5))], U256::from(115));
            assert_eq!(
                db.slots[&(a, U256::from(1))],
                U256::from(120) | (U256::from(230) << 128)
            );
            assert!(liquidity(&mut db, &p, &event(true, bin, -120, -230, 115)).unwrap());
            assert_eq!(db.slots[&(a, U256::from(1))], U256::ZERO);
            assert_eq!(db.slots[&(a, bin_key(bin, 4))], U256::from(7) << 208);
            let final_position: U256 = db.slots[&(a, U256::ZERO)] >> 24usize;
            assert_eq!(
                final_position,
                if bin < 0 {
                    (U256::from(1) << 104) - U256::from(1)
                } else {
                    U256::ZERO
                }
            );
        }
    }
    #[test]
    fn unsupported_lp_hook_is_not_silently_skipped() {
        let mut imm = vec![0; 768];
        imm[18 * 32 + 31] = 1;
        let p = json!({"pool":Address::from([0x11;20]).to_string(),"immutables":format!("0x{}",hex::encode(imm))});
        assert!(
            liquidity(&mut State::default(), &p, &event(false, 0, 1, 1, 1))
                .unwrap_err()
                .to_string()
                .contains("LP extensions")
        );
    }
}
