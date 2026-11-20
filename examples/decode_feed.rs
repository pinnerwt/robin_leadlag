#[path = "../src/nitro.rs"]
mod nitro;
use anyhow::{Context, Result};
use serde_json::Value;
use std::io::{self, BufRead};
fn main() -> Result<()> {
    let optimistic = std::env::args().any(|x| x == "--optimistic");
    let passthrough = std::env::args().any(|x| x == "--with-raw");
    for line in io::stdin().lock().lines() {
        let row: Value = serde_json::from_str(&line?)?;
        if row["kind"] == "nitro_push" {
            // Feed confirmations acknowledge earlier sequence numbers; they do
            // not contain transactions or advance the execution state.
            if row["payload"]["messages"].is_null()
                && row["payload"]["confirmedSequenceNumberMessage"]["sequenceNumber"].is_u64()
                && row["payload"].as_object().is_some_and(|p| {
                    p.keys()
                        .all(|k| k == "version" || k == "confirmedSequenceNumberMessage")
                })
            {
                if passthrough {
                    println!(
                        "{}",
                        serde_json::json!({"kind":"feed_confirmation",
                        "sequence":row["payload"]["confirmedSequenceNumberMessage"]["sequenceNumber"],
                        "recv_ns":row["recv_ns"],"mono_ns":row["mono_ns"]})
                    );
                }
                continue;
            }
            for item in row["payload"]["messages"]
                .as_array()
                .context("Nitro messages array")?
            {
                let mut single = row.clone();
                single["payload"]["messages"] = serde_json::json!([item]);
                // Decode first: never publish a block marker for an undecodable message.
                match nitro::transactions(&single) {
                    Ok(txs) => {
                        if passthrough {
                            println!(
                                "{}",
                                serde_json::json!({"kind":"feed_block","block_hash":item["blockHash"],"sequence":item["sequenceNumber"],"timestamp":item["message"]["message"]["header"]["timestamp"],"l1_block":item["message"]["message"]["header"]["blockNumber"],"transaction_count":txs.len(),"mono_ns":row["mono_ns"],"recv_ns":row["recv_ns"]})
                            );
                        }
                        for tx in txs {
                            println!("{tx}");
                        }
                    }
                    Err(e) => {
                        if optimistic {
                            println!(
                                "{}",
                                serde_json::json!({"kind":"gap", "stream":"nitro", "reason":e.to_string(), "mono_ns":row["mono_ns"], "recv_ns":row["recv_ns"]})
                            );
                            println!(
                                "{}",
                                serde_json::json!({"kind":"undecoded_nitro", "event":single})
                            );
                        } else if passthrough {
                            return Err(e);
                        }
                        eprintln!("decode unsupported: {e}");
                    }
                }
            }
        } else if passthrough {
            println!("{row}");
        }
    }
    Ok(())
}
