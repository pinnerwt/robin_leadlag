use anyhow::{Context, Result, ensure};
use serde_json::{Value, json};

pub const FEED: u32 = 3316;

fn take<'a>(input: &mut &'a [u8], n: usize) -> Result<&'a [u8]> {
    let (bytes, remaining) = input.split_at_checked(n).context("truncated Pyth update")?;
    *input = remaining;
    Ok(bytes)
}

fn read<const N: usize>(input: &mut &[u8]) -> Result<[u8; N]> {
    Ok(take(input, N)?.try_into()?)
}

/// Decode a direct PythOracle fallback input after its receipt emitted FeedUpdated.
pub fn decode_all(input: &str) -> Result<Vec<Value>> {
    let bytes = hex::decode(input.strip_prefix("0x").context("missing hex prefix")?)?;
    let mut data = bytes.as_slice();
    let count = usize::from(u16::from_be_bytes(read(&mut data)?));
    ensure!(count > 0 && count <= 255, "invalid feed count");
    let ids = take(&mut data, 4 * count)?;
    ensure!(
        take(&mut data, 4)? == [0x2a, 0x22, 0x99, 0x9a],
        "wrong EVM envelope"
    );
    take(&mut data, 65)?;
    let length = usize::from(u16::from_be_bytes(read(&mut data)?));
    let mut payload = take(&mut data, length)?;
    ensure!(
        u32::from_be_bytes(read(&mut payload)?) == 2479346549,
        "wrong payload magic"
    );
    take(&mut payload, 9)?;
    ensure!(
        usize::from(read::<1>(&mut payload)?[0]) == count,
        "feed count mismatch"
    );
    let mut result = Vec::new();
    for id in ids.chunks_exact(4) {
        ensure!(take(&mut payload, 4)? == id, "feed ID mismatch");
        let fields = read::<1>(&mut payload)?[0];
        let (mut price, mut exponent, mut confidence, mut publish_us) = (None, None, None, None);
        let mut seen = 0u16;
        for _ in 0..fields {
            let field = read::<1>(&mut payload)?[0];
            ensure!(
                field <= 12 && seen & (1 << field) == 0,
                "invalid property set"
            );
            seen |= 1 << field;
            match field {
                0 => price = Some(i64::from_be_bytes(read(&mut payload)?)),
                4 => exponent = Some(i16::from_be_bytes(read(&mut payload)?)),
                5 => confidence = Some(u64::from_be_bytes(read(&mut payload)?)),
                12 => {
                    if read::<1>(&mut payload)?[0] != 0 {
                        publish_us = Some(u64::from_be_bytes(read(&mut payload)?));
                    }
                }
                1 | 2 | 10 | 11 => {
                    take(&mut payload, 8)?;
                }
                3 | 9 => {
                    take(&mut payload, 2)?;
                }
                _ => anyhow::bail!("unsupported Pyth property {field}"),
            }
        }
        {
            let feed = u32::from_be_bytes(id.try_into()?);
            ensure!(
                !result.iter().any(|v: &Value| v["feed"] == feed),
                "duplicate feed"
            );
            let price = u128::try_from(price.context("missing price")?)?;
            let confidence = u128::from(confidence.context("missing confidence")?);
            let publish_us = publish_us.context("missing feed publish time")?;
            let exponent = i32::from(exponent.context("missing exponent")?) + 8;
            ensure!(
                price > 0 && (-57..=57).contains(&exponent),
                "invalid price/exponent"
            );
            let scale = 10u128.checked_pow(exponent.unsigned_abs());
            let price_e8 = if exponent >= 0 {
                price
                    .checked_mul(scale.context("scale overflow")?)
                    .context("price overflow")?
            } else {
                scale.map_or(0, |scale| price / scale)
            };
            ensure!(
                price_e8 > 0 && publish_us >= 1000 && publish_us / 1000 < 1 << 48,
                "invalid accepted update"
            );
            result.push(json!({
                "feed": feed,
                "price_e8": u64::try_from(price_e8)?,
                "spread_e6": (confidence * 1_000_000).div_ceil(price).min(65534) as u16,
                "publish_us": publish_us
            }));
        }
    }
    ensure!(payload.is_empty(), "unexpected payload remainder");
    Ok(result)
}

pub fn decode(input: &str) -> Result<Value> {
    decode_all(input)?
        .into_iter()
        .find(|v| v["feed"] == FEED)
        .context("SPCX feed missing")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn matches_mainnet_storage() {
        let input = include_str!("../tests/fixtures/spcx-update.hex").trim();
        let result = decode(input).unwrap();
        assert_eq!(result["price_e8"], 13_594_407_000u64);
        assert_eq!(result["spread_e6"], 2);
        assert_eq!(
            result["publish_us"].as_u64().unwrap() / 1000,
            1_794_655_995_800
        );
        assert!(decode(&input[..input.len() - 2]).is_err());
    }
}
