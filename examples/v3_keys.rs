//! Initialization-only Uniswap V3 storage index. No network calls.
use anyhow::Result;
use serde_json::{Value, json};
use sha3::{Digest, Keccak256};
use std::io::{self, Read};
fn key(index: i64, slot: u64) -> String {
    let mut raw = [0u8; 64];
    if index < 0 {
        raw[..32].fill(255);
    }
    raw[24..32].copy_from_slice(&index.to_be_bytes());
    raw[56..].copy_from_slice(&slot.to_be_bytes());
    format!("0x{}", hex::encode(Keccak256::digest(raw)))
}
fn main() -> Result<()> {
    let mut input = String::new();
    io::stdin().read_to_string(&mut input)?;
    let seed: Value = serde_json::from_str(&input)?;
    let mut out = json!({});
    for p in seed["pools"].as_array().unwrap() {
        let mut bitmap = json!({});
        let mut ticks = json!({});
        for index in p["bitmap"].as_object().unwrap().keys() {
            bitmap[key(index.parse()?, 6)] = json!(index.parse::<i64>()?);
        }
        for index in p["ticks"].as_object().unwrap().keys() {
            ticks[key(index.parse()?, 5)] = json!(index.parse::<i64>()?);
        }
        out[p["pool"].as_str().unwrap()] = json!({"bitmap":bitmap,"ticks":ticks});
    }
    println!("{out}");
    Ok(())
}
