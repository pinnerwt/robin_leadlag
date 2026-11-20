//! Offline parity check: omitting sender recovery must not change decoded content.
#[path = "../src/nitro.rs"]
mod nitro;
use anyhow::{Result, ensure};
use serde_json::Value;
use std::io::{self, BufRead};
fn main() -> Result<()> {
    let mut count = 0;
    for l in io::stdin().lock().lines() {
        let r: Value = serde_json::from_str(&l?)?;
        if r["kind"] != "nitro_push" {
            continue;
        }
        let Ok(a) = nitro::transactions(&r) else {
            continue;
        };
        let b = nitro::transactions_without_sender(&r)?;
        ensure!(a.len() == b.len(), "length");
        for (mut x, mut y) in a.into_iter().zip(b) {
            x.as_object_mut().unwrap().remove("from");
            y.as_object_mut().unwrap().remove("from");
            ensure!(x == y, "decoded transaction differs");
            count += 1;
        }
        if count >= 100 {
            break;
        }
    }
    ensure!(count >= 100, "insufficient fixture");
    println!("{count} transactions identical except sender");
    Ok(())
}
