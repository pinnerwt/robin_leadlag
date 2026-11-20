//! Fast bounded offline diagnostic decoder, retaining chain inputs and one pool's logs.
#[path = "../src/journal.rs"]
mod journal;
use anyhow::{Result, ensure};
use std::io::{self, Read, Write};
fn main() -> Result<()> {
    let seconds = std::env::args()
        .nth(1)
        .unwrap_or("7201".into())
        .parse::<u64>()?;
    let mut input = io::BufReader::new(io::stdin().lock());
    let mut output = io::BufWriter::new(io::stdout().lock());
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
        if raw.first().is_some_and(|t| *t == 9 || *t == 10) {
            continue;
        }
        let r = journal::parse(&raw)?;
        if r["mono_ns"]
            .as_u64()
            .is_some_and(|t| t > seconds * 1_000_000_000)
        {
            break;
        }
        if r["kind"] == "chain_log" {
            let l = &r["payload"];
            let pool = l["address"].as_str().is_some_and(|a| {
                a.eq_ignore_ascii_case("0xa94e5130a57c48b0b2f266709634a45be7ae8171")
            });
            let feed = l["topics"][1]
                == "0x8dfdc825dd0453e7c80b1c1d32ae910e35d6efe9000000000000000012375400";
            if !pool && !feed {
                continue;
            }
        }
        serde_json::to_writer(&mut output, &r)?;
        writeln!(output)?;
    }
    Ok(())
}
