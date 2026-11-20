//! Scoped V3 spot-price dependency, not a V3 liquidity or swap executor.
use anyhow::{Context, Result, ensure};
use revm::primitives::U256;
use serde_json::Value;
pub const SWAP: &str = "0xc42079f94a6350d7e6235f29174924f928cc2ac818eb64fed8004e115fbcca67";
pub fn slot0(old: U256, log: &Value) -> Result<U256> {
    ensure!(log["removed"] != true, "removed V3 price requires recovery");
    ensure!(
        log["topics"].as_array().is_some_and(|x| x.len() == 3) && log["topics"][0] == SWAP,
        "unsupported V3 price event"
    );
    let b = hex::decode(
        log["data"]
            .as_str()
            .context("V3 data")?
            .trim_start_matches("0x"),
    )?;
    ensure!(b.len() == 160, "V3 Swap data length");
    let sqrt = U256::from_be_slice(&b[64..96]);
    ensure!(
        sqrt > U256::ZERO && sqrt < (U256::from(1) << 160usize),
        "invalid V3 sqrt price"
    );
    let tick = U256::from_be_slice(&b[128..160]);
    let negative = b[157] & 128 != 0;
    ensure!(
        b[128..157]
            .iter()
            .all(|x| *x == if negative { 255 } else { 0 }),
        "invalid V3 tick encoding"
    );
    let mask: U256 = (U256::from(1) << 184usize) - U256::from(1);
    // Observation fields are advanced separately when the tick changes.
    Ok((old & !mask) | sqrt | ((tick & ((U256::from(1) << 24usize) - U256::from(1))) << 160usize))
}
#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;
    #[test]
    fn updates_price_and_signed_tick_preserving_nonprice_bits() {
        let old = U256::from(123) << 184usize;
        let data = format!(
            "0x{}{:064x}{}{}",
            "00".repeat(64),
            77,
            "00".repeat(32),
            "ff".repeat(32)
        );
        let log = json!({"topics":[SWAP,"a","b"],"data":data});
        let n = slot0(old, &log).unwrap();
        assert_eq!(n >> 184usize, U256::from(123));
        assert_eq!(
            n & ((U256::from(1) << 160usize) - U256::from(1)),
            U256::from(77)
        );
        assert_eq!((n >> 160usize) & U256::from(0xffffff), U256::from(0xffffff));
        let mut removed = log.clone();
        removed["removed"] = json!(true);
        assert!(slot0(old, &removed).is_err());
        let mut bad = log;
        bad["data"] = json!("0x00");
        assert!(slot0(old, &bad).is_err());
    }
}

/// Reproduce the ring index, timestamp and tick cumulative used by this adapter.
/// secondsPerLiquidity is deliberately not modeled: these checkpoints do not
/// contain V3 liquidity. Never use this projected state for liquidity/TWAP APIs.
pub fn advance_observation(
    old: U256,
    now: u32,
    read: impl Fn(U256) -> Option<U256>,
) -> Result<(U256, Option<(U256, U256)>)> {
    let index = ((old >> 184usize) & U256::from(65535)).to::<u16>();
    let cardinality = ((old >> 200usize) & U256::from(65535)).to::<u16>();
    let next = ((old >> 216usize) & U256::from(65535)).to::<u16>();
    ensure!(
        cardinality > 0 && index < cardinality && next >= cardinality,
        "invalid observation ring"
    );
    let obs = read(U256::from(index) + U256::from(8)).context("latest V3 observation")?;
    let prev = (obs & U256::from(u32::MAX)).to::<u32>();
    if prev == now {
        return Ok((old, None));
    }
    let cardinality = if next > cardinality && index == cardinality - 1 {
        next
    } else {
        cardinality
    };
    let index = (u32::from(index) + 1) % u32::from(cardinality);
    let tick = ((old >> 160usize) & U256::from(0xffffff)).to::<u32>();
    let tick = ((tick << 8usize) as i32 >> 8usize) as i128;
    let cumulative = ((obs >> 32usize) & ((U256::from(1) << 56usize) - U256::from(1))).to::<u64>();
    let cumulative = ((cumulative << 8usize) as i64 >> 8usize) as i128;
    let updated = cumulative + tick * i128::from(now.wrapping_sub(prev));
    let mask: U256 = (U256::from(1) << 56usize) - U256::from(1);
    let updated = U256::from(updated as u128) & mask;
    let obs = (obs & !((mask << 32usize) | U256::from(u32::MAX)))
        | (updated << 32usize)
        | U256::from(now)
        | (U256::from(1) << 248usize);
    let fields: U256 = U256::from(u32::MAX) << 184usize;
    let slot =
        (old & !fields) | (U256::from(index) << 184usize) | (U256::from(cardinality) << 200usize);
    Ok((slot, Some((U256::from(index) + U256::from(8), obs))))
}

#[cfg(test)]
mod ring_tests {
    use super::*;
    #[test]
    fn advances_negative_tick_cumulative_and_grows_ring() {
        let old = (U256::from(0xfffffd) << 160usize)
            | (U256::from(7) << 184usize)
            | (U256::from(8) << 200usize)
            | (U256::from(10) << 216usize);
        let mask: U256 = (U256::from(1) << 56usize) - U256::from(1);
        let cumulative = U256::from((-200i128) as u128) & mask;
        let obs = (U256::from(1) << 248usize) | (cumulative << 32usize) | U256::from(100);
        let (slot, next) =
            advance_observation(
                old,
                110,
                |k| if k == U256::from(15) { Some(obs) } else { None },
            )
            .unwrap();
        assert_eq!((slot >> 184usize) & U256::from(65535), U256::from(8));
        assert_eq!((slot >> 200usize) & U256::from(65535), U256::from(10));
        let (key, new) = next.unwrap();
        assert_eq!(key, U256::from(16));
        assert_eq!(
            (new >> 32usize) & mask,
            U256::from((-230i128) as u128) & mask
        );
        assert_eq!(new & U256::from(u32::MAX), U256::from(110));
        assert!(
            advance_observation(old, 100, |_| Some(obs))
                .unwrap()
                .1
                .is_none()
        );
        assert!(advance_observation(old, 110, |_| None).is_err());
    }
}

pub const MINT: &str = "0x7a53080ba414158be7ec69b987b5fb7d07dee101fe85488f0853ae16239d0bde";
pub const BURN: &str = "0x0c396cd989a39f4459b5fa1aed6a9a8dcdbc45908acfd67e028cd568da98982c";
pub const GROW: &str = "0xac49e518f90a358f652e4400164f05a5d8f7e35e7747279bc3a93dbf584e125a";
pub fn price_event(old: U256, log: &Value) -> Result<(U256, bool)> {
    ensure!(log["removed"] != true, "removed V3 price requires recovery");
    match log["topics"][0].as_str().context("V3 topic")? {
        SWAP => {
            let new = slot0(old, log)?;
            Ok((
                new,
                ((old >> 160usize) & U256::from(0xffffff))
                    != ((new >> 160usize) & U256::from(0xffffff)),
            ))
        }
        MINT | BURN => {
            ensure!(
                log["topics"].as_array().is_some_and(|x| x.len() == 4),
                "V3 LP topics"
            );
            let bytes = hex::decode(
                log["data"]
                    .as_str()
                    .context("V3 LP data")?
                    .trim_start_matches("0x"),
            )?;
            let mint = log["topics"][0] == MINT;
            ensure!(
                bytes.len() == if mint { 128 } else { 96 },
                "V3 LP data length"
            );
            let offset = if mint { 32 } else { 0 };
            let amount = U256::from_be_slice(&bytes[offset..offset + 32]);
            ensure!(amount < (U256::from(1) << 128usize), "V3 LP amount width");
            let tick = (((old >> 160usize) & U256::from(0xffffff)).to::<u32>() << 8) as i32 >> 8;
            let signed = |v: &Value| -> Result<i32> {
                let b = hex::decode(v.as_str().context("tick")?.trim_start_matches("0x"))?;
                ensure!(b.len() == 32, "tick width");
                let n = i32::from_be_bytes(b[28..].try_into()?);
                ensure!((-887272..=887272).contains(&n), "tick range");
                Ok(n)
            };
            let lower = signed(&log["topics"][2])?;
            let upper = signed(&log["topics"][3])?;
            ensure!(lower < upper, "V3 tick interval");
            Ok((old, amount > U256::ZERO && lower <= tick && tick < upper))
        }
        GROW => {
            let b = hex::decode(
                log["data"]
                    .as_str()
                    .context("V3 grow data")?
                    .trim_start_matches("0x"),
            )?;
            ensure!(b.len() == 64, "V3 grow length");
            let before = U256::from_be_slice(&b[..32]);
            let after = U256::from_be_slice(&b[32..]);
            ensure!(
                after <= U256::from(65535)
                    && after >= before
                    && before == ((old >> 216usize) & U256::from(65535)),
                "V3 growth discontinuity"
            );
            let mask = U256::from(65535) << 216usize;
            Ok(((old & !mask) | (after << 216usize), false))
        }
        _ => anyhow::bail!("unsupported V3 pricing event"),
    }
}

#[cfg(test)]
mod lp_tests {
    use super::*;
    use serde_json::json;
    #[test]
    fn only_nonzero_in_range_liquidity_writes_observations() {
        let old = U256::from(77) | (U256::from(5) << 160usize);
        let mut l = json!({"topics":[BURN,format!("0x{:064x}",0),format!("0x{:064x}",0),format!("0x{:064x}",10)],"data":format!("0x{:064x}{}",1,"00".repeat(64))});
        assert!(price_event(old, &l).unwrap().1);
        l["data"] = json!(format!("0x{}", "00".repeat(96)));
        assert!(!price_event(old, &l).unwrap().1);
        l["topics"][0] = json!(MINT);
        l["data"] = json!(format!(
            "0x{}{:064x}{}",
            "00".repeat(32),
            1,
            "00".repeat(64)
        ));
        assert!(price_event(old, &l).unwrap().1);
        assert!(!price_event(U256::from(10) << 160usize, &l).unwrap().1);
        l["data"] = json!("0x00");
        assert!(price_event(old, &l).is_err());
    }
}
