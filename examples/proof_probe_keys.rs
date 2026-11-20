//! Find storage slot preimages reaching explicitly missing secure-trie prefixes.
use anyhow::{Context, Result, ensure};
use serde_json::{Value, json};
use sha3::{Digest, Keccak256};
use std::{
    collections::BTreeSet,
    io::{self, Read},
};
fn main() -> Result<()> {
    let mut input = String::new();
    io::stdin().read_to_string(&mut input)?;
    let v: Value = serde_json::from_str(&input)?;
    let mut prefixes = BTreeSet::new();
    for p in v["prefixes"].as_array().context("prefixes")? {
        let p = p.as_str().context("prefix")?;
        ensure!(
            p.len() <= 64 && p.bytes().all(|c| c.is_ascii_hexdigit()),
            "invalid prefix"
        );
        prefixes.insert(p.to_lowercase());
    }
    let mut n = v["start"].as_u64().unwrap_or(0);
    let limit = v["limit"].as_u64().unwrap_or(10_000_000);
    let mut found = Vec::new();
    for _ in 0..limit {
        if prefixes.is_empty() {
            break;
        }
        let mut word = [0u8; 32];
        word[24..].copy_from_slice(&n.to_be_bytes());
        let hash = hex::encode(Keccak256::digest(word));
        let matches: Vec<_> = prefixes
            .iter()
            .filter(|p| hash.starts_with(p.as_str()))
            .cloned()
            .collect();
        for p in matches {
            prefixes.remove(&p);
            found.push(json!({"prefix":p,"key":format!("0x{}",hex::encode(word))}));
        }
        n = n.checked_add(1).context("probe counter overflow")?;
    }
    println!(
        "{}",
        json!({"found":found,"unmatched":prefixes,"next_counter":n})
    );
    Ok(())
}
