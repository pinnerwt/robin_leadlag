#[path = "../src/local_evm.rs"]
mod local_evm;
use anyhow::Result;
use serde_json::{Value, json};
use std::io::{self, BufRead};
fn main() -> Result<()> {
    let seed: Value = serde_json::from_slice(&std::fs::read(
        std::env::args().nth(1).expect("checkpoint"),
    )?)?;
    let db = local_evm::State::load(&seed["accounts"])?;
    for line in io::stdin().lock().lines() {
        let call: Value = serde_json::from_str(&line?)?;
        let mut candidate = db.clone();
        candidate.trace_reads = call["trace"].as_bool().unwrap_or(false);
        let result = candidate.run(&seed["anchor"], &call, false);
        let row = match result {
            Ok(r) => {
                json!({"tx":call["tx"],"success":r.is_success(),"output":local_evm::output(&r)})
            }
            Err(e) => json!({"tx":call["tx"],"error":e.to_string()}),
        };
        println!("{row}");
    }
    Ok(())
}
