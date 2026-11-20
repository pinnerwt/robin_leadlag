//! Local state projection: accepted logs advance the base, pending calldata
//! overlays only the quote copy. No network or signing in this process.
#[path = "../../examples/spcx_state_worker.rs"]
mod worker;
#[path = "../nitro.rs"]
mod nitro;
#[path="../pyth.rs"]
mod pyth;
use worker::model::{local_evm, pool, pool_reduce, scoped_reconcile};
use anyhow::{Context, Result, ensure};
use serde_json::{Value,json};
use std::io::{self,BufRead,Write};
fn main()->Result<()> {
    let mut state:Option<local_evm::State>=None;
    let mut pool=Value::Null;
    let mut version=0u64;
    let mut output=io::stdout().lock();
    for line in io::stdin().lock().lines() {
        let r:Value=serde_json::from_str(&line?)?;
        let result=(||->Result<Value>{
            match r["kind"].as_str().context("kind")? {
                "pyth"=>Ok(json!({"updates":pyth::decode_all(r["data"].as_str().context("data")?)?})),
                "audit"=>{
                    let mut db=state.as_ref().context("uninitialized")?.clone();
                    let prices=worker::model::quote(&mut db,&r["header"],&pool)?;
                    let mut quotes=vec![];
                    for raw in r["sizes"].as_array().context("sizes")? {
                        let q=worker::handle(&mut db,&pool,&json!({"kind":"quote","header":r["header"],"raw_base":raw}))?;
                        quotes.push(json!({"raw_base":raw,"quote":q}));
                    }
                    Ok(json!({"prices":format!("0x{}",hex::encode(prices)),"quotes":quotes}))
                }
                "decode"=>Ok(json!({"transactions":nitro::transactions_without_sender(&r["row"])?})),
                "initialize"=>{
                    let seed=&r["seed"];
                    ensure!(seed["pools"].as_array().context("pools")?.len()==1,"one pool required");
                    ensure!(seed["local_parity"]["passed"]==true && seed["anchor_verified"]==true,"unverified checkpoint");
                    state=Some(local_evm::State::load(&seed["accounts"])?);
                    pool=seed["pools"][0].clone(); version=0;
                    Ok(json!({"version":version}))
                }
                "confirmed"=>{
                    let db=state.as_mut().context("uninitialized")?;
                    // Failed updates must never leave partial writes behind.
                    let mut candidate=db.clone();
                    let value=worker::handle(&mut candidate,&pool,&r["request"])?;
                    *db=candidate;version+=1;
                    Ok(json!({"version":version,"update":value}))
                }
                "quote"=>{
                    let mut db=state.as_ref().context("uninitialized")?.clone();
                    for update in r["pending"].as_array().context("pending updates")? {
                        // v3_price carries a calldata-predicted spot price; it only ever touches this copy.
                        ensure!(update["kind"]=="aux_oracle" || update["kind"]=="v3_price","only oracle and V3 price overlays allowed");
                        worker::handle(&mut db,&pool,update)?;
                    }
                    let value=worker::handle(&mut db,&pool,&json!({"kind":"quote","header":r["header"],"raw_base":r["raw_base"]}))?;
                    Ok(json!({"version":version,"quote":value}))
                }
                _=>anyhow::bail!("unknown command"),
            }
        })();
        let response=match result {Ok(v)=>json!({"result":v}),Err(e)=>json!({"error":e.to_string()})};
        writeln!(output,"{response}")?;output.flush()?;
    }
    Ok(())
}
