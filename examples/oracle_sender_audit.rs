#[path = "../src/journal.rs"] mod journal;
#[path = "../src/nitro.rs"] mod nitro;
use anyhow::{Result,ensure};
use alloy_consensus::TxEnvelope;
use alloy_eips::eip2718::Decodable2718;
use serde_json::json;
use std::io::{self,Read};
fn main()->Result<()> {
 let target=std::env::args().nth(1);let mut input=io::BufReader::new(io::stdin().lock());let mut magic=[0;8];input.read_exact(&mut magic)?;ensure!(&magic==journal::MAGIC,"magic");
 loop {let mut len=[0;4];if input.read(&mut len[..1])?==0{break}input.read_exact(&mut len[1..])?;let n=u32::from_le_bytes(len)as usize;journal::valid_size(n)?;let mut raw=vec![0;n];input.read_exact(&mut raw)?;let row=journal::parse(&raw)?;if row["kind"]!="nitro_push"{continue}
 for t in nitro::transactions_without_sender(&row)? {
  if !t["to"].as_str().is_some_and(|a|a.eq_ignore_ascii_case("0xe844701934d9c6085b292e428f41b911cc0b3872")){continue}
  if target.as_ref().is_some_and(|s|t["tx"]!=s.as_str()){continue}
  let raw=hex::decode(t["raw_transaction"].as_str().unwrap().trim_start_matches("0x"))?;let tx=TxEnvelope::decode_2718(&mut raw.as_slice())?;let now=std::time::Instant::now();let sender=tx.recover_signer()?;
  println!("{}",json!({"tx":t["tx"],"from":sender.to_string(),"recovery_ns":now.elapsed().as_nanos(),"data":t["data"]}));if target.is_some(){return Ok(())}
 }
 }Ok(())
}
