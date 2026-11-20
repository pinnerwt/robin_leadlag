//! Pack JSONL research/checkpoint records into the existing versioned binary tape.
#[path = "../src/journal.rs"]
mod journal;
use anyhow::{Result, ensure};
use std::io::{self, BufRead, Write};
fn main() -> Result<()> {
    let mut out = io::BufWriter::new(io::stdout().lock());
    out.write_all(journal::MAGIC)?;
    for line in io::stdin().lock().lines() {
        let v: serde_json::Value = serde_json::from_str(&line?)?;
        let frame = journal::frame(&v)?;
        ensure!(
            frame.len() <= 8 * 1024 * 1024 + 4,
            "record exceeds replay frame limit"
        );
        out.write_all(&frame)?;
    }
    out.flush()?;
    Ok(())
}
