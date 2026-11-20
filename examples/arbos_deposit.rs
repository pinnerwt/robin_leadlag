#[path = "../src/arbos_deposit.rs"]
mod arbos_deposit;
#[path = "../src/arbos_units.rs"]
mod arbos_units;
#[path = "../src/local_evm.rs"]
mod local_evm;
use anyhow::{Context, Result};
use serde_json::{Value, json};
fn main() -> Result<()> {
    let f: Value =
        serde_json::from_slice(&std::fs::read(std::env::args().nth(1).context("fixture")?)?)?;
    let db = local_evm::State::load(&f["accounts"])?;
    let (next, filtered, to) = arbos_deposit::apply(&db, &f["message"])?;
    let mut balances = json!({});
    for (a, v) in &next.accounts {
        if db.accounts.get(a).map(|x| x.balance) != Some(v.balance) {
            balances[a.to_string().to_lowercase()] = json!(format!("{:#x}", v.balance));
        }
    }
    println!(
        "{}",
        json!({"balances":balances,"filtered":filtered,"recipient":to.to_string().to_lowercase(),"gas_used":0})
    );
    Ok(())
}
