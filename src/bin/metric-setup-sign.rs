//! Cold setup signer. Credentials stay on the host; never participates in signals.
#[path="../trading/config.rs"] mod config;
use anyhow::{Result,Context,ensure};
use robin_leadlag::execution::codec::{self,Transaction};
use serde_json::{Value,json};
use std::io::Read;
fn main()->Result<()> {
 let path=std::env::args().nth(1).context("configuration required")?;
 let c=config::Config::load(std::path::Path::new(&path))?;
 ensure!(c.mode==config::Mode::Standby,"setup requires standby");
 let credentials=c.credentials()?;let key=credentials.key.context("key missing")?;
 let owner=codec::wallet(&key);
 let mut input=String::new();std::io::stdin().read_to_string(&mut input)?;
 let r:Value=serde_json::from_str(&input)?;
 if r["action"]=="hash" {
  let bytes=hex::decode(r["data"].as_str().context("data")?.trim_start_matches("0x"))?;
  println!("{}",json!({"hash":format!("0x{}",hex::encode(codec::hash(&bytes)))}));return Ok(());
 }
 let nonce=r["nonce"].as_u64().context("nonce")?;
 let gas=r["gas"].as_u64().context("gas")?;
 ensure!(gas>0 && gas<=2_000_000,"setup gas cap");
 let fee=r["max_fee"].as_str().context("max_fee")?.parse::<u128>()?;
 ensure!(fee>0 && fee<=1_000_000_000,"setup fee cap");
 let action=r["action"].as_str().context("action")?;
 let mut expected_runtime=None;
 let (to,data)=match action {
  "deploy"=>{
   let artifact:Value=serde_json::from_str(include_str!("../../contracts/metric-executor/out/MetricInventoryExecutor.sol/MetricInventoryExecutor.json"))?;
   let mut code=hex::decode(artifact["bytecode"]["object"].as_str().context("creation bytecode")?.trim_start_matches("0x"))?;
   code.extend(codec::address(owner));
   let mut runtime=hex::decode(artifact["deployedBytecode"]["object"].as_str().context("runtime")?.trim_start_matches("0x"))?;
   for refs in artifact["deployedBytecode"]["immutableReferences"].as_object().context("immutable references")?.values() {
    for item in refs.as_array().context("references")? {
     let start=item["start"].as_u64().context("start")? as usize;
     ensure!(item["length"]==32,"immutable length");runtime[start..start+32].copy_from_slice(&codec::address(owner));
    }
   }
   expected_runtime=Some(format!("0x{}",hex::encode(runtime)));([0;20],code)
  },
  "configure"=>{
   let to=config::address(r["executor"].as_str().context("executor")?)?;
   let hash=hex::decode(r["pool_codehash"].as_str().context("pool_codehash")?.trim_start_matches("0x"))?;
   ensure!(hash.len()==32,"codehash");
   let mut args=codec::address(config::address(config::POOL)?);
   args.extend(codec::address(config::address(config::BASE)?));args.extend(codec::address(config::address(config::QUOTE)?));args.extend(codec::word(1));args.extend(hash);
   (to,codec::call("configurePool(address,address,address,bool,bytes32)",args))
  },
  "approve_base"|"approve_quote"=>{
   let spender=config::address(r["executor"].as_str().context("executor")?)?;
   ensure!(spender!=[0;20],"zero spender");
   let base=action=="approve_base";
   let mut args=codec::address(spender);
   // Finite approvals. Replenishment is explicit cold maintenance, never hot path.
   args.extend(codec::word(if base {116_000_000_000_000_000}else{1_000_000_000}));
   (config::address(if base {config::BASE}else{config::QUOTE})?,codec::call("approve(address,uint256)",args))
  },
  _=>anyhow::bail!("unsupported setup action")
 };
 let tx=Transaction{nonce,priority_fee:0,max_fee:fee,gas,to,value:0,data:data.clone()};
 let raw=if action=="deploy"{tx.sign_creation(&key)?}else{tx.sign(&key)?};
 println!("{}",json!({"wallet":format!("0x{}",hex::encode(owner)),"raw":format!("0x{}",hex::encode(&raw)),"hash":format!("0x{}",hex::encode(codec::hash(&raw))),"expected_runtime":expected_runtime,"data":format!("0x{}",hex::encode(data)),"to":if action=="deploy"{None}else{Some(format!("0x{}",hex::encode(to)))}}));
 Ok(())
}
