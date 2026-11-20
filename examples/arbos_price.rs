//! Offline StartBlock pricing-component parity. No networking.
#[path = "../src/arbos_units.rs"]
mod arbos_units;
#[path = "../src/local_evm.rs"]
mod local_evm;
use anyhow::{Context, Result};
use serde_json::{Value, json};
fn main() -> Result<()> {
    let f: Value =
        serde_json::from_slice(&std::fs::read(std::env::args().nth(1).context("fixture")?)?)?;
    let db = local_evm::State::load(&f["system_accounts"])?;
    let time =
        |v: &Value| u64::from_str_radix(v.as_str().unwrap().trim_start_matches("0x"), 16).unwrap();
    let (fee, writes) = arbos_units::update_pricing(
        &db,
        time(&f["header"]["timestamp"]) - time(&f["parent"]["timestamp"]),
    )?;
    let changes: serde_json::Map<String, Value> = writes
        .iter()
        .map(|(k, v)| (format!("{k:#x}"), json!(format!("{v:#x}"))))
        .collect();
    println!(
        "{}",
        json!({"current_base_fee":format!("{fee:#x}"),"pricing_writes":changes,"complete_start_block":false})
    );
    Ok(())
}
