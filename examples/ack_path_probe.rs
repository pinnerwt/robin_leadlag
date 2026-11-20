//! Read-only transport probes plus deliberately invalid, unsigned transaction bytes.
//! These measure route/server response time, not acceptance of a valid transaction.
use anyhow::Result;
use futures_util::{SinkExt,StreamExt};
use serde_json::{json,Value};
use std::time::{Duration,Instant};
#[tokio::main]
async fn main()->Result<()> {
 let urls=["https://sequencer.mainnet.chain.robinhood.com","https://rpc.mainnet.chain.robinhood.com","https://rpc-robinhood.blockmachine.io"];
 let mut rows=vec![];
 for url in urls {
  let client=robin_leadlag::execution::transport::client(Duration::from_secs(10))?;
  for (method,params) in [("eth_chainId",json!([])),("eth_sendRawTransaction",json!(["0x00"]))] {
   for sample in 0..10 {
    let start=Instant::now();
    let result=client.post(url).json(&json!({"jsonrpc":"2.0","id":1,"method":method,"params":params})).send().await;
    let row=match result {
     Ok(response)=>{let status=response.status().as_u16();let version=format!("{:?}",response.version());let body=response.text().await.unwrap_or_default();json!({"transport":"http","url":url,"method":method,"sample":sample,"elapsed_ms":start.elapsed().as_secs_f64()*1000.,"status":status,"version":version,"body":body})},
     Err(e)=>json!({"url":url,"method":method,"sample":sample,"error":e.to_string()})
    };
    rows.push(row);tokio::time::sleep(Duration::from_millis(100)).await;
   }
  }
 }
 for url in ["wss://sequencer.mainnet.chain.robinhood.com","wss://rpc.mainnet.chain.robinhood.com","wss://rpc-robinhood.blockmachine.io"] {
  let start=Instant::now();
  match tokio::time::timeout(Duration::from_secs(10),tokio_tungstenite::connect_async(url)).await {
   Ok(Ok((mut ws,_)))=>{
    rows.push(json!({"transport":"ws_connect","url":url,"elapsed_ms":start.elapsed().as_secs_f64()*1000.}));
    for sample in 0..10 {
     let start=Instant::now();ws.send(tokio_tungstenite::tungstenite::Message::Text(json!({"jsonrpc":"2.0","id":sample,"method":"eth_sendRawTransaction","params":["0x00"]}).to_string().into())).await?;
     let result=tokio::time::timeout(Duration::from_secs(10),async {loop {let m=ws.next().await?;if let Ok(tokio_tungstenite::tungstenite::Message::Text(s))=m {let v:Value=serde_json::from_str(&s).ok()?;if v["id"]==sample{return Some(v)}}}}).await;
     rows.push(json!({"transport":"ws","url":url,"sample":sample,"elapsed_ms":start.elapsed().as_secs_f64()*1000.,"result":format!("{result:?}")}));
     tokio::time::sleep(Duration::from_millis(100)).await;
    }
   },
   other=>rows.push(json!({"transport":"ws_connect","url":url,"error":format!("{other:?}")}))
  }
 }
 println!("{}",serde_json::to_string_pretty(&rows)?);Ok(())
}
