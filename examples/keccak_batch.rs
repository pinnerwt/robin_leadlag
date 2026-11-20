use anyhow::Result;
use sha3::{Digest, Keccak256};
use std::io::{self, Read};
fn main() -> Result<()> {
    let mut s = String::new();
    io::stdin().read_to_string(&mut s)?;
    let inputs: Vec<String> = serde_json::from_str(&s)?;
    let mut hashes = Vec::new();
    for s in inputs {
        hashes.push(hex::encode(Keccak256::digest(hex::decode(
            s.trim_start_matches("0x"),
        )?)));
    }
    println!("{}", serde_json::to_string(&hashes)?);
    Ok(())
}
