#[path="../src/journal.rs"]mod journal;
use anyhow::{Result,ensure};
use std::io::Read;
fn main()->Result<()>{let mut f=std::io::BufReader::new(std::io::stdin().lock());let mut magic=[0;8];f.read_exact(&mut magic)?;ensure!(&magic==journal::MAGIC,"magic");let mut prev=None;let mut count=0;
loop{let mut l=[0;4];if f.read(&mut l[..1])?==0{break}f.read_exact(&mut l[1..])?;let n=u32::from_le_bytes(l)as usize;journal::valid_size(n)?;let mut b=vec![0;n];f.read_exact(&mut b)?;let r=journal::parse(&b)?;let t=r["mono_ns"].as_u64().unwrap_or(0);if t>6_465_000_000_000{break}
if t>6_462_000_000_000 && r["kind"]=="nitro_push" {if let Some(ms)=r["payload"]["messages"].as_array(){for m in ms{println!("{}",serde_json::json!({"kind":"nitro_hash","mono_ns":t,"sequence":m["sequenceNumber"],"hash":m["blockHash"]}));}}}
if r["kind"]=="head"{if t>6_462_000_000_000{println!("{}",serde_json::json!({"kind":"head_detail","mono_ns":t,"payload":r["payload"]}));}let h=&r["payload"];let num=u64::from_str_radix(h["number"].as_str().unwrap().trim_start_matches("0x"),16)?;let hash=h["hash"].as_str().unwrap().to_string();let parent=h["parentHash"].as_str().unwrap();if let Some((pn,ph))=&prev{if num!=pn+1||parent!=ph{println!("{}",serde_json::json!({"mono_ns":t,"recv_ns":r["recv_ns"],"number":num,"prev_number":pn,"hash":hash,"parent":parent,"prev_hash":ph,"epoch":r["epoch"]}));count+=1;}}prev=Some((num,hash));}
if r["kind"]=="checkpoint_recovery"&&t>6_450_000_000_000{println!("{}",r);}
}eprintln!("head discontinuities {}",count);Ok(())}
