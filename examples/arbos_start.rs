//! Offline complete guarded StartBlock comparison against a diagnostic witness.
#[path = "../src/arbos_block.rs"]
mod arbos_block;
#[path = "../src/arbos_units.rs"]
mod arbos_units;
#[path = "../src/local_evm.rs"]
mod local_evm;
use anyhow::{Context, Result};
use revm::primitives::B256;
use serde_json::{Value, json};
use std::str::FromStr;
fn main() -> Result<()> {
    let f: Value =
        serde_json::from_slice(&std::fs::read(std::env::args().nth(1).context("fixture")?)?)?;
    let db = local_evm::State::load(&f["system_accounts"])?;
    let n =
        |v: &Value| u64::from_str_radix(v.as_str().unwrap().trim_start_matches("0x"), 16).unwrap();
    let (fee, writes) = arbos_block::start(
        &db,
        n(&f["header"]["number"]),
        n(&f["header"]["timestamp"]),
        n(&f["parent"]["timestamp"]),
        n(&f["header"]["l1BlockNumber"]),
        B256::from_str(f["header"]["parentHash"].as_str().unwrap())?,
    )?;
    let mut out = json!({});
    for ((a, k), v) in writes {
        out[a.to_string().to_lowercase()][format!("{k:#x}")] = json!(format!("{v:#x}"));
    }
    println!(
        "{}",
        json!({"current_base_fee":format!("{fee:#x}"),"writes":out,"scope":"ArbOS61 empty retryables single-gas no due upgrade"})
    );
    Ok(())
}
