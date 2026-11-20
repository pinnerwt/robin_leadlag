//! Durable, fail-closed trading circuit. Configuration changes never erase trips.
use anyhow::{Result,Context};
use serde::{Serialize,Deserialize};
use std::{path::{Path,PathBuf},fs::{self,OpenOptions},io::Write};
#[derive(Clone,Serialize,Deserialize)]
#[serde(default,deny_unknown_fields)]
pub struct Limits {pub window_seconds:u64,pub max_orders:usize,pub max_reverts:usize}
impl Default for Limits {fn default()->Self {Self{window_seconds:60,max_orders:12,max_reverts:3}}}
#[derive(Default,Serialize,Deserialize)]
struct State {orders:Vec<u64>,reverts:Vec<u64>,last_receipt:Option<String>,halt:Option<String>}
pub struct Circuit {path:PathBuf,state:State,limits:Limits}
impl Circuit {
 pub fn open(root:&Path,limits:Limits)->Result<Self>{
  fs::create_dir_all(root)?;let path=root.join("circuit.json");
  let state=if path.exists(){serde_json::from_slice(&fs::read(&path)?)?}else{State::default()};
  Ok(Self{path,state,limits})
 }
 pub fn halt(&self)->Option<&str>{self.state.halt.as_deref()}
 fn prune(&mut self,now:u64){let cutoff=now.saturating_sub(self.limits.window_seconds*1_000_000_000);self.state.orders.retain(|t|*t>=cutoff);self.state.reverts.retain(|t|*t>=cutoff);}
 fn save(&mut self)->Result<()>{
  let result=(||->Result<()>{let tmp=self.path.with_extension("tmp");let mut f=OpenOptions::new().write(true).create(true).truncate(true).open(&tmp)?;f.write_all(&serde_json::to_vec(&self.state)?)?;f.sync_all()?;fs::rename(tmp,&self.path)?;std::fs::File::open(self.path.parent().context("parent")?)?.sync_all()?;Ok(())})();
  if result.is_err(){self.state.halt=Some("circuit persistence failure".into());}result
 }
 pub fn before_order(&mut self,now:u64)->Result<bool>{
  self.prune(now);if self.halt().is_some(){return Ok(false)}
  if self.state.orders.len()>=self.limits.max_orders {self.state.halt=Some("order rate limit".into());self.save()?;return Ok(false)}
  self.state.orders.push(now);self.save()?;Ok(true)
 }
 pub fn receipt(&mut self,hash:String,success:bool,now:u64)->Result<()>{
  if self.state.last_receipt.as_ref()==Some(&hash){return Ok(())}
  self.prune(now);self.state.last_receipt=Some(hash);
  if !success {self.state.reverts.push(now);if self.state.reverts.len()>=self.limits.max_reverts{self.state.halt=Some("revert rate limit".into());}}
  self.save()
 }
}
#[cfg(test)] mod tests {
 use super::*;
 #[test] fn trips_survive_restart_and_receipts_are_idempotent(){
  let root=std::env::temp_dir().join(format!("metric-circuit-{}",std::process::id()));let _=fs::remove_dir_all(&root);
  let mut c=Circuit::open(&root,Limits::default()).unwrap();
  for i in 0..3{c.receipt(i.to_string(),false,10).unwrap();c.receipt(i.to_string(),false,10).unwrap();}
  assert!(c.halt().is_some());drop(c);let mut c=Circuit::open(&root,Limits::default()).unwrap();assert!(!c.before_order(999_000_000_000).unwrap());fs::remove_dir_all(root).unwrap();
 }
 #[test] fn order_budget_does_not_allow_thirteenth(){
  let root=std::env::temp_dir().join(format!("metric-rate-{}",std::process::id()));let _=fs::remove_dir_all(&root);let mut c=Circuit::open(&root,Limits::default()).unwrap();for _ in 0..12{assert!(c.before_order(1).unwrap())}assert!(!c.before_order(1).unwrap());fs::remove_dir_all(root).unwrap();
 }
}
