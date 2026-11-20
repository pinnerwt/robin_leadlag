use anyhow::{Context, Result, ensure};
use serde_json::{Value, json};
use std::collections::BTreeMap;

const ADD: &str = "0xa55772434bee2a347743b1e8086fa44bac69a060e124ec92ab6b9cc7fc5268af";
const REMOVE: &str = "0xf53d04bdbda6d88dd536895ec533833d3e09d0cbe2474fae32a368c5f83fc610";
const BIN_SWAP: &str = "0xcad09799f755048f0fd388c6b2fcc8e0cebefd15756c6903522cc2a95f661f70";

fn signed(word: &[u8]) -> Result<i128> {
    let number = i128::from_be_bytes(word[16..].try_into()?);
    ensure!(
        word[..16]
            .iter()
            .all(|&byte| byte == if number < 0 { 255 } else { 0 }),
        "ABI integer outside i128"
    );
    Ok(number)
}

fn word(data: &[u8], offset: usize) -> Result<&[u8]> {
    data.get(offset..offset.checked_add(32).context("ABI offset overflow")?)
        .context("truncated ABI word")
}

fn array(data: &[u8], head: usize, stride: usize) -> Result<&[u8]> {
    let offset = usize::try_from(signed(word(data, head)?)?)?;
    ensure!(offset >= 96 && offset % 32 == 0, "invalid ABI offset");
    let len = usize::try_from(signed(word(data, offset)?)?)?;
    let start = offset + 32;
    let end = len
        .checked_mul(stride)
        .and_then(|n| start.checked_add(n))
        .context("ABI array size overflow")?;
    data.get(start..end).context("truncated ABI array")
}

pub fn decode(log: &Value) -> Result<Option<Value>> {
    let kind = match log["topics"][0].as_str() {
        Some(ADD) => "liquidity_add",
        Some(REMOVE) => "liquidity_remove",
        Some(BIN_SWAP) => "bin_swap",
        _ => return Ok(None),
    };
    let data = hex::decode(
        log["data"]
            .as_str()
            .and_then(|x| x.strip_prefix("0x"))
            .context("missing event data")?,
    )?;
    let mut bins = Vec::new();
    if kind == "bin_swap" {
        ensure!(data.len() == 96, "invalid BinSwapped payload");
        let bin = i16::try_from(signed(word(&data, 0)?)?)?;
        let d0 = i128::from_be_bytes(data[32..48].try_into()?);
        let d1 = i128::from_be_bytes(data[48..64].try_into()?);
        bins.push(json!([bin, d0.to_string(), d1.to_string()]));
        return Ok(Some(json!({"event":kind,"bins":bins,
            "lp_fee_scaled":u128::from_be_bytes(data[64..80].try_into()?).to_string(),
            "platform_fee_scaled":u128::from_be_bytes(data[80..96].try_into()?).to_string()})));
    }
    let ids = array(&data, 0, 32)?;
    let deltas = array(&data, 32, 64)?;
    let shares = array(&data, 64, 32)?;
    ensure!(
        ids.len() == shares.len() && ids.len() * 2 == deltas.len(),
        "LP array lengths differ"
    );
    for ((id, delta), share) in ids
        .chunks_exact(32)
        .zip(deltas.chunks_exact(64))
        .zip(shares.chunks_exact(32))
    {
        let bin = i16::try_from(signed(id)?)?;
        let d0 = signed(&delta[..32])?;
        let d1 = signed(&delta[32..])?;
        bins.push(json!([
            bin,
            d0.to_string(),
            d1.to_string(),
            format!("0x{}", hex::encode(share))
        ]));
    }
    Ok(Some(
        json!({"event":kind,"bins":bins,"provider":log["topics"][1],"salt":log["topics"][2]}),
    ))
}

#[derive(Clone, Default)]
pub struct Bins {
    pub balances: BTreeMap<i16, [i128; 2]>,
}

impl Bins {
    pub fn apply(&mut self, event: &Value) -> Result<()> {
        self.apply_signed(event, 1)
    }

    pub fn apply_signed(&mut self, event: &Value, sign: i128) -> Result<()> {
        for bin in event["bins"].as_array().context("missing bin changes")? {
            let key = i16::try_from(bin[0].as_i64().context("missing bin index")?)?;
            let balances = self.balances.entry(key).or_default();
            for (i, balance) in balances.iter_mut().enumerate() {
                let delta: i128 = bin[i + 1].as_str().context("missing bin delta")?.parse()?;
                *balance = balance
                    .checked_add(delta.checked_mul(sign).context("bin delta overflow")?)
                    .context("bin balance overflow")?;
            }
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn decodes_mainnet_add_and_remove_and_replays_balances() {
        let logs: Vec<Value> =
            serde_json::from_str(include_str!("../tests/fixtures/carcosa-lp.json")).unwrap();
        let mut bins = Bins::default();
        for (index, log) in logs.iter().enumerate() {
            let event = decode(log).unwrap().unwrap();
            assert_eq!(
                event["event"],
                if index == 0 {
                    "liquidity_add"
                } else {
                    "liquidity_remove"
                }
            );
            let changes = event["bins"].as_array().unwrap();
            assert!(!changes.is_empty());
            let prior = bins.clone();
            bins.apply(&event).unwrap();
            for row in changes {
                let bin = row[0].as_i64().unwrap() as i16;
                let delta = |i: usize| row[i].as_str().unwrap().parse::<i128>().unwrap();
                assert!([delta(1), delta(2)].iter().all(|d| if index == 0 {
                    *d >= 0
                } else {
                    *d <= 0
                }));
                let previous = prior.balances.get(&bin).copied().unwrap_or_default();
                assert_eq!(
                    bins.balances[&bin],
                    [previous[0] + delta(1), previous[1] + delta(2)]
                );
            }
        }
    }
}
