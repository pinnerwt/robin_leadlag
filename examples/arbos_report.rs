#[path = "../src/arbos_report.rs"]
mod arbos_report;
#[path = "../src/arbos_units.rs"]
mod arbos_units;
#[path = "../src/local_evm.rs"]
mod local_evm;
use anyhow::{Context, Result};
use serde_json::{Value, json};
fn main() -> Result<()> {
    let path = std::env::args().nth(1).context("fixture path")?;
    let f: Value = serde_json::from_slice(&std::fs::read(path)?)?;
    let db = local_evm::State::load(&f["pre"][1]["result"])?;
    let time = u64::from_str_radix(
        f["header"]["timestamp"]
            .as_str()
            .context("header time")?
            .trim_start_matches("0x"),
        16,
    )?;
    let after = arbos_report::apply(&db, &f["message"], time)?;
    let mut writes = json!({});
    let mut balances = json!({});
    for ((a, k), v) in &after.slots {
        if db.slots.get(&(*a, *k)) != Some(v) {
            writes[a.to_string().to_lowercase()][format!("{k:#x}")] = json!(format!("{v:#x}"));
        }
    }
    for (a, v) in &after.accounts {
        if db.accounts.get(a).map(|x| x.balance) != Some(v.balance) {
            balances[a.to_string().to_lowercase()] = json!(format!("{:#x}", v.balance));
        }
    }
    println!("{}", json!({"writes":writes,"balances":balances}));
    Ok(())
}
