use anyhow::{Context, Result};
use serde_json::{Value, json};
use sha3::{Digest, Keccak256};
use std::io::{self, Read};
fn main() -> Result<()> {
    let mut input = String::new();
    io::stdin().read_to_string(&mut input)?;
    let v: Value = serde_json::from_str(&input)?;
    let slot = v["slot"].as_u64().context("slot")?;
    let mut keys = Vec::new();
    for a in v["addresses"].as_array().context("addresses")? {
        let bytes = hex::decode(a.as_str().context("address")?.trim_start_matches("0x"))?;
        anyhow::ensure!(bytes.len() == 20, "address length");
        let mut raw = [0u8; 64];
        raw[12..32].copy_from_slice(&bytes);
        raw[56..].copy_from_slice(&slot.to_be_bytes());
        let outer = Keccak256::digest(raw);
        if let Some(indices) = v.get("nested_indices") {
            for index in indices.as_array().context("nested_indices array")? {
                let index = index.as_u64().context("nested index u64")?;
                let mut nested = [0u8; 64];
                nested[24..32].copy_from_slice(&index.to_be_bytes());
                nested[32..].copy_from_slice(&outer);
                keys.push(format!("0x{}", hex::encode(Keccak256::digest(nested))));
            }
        } else {
            keys.push(format!("0x{}", hex::encode(outer)));
        }
    }
    println!("{}", json!(keys));
    Ok(())
}
