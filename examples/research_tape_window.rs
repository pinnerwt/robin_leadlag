//! Offline fixed-prefix trimming only. Never open or modify an active recorder file.
#[path="../src/journal.rs"] mod journal;
use anyhow::{Result,Context,ensure};
use std::io::{Read,Write};
fn main()->Result<()>{
 let a:Vec<_>=std::env::args().collect();let field=a.get(1).context("clock field")?;ensure!(field=="recv_ns"||field=="mono_ns","clock");let start:u64=a.get(2).context("start")?.parse()?;let end:u64=a.get(3).context("end")?.parse()?;ensure!(start<end,"window");
 let mut input=std::io::BufReader::new(std::io::stdin().lock());let mut output=std::io::BufWriter::new(std::io::stdout().lock());let mut magic=[0;8];input.read_exact(&mut magic)?;ensure!(&magic==journal::MAGIC,"magic");output.write_all(&magic)?;let(mut kept,mut skipped,mut partial)=(0u64,0u64,false);
 loop{let mut len=[0;4];if input.read(&mut len[..1])?==0{break}if input.read_exact(&mut len[1..]).is_err(){partial=true;break}let n=u32::from_le_bytes(len)as usize;journal::valid_size(n)?;let mut raw=vec![0;n];if input.read_exact(&mut raw).is_err(){partial=true;break}let r=journal::parse(&raw)?;let kind=r["kind"].as_str().unwrap_or("");let t=r[field].as_u64();
 // Keep connection/session metadata so exchange freshness and gaps can be reconstructed.
 let metadata=matches!(kind,"session"|"equity_session"|"connected"|"ready"|"gap"|"rotation_complete"|"subscribed");
 if t.is_some_and(|t|t>end){skipped+=1;continue}
 if metadata||t.is_some_and(|t|t>=start&&t<=end){output.write_all(&len)?;output.write_all(&raw)?;kept+=1}else{skipped+=1}
 }output.flush()?;eprintln!("{}",serde_json::json!({"kept":kept,"skipped":skipped,"partial_tail_discarded":partial,"clock":field,"start":start,"end":end}));Ok(())
}
