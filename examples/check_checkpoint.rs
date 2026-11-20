#[path = "../src/local_evm.rs"]
mod local_evm;
use anyhow::Result;
use serde_json::{Value, json};
fn main() -> Result<()> {
    let path = std::env::args().nth(1).expect("checkpoint path");
    let seed: Value = serde_json::from_slice(&std::fs::read(path)?)?;
    let db = local_evm::State::load(&seed["accounts"])?;
    let mut results = Vec::new();
    for pool in seed["pools"].as_array().unwrap() {
        let mut calls = vec![
            json!({"side":"provider","call":{"to":pool["provider"],"data":"0x171755b1"},"expected":pool["quote_trace"]["output"]}),
        ];
        calls.extend(pool["quote_checks"].as_array().unwrap().iter().cloned());
        for call in calls {
            let start = std::time::Instant::now();
            let result = db.clone().run(&seed["anchor"], &call["call"], false);
            let row = match result {
                Ok(result) => {
                    let output = local_evm::output(&result);
                    json!({"pool":pool["pool"],"pair":pool["pair"],"side":call["side"],"size_tokens":call["size_tokens"],"match":output.as_deref()==call["expected"].as_str(),"success":result.is_success(),"output":output,"expected":call["expected"],"elapsed_us":start.elapsed().as_micros() as u64})
                }
                Err(e) => {
                    json!({"pool":pool["pool"],"pair":pool["pair"],"side":call["side"],"size_tokens":call["size_tokens"],"error":e.to_string()})
                }
            };
            results.push(row);
        }
    }
    println!("{}", serde_json::to_string_pretty(&results)?);
    Ok(())
}
