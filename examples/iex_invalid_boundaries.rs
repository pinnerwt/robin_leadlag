//! Offline invalid BBO boundaries for a complete-frame IEX tape.
#[path="../src/journal.rs"] mod journal;
use anyhow::{Result,ensure,Context};
use std::{io::{Read,Write},collections::HashMap};
fn main()->Result<()>{
 let mut input=std::io::BufReader::new(std::io::stdin().lock());let mut out=std::io::BufWriter::new(std::io::stdout().lock());let mut magic=[0;8];input.read_exact(&mut magic)?;ensure!(&magic==journal::MAGIC,"magic");let mut latest:HashMap<String,u64>=HashMap::new();
 loop {let mut len=[0;4];if input.read(&mut len[..1])?==0{break}input.read_exact(&mut len[1..])?;let n=u32::from_le_bytes(len)as usize;journal::valid_size(n)?;let mut raw=vec![0;n];input.read_exact(&mut raw)?;let r=journal::parse(&raw)?;
 match r["kind"].as_str().unwrap_or("") {
 "iex_gap"|"iex_stopped"=>{writeln!(out,"{}",r)?;},
 "iex_bbo"=>{let s=r["symbol"].as_str().unwrap();let stamp=r["exchange_ns"].as_u64().ok_or_else(||anyhow::anyhow!("missing stamp: {}",r))?;if stamp<*latest.get(s).unwrap_or(&0){continue}latest.insert(s.to_string(),stamp);let b=r["bid"].as_str().map(str::parse::<f64>).transpose()?.or_else(||r["bid"].as_f64()).context("bid")?;let a=r["ask"].as_str().map(str::parse::<f64>).transpose()?.or_else(||r["ask"].as_f64()).context("ask")?;if !(b.is_finite()&&a.is_finite()&&b>0.&&a>=b){writeln!(out,"{}",serde_json::json!({"symbol":s,"recv_ns":r["recv_ns"],"invalid":true}))?;}},_=>{}
 }}out.flush()?;Ok(())
}
