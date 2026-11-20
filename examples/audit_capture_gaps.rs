#[path = "../src/journal.rs"]
mod journal;
use anyhow::{Result, ensure};
use std::io::{self, Read};
fn main() -> Result<()> {
    let mut i = io::BufReader::new(io::stdin().lock());
    let mut m = [0; 8];
    i.read_exact(&mut m)?;
    ensure!(&m == journal::MAGIC, "magic");
    loop {
        let mut n = [0; 4];
        if i.read(&mut n[..1])? == 0 {
            break;
        }
        if i.read_exact(&mut n[1..]).is_err() {
            break;
        }
        let n = u32::from_le_bytes(n) as usize;
        journal::valid_size(n)?;
        let mut b = vec![0; n];
        if i.read_exact(&mut b).is_err() {
            break;
        }
        if b.first().is_some_and(|t| *t == 9 || *t == 10) {
            continue;
        }
        let r = journal::parse(&b)?;
        if matches!(
            r["kind"].as_str(),
            Some("gap" | "connected" | "session" | "capture_end")
        ) {
            println!("{r}");
        }
    }
    Ok(())
}
