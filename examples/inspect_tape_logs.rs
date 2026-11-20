//! Offline log inspection for a transaction or emitting address.
#[path = "../src/journal.rs"]
mod journal;
use anyhow::{Result, ensure};
use std::io::{self, Read};
fn main() -> Result<()> {
    let targets: Vec<String> = std::env::args().skip(1).map(|s| s.to_lowercase()).collect();
    let mut input = io::BufReader::new(io::stdin().lock());
    let mut magic = [0; 8];
    input.read_exact(&mut magic)?;
    ensure!(&magic == journal::MAGIC, "magic");
    loop {
        let mut len = [0; 4];
        if input.read(&mut len[..1])? == 0 {
            break;
        }
        input.read_exact(&mut len[1..])?;
        let n = u32::from_le_bytes(len) as usize;
        journal::valid_size(n)?;
        let mut raw = vec![0; n];
        input.read_exact(&mut raw)?;
        let row = journal::parse(&raw)?;
        if row["kind"] == "chain_log"
            && ["address", "transactionHash"].iter().any(|k| {
                row["payload"][k]
                    .as_str()
                    .is_some_and(|x| targets.contains(&x.to_lowercase()))
            })
        {
            println!("{row}");
        }
    }
    Ok(())
}
