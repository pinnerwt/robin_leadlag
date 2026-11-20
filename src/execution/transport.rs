//! Submission only. Acknowledgements are telemetry, never fill/nonce authority.
use super::Pending;
use anyhow::{Result, ensure};
use serde_json::json;
use std::time::{Duration, Instant};
#[derive(Debug, Clone, serde::Serialize)]
pub struct Ack {
    pub endpoint: usize,
    pub http_status: Option<u16>,
    pub rpc_error: Option<serde_json::Value>,
    pub matched_hash: bool,
    pub elapsed_us: u128,
}
/// Reuse this client outside the signal loop. No account/gas/simulation requests.
pub fn client(timeout: Duration) -> Result<reqwest::Client> {
    ensure!(
        !timeout.is_zero() && timeout <= Duration::from_secs(30),
        "invalid submit timeout"
    );
    Ok(reqwest::Client::builder()
        .user_agent("robin-leadlag/0.1")
        .timeout(timeout)
        .pool_idle_timeout(Duration::from_secs(90))
        .tcp_nodelay(true)
        .build()?)
}
/// All endpoints receive identical nonce/raw bytes. Call only after durable reserve.
/// Run in a detached owned task; ACK latency does not block feed/decision ownership.
pub async fn broadcast(
    client: &reqwest::Client,
    urls: &[String],
    pending: &Pending,
) -> Result<Vec<Ack>> {
    ensure!(!urls.is_empty() && urls.len() <= 8, "submit endpoint count");
    ensure!(
        super::codec::hash(&pending.raw) == pending.hash,
        "raw hash mismatch"
    );
    for url in urls {
        let u = reqwest::Url::parse(url)?;
        ensure!(
            matches!(u.scheme(), "http" | "https"),
            "unsupported submit scheme"
        );
    }
    let requests=urls.iter().enumerate().map(|(endpoint,url)|submit(client,url,endpoint,pending));
    Ok(futures_util::future::join_all(requests).await)
}
pub async fn submit(client:&reqwest::Client,url:&str,endpoint:usize,pending:&Pending)->Ack {
 let started=Instant::now();let mut ack=Ack{endpoint,matched_hash:false,elapsed_us:0,http_status:None,rpc_error:None};
 if super::codec::hash(&pending.raw)!=pending.hash {ack.rpc_error=Some(json!({"message":"raw hash mismatch"}));return ack}
 let raw=format!("0x{}",hex::encode(&pending.raw));let expected=format!("0x{}",hex::encode(pending.hash));
 match client.post(url).json(&json!({"jsonrpc":"2.0","id":1,"method":"eth_sendRawTransaction","params":[raw]})).send().await {
  Ok(response)=>{
   ack.http_status=Some(response.status().as_u16());
   match response.json::<serde_json::Value>().await {
    Ok(v)=>{ack.matched_hash=ack.http_status==Some(200)&&v["id"]==1&&v.get("error").is_none()&&v["result"].as_str().is_some_and(|s|s.eq_ignore_ascii_case(&expected));ack.rpc_error=v.get("error").cloned();if !ack.matched_hash&&ack.rpc_error.is_none(){ack.rpc_error=Some(json!({"message":"unexpected response identity or hash"}));}},
    Err(_)=>ack.rpc_error=Some(json!({"message":"invalid JSON response"}))
   }
  },
  Err(e)=>ack.rpc_error=Some(json!({"message":if e.is_timeout(){"request timeout"}else{"transport failure"}}))
 }
 ack.elapsed_us=started.elapsed().as_micros();ack
}

#[cfg(test)]
mod tests {
    use super::*;
    use tokio::{
        io::{AsyncReadExt, AsyncWriteExt},
        net::TcpListener,
    };
    async fn endpoint(result: String) -> (String, tokio::task::JoinHandle<serde_json::Value>) {
        let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
        let addr = listener.local_addr().unwrap();
        let task = tokio::spawn(async move {
            let (mut socket, _) = listener.accept().await.unwrap();
            let mut input = vec![];
            let mut buf = [0; 4096];
            let (offset, length) = loop {
                let n = socket.read(&mut buf).await.unwrap();
                assert!(n > 0);
                input.extend_from_slice(&buf[..n]);
                if let Some(i) = input.windows(4).position(|w| w == b"\r\n\r\n") {
                    let h = String::from_utf8_lossy(&input[..i]);
                    let n = h
                        .lines()
                        .find_map(|l| {
                            l.to_lowercase()
                                .strip_prefix("content-length:")
                                .map(|s| s.trim().parse::<usize>().unwrap())
                        })
                        .unwrap();
                    break (i + 4, n);
                }
            };
            while input.len() < offset + length {
                let n = socket.read(&mut buf).await.unwrap();
                assert!(n > 0);
                input.extend_from_slice(&buf[..n]);
            }
            let request = serde_json::from_slice(&input[offset..offset + length]).unwrap();
            let body = json!({"jsonrpc":"2.0","id":1,"result":result}).to_string();
            let response = format!(
                "HTTP/1.1 200 OK\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{}",
                body.len(),
                body
            );
            socket.write_all(response.as_bytes()).await.unwrap();
            request
        });
        (format!("http://{addr}"), task)
    }
    #[tokio::test]
    async fn identical_bytes_fanout_and_wrong_hash_is_not_ack() {
        let raw = vec![2, 1, 2, 3];
        let hash = super::super::codec::hash(&raw);
        let (a, ta) = endpoint(format!("0x{}", hex::encode(hash))).await;
        let (b, tb) = endpoint(format!("0x{}", hex::encode([0; 32]))).await;
        let p = Pending {
            intent: super::super::Intent {
                side: super::super::Side::Buy,
                opening: true,
                quantity: super::super::Amount(1),
                quote_usdg: super::super::Amount(1),
                limit_usdg: super::super::Amount(1),
                signal_ns: 1,
                valid_until_ns: 2,
                epoch: 1,
                state_version: 1,
            },
            nonce: 7,
            hash,
            raw,
        };
        let client = reqwest::Client::builder()
            .no_proxy()
            .timeout(Duration::from_secs(2))
            .build()
            .unwrap();
        let replies = broadcast(&client, &[a, b], &p).await.unwrap();
        assert!(replies[0].matched_hash);
        assert!(!replies[1].matched_hash);
        let ra = ta.await.unwrap();
        let rb = tb.await.unwrap();
        assert_eq!(ra, rb);
        assert_eq!(ra["method"], "eth_sendRawTransaction");
        assert_eq!(ra["params"][0], "0x02010203");
    }
}
