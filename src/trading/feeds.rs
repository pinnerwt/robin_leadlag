use super::{Event, now_ns};
use anyhow::{Context, Result, ensure};
use futures_util::{SinkExt, StreamExt};
use serde_json::{Value, json};
use tokio::{
    sync::{mpsc, watch},
    time::{Duration, timeout},
};
use tokio_tungstenite::{connect_async, tungstenite::Message};
async fn send(tx: &mpsc::Sender<Event>, event: Event) -> Result<()> {
    tx.send(event).await.context("engine stopped")
}
pub async fn binance(
    url: String,
    link: usize,
    tx: mpsc::Sender<Event>,
    mut rotate: watch::Receiver<u64>,
) {
    loop {
        let result=async {
   let (mut ws,_)=timeout(Duration::from_secs(10),connect_async(&url)).await??;
   send(&tx,Event::BinanceLink(link,true)).await?;
   loop {tokio::select!{
    _=rotate.changed()=>{let _=ws.close(None).await;break;},
    packet=timeout(Duration::from_secs(30),ws.next())=>{
     let message=packet?.context("Binance socket ended")??;let recv=now_ns();
     match message {
      Message::Text(s)=>{let r:Value=serde_json::from_str(&s)?;ensure!(r["s"]=="ETHUSDT","unexpected Binance symbol");send(&tx,Event::Bbo{link,recv,id:r["u"].as_u64().context("sequence")?,bid:r["b"].as_str().context("bid")?.to_owned(),ask:r["a"].as_str().context("ask")?.to_owned()}).await?;},
      Message::Ping(_)=>ws.flush().await?,Message::Close(_)=>break,_=>{}
     }
    }
   }} Ok::<_,anyhow::Error>(())
  }.await;
        if send(&tx, Event::BinanceLink(link, false)).await.is_err() {
            return;
        }
        // Never print a URL (it may later contain a provider credential).
        let _ = result;
        tokio::time::sleep(Duration::from_secs(1)).await;
    }
}
pub async fn heads(url: String, tx: mpsc::Sender<Event>) {
    loop {
        let result=async {
   let (mut ws,_)=timeout(Duration::from_secs(10),connect_async(&url)).await??;
   // Cold connection identity check only, never a per-signal request.
   ws.send(Message::Text(json!({"jsonrpc":"2.0","id":1,"method":"eth_chainId","params":[]}).to_string().into())).await?;
   let mut verified=false;
   loop {
    let m=timeout(Duration::from_secs(15),ws.next()).await?.context("head socket ended")??;
    match m {
     Message::Text(s)=>{
      let r:Value=serde_json::from_str(&s)?;
      if r["id"]==1 {ensure!(r["result"]=="0x1237","wrong chain");verified=true;ws.send(Message::Text(json!({"jsonrpc":"2.0","id":2,"method":"eth_subscribe","params":["newHeads"]}).to_string().into())).await?;continue;}
      if r["id"]==2 {ensure!(r["result"].is_string()&&r.get("error").is_none(),"head subscription failed");continue;}
      if r["method"]=="eth_subscription" {ensure!(verified,"unverified chain");send(&tx,Event::Head{recv:now_ns(),head:r["params"]["result"].clone()}).await?;}
     },
     Message::Ping(_)=>ws.flush().await?,Message::Close(_)=>break,_=>{}
    }
   } Ok::<_,anyhow::Error>(())
  }.await;
        let _ = result;
        if send(&tx, Event::ChainGap).await.is_err() {
            return;
        }
        tokio::time::sleep(Duration::from_secs(1)).await;
    }
}
