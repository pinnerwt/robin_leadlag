//! Startup-only mapping hypotheses from actual pre-anchor storage reads.
use anyhow::{Context, Result};
use serde_json::{Value, json};
use sha3::{Digest, Keccak256};
use std::{
    collections::{BTreeMap, HashSet},
    io::{self, Read},
};
fn main() -> Result<()> {
    let mut input = String::new();
    io::stdin().read_to_string(&mut input)?;
    let rows: Vec<Value> = serde_json::from_str(&input)?;
    let mut profiles = BTreeMap::new();
    for r in rows {
        let router = r["router"].as_str().context("router")?;
        let caller = hex::decode(
            r["caller"]
                .as_str()
                .context("caller")?
                .trim_start_matches("0x"),
        )?;
        anyhow::ensure!(caller.len() == 20, "caller length");
        let reads: HashSet<Vec<u8>> = r["keys"]
            .as_array()
            .context("keys")?
            .iter()
            .map(|v| {
                let raw = v.as_str().unwrap().trim_start_matches("0x");
                hex::decode(format!("{raw:0>64}"))
            })
            .collect::<std::result::Result<_, _>>()?;
        for slot in 0..32u64 {
            let mut raw = [0u8; 64];
            raw[12..32].copy_from_slice(&caller);
            raw[56..].copy_from_slice(&slot.to_be_bytes());
            if !reads.contains(Keccak256::digest(raw).as_slice()) {
                continue;
            }
            let code = hex::decode(r["code"].as_str().context("code")?.trim_start_matches("0x"))?;
            let hash = format!("0x{}", hex::encode(Keccak256::digest(code)));
            profiles.insert((router.to_owned(),slot,hash.clone()),json!({"router":router,"mapping_slot":slot,
    "implementation_code_hash":hash,"evidence":"pre-anchor root-caller key matched a real storage read; semantics not inferred"}));
        }
    }
    println!("{}", json!(profiles.into_values().collect::<Vec<_>>()));
    Ok(())
}
