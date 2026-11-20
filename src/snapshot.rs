use anyhow::{Context, Result, ensure};
use futures_util::{StreamExt, stream};
use serde_json::{Value, json};
use sha3::{Digest, Keccak256};
use std::time::Duration;

async fn rpc(client: &reqwest::Client, url: &str, method: &str, params: Value) -> Result<Value> {
    let response: Value = client
        .post(url)
        .json(&json!({"jsonrpc":"2.0","id":1,
        "method":method,"params":params}))
        .send()
        .await?
        .error_for_status()?
        .json()
        .await?;
    ensure!(
        response["id"] == 1 && response["error"].is_null() && !response["result"].is_null(),
        "{method} returned no result"
    );
    Ok(response["result"].clone())
}

async fn call(
    client: &reqwest::Client,
    url: &str,
    pool: &str,
    block: &str,
    data: String,
) -> Result<Vec<u8>> {
    let result = rpc(
        client,
        url,
        "eth_call",
        json!([{"to":pool,"data":data},block]),
    )
    .await?;
    Ok(hex::decode(
        result
            .as_str()
            .and_then(|s| s.strip_prefix("0x"))
            .context("invalid call data")?,
    )?)
}

fn read_bin(data: &[u8]) -> [i128; 2] {
    let mut lo = [0u8; 16];
    let mut hi = [0u8; 16];
    lo[3..].copy_from_slice(&data[19..32]);
    hi[3..].copy_from_slice(&data[6..19]);
    [i128::from_be_bytes(lo), i128::from_be_bytes(hi)]
}

async fn pool_state(
    client: &reqwest::Client,
    url: &str,
    address: String,
    block: &str,
) -> Result<Value> {
    let settings = call(client, url, &address, block, "0xbcdb4dad".to_owned()).await?;
    ensure!(settings.len() == 768, "unexpected getImmutables ABI");
    let lower = i16::from_be_bytes(settings[318..320].try_into()?);
    let upper = i16::from_be_bytes(settings[350..352].try_into()?);
    ensure!(
        upper >= lower && i32::from(upper) - i32::from(lower) < 2048,
        "unsupported bin bounds"
    );
    let mut data = Vec::new();
    data.extend(abi(32));
    data.extend(abi(i128::from(upper) - i128::from(lower) + 3));
    data.extend(abi(0));
    data.extend(abi(1));
    for bin in lower..=upper {
        let mut key = abi(i128::from(bin)).to_vec();
        key.extend(abi(4));
        data.extend(Keccak256::digest(key));
    }
    let response = call(
        client,
        url,
        &address,
        block,
        format!("0xdbd035ff{}", hex::encode(data)),
    )
    .await?;
    ensure!(
        response.len() == (i32::from(upper) - i32::from(lower) + 5) as usize * 32,
        "unexpected extsload ABI"
    );
    let mut sum = [0, 0];
    let bins: Vec<_> = response[128..]
        .chunks_exact(32)
        .zip(lower..=upper)
        .map(|(word, bin)| {
            let balance = read_bin(word);
            sum[0] += balance[0];
            sum[1] += balance[1];
            json!([
                bin,
                balance[0].to_string(),
                balance[1].to_string(),
                u16::from_be_bytes(word[4..6].try_into().unwrap()),
                u16::from_be_bytes(word[2..4].try_into().unwrap()),
                u16::from_be_bytes(word[..2].try_into().unwrap())
            ])
        })
        .collect();
    // BinTotals uses two uint128s rather than uint104s.
    let totals = [
        i128::from_be_bytes(response[112..128].try_into()?),
        i128::from_be_bytes(response[96..112].try_into()?),
    ];
    ensure!(sum == totals, "bin layout or aggregate balances differ");
    Ok(json!({"pool":address,"slot0":hex::encode(&response[64..96]),"bins":bins}))
}

fn abi(value: i128) -> [u8; 32] {
    let mut word = [if value < 0 { 255 } else { 0 }; 32];
    word[16..].copy_from_slice(&value.to_be_bytes());
    word
}

pub async fn read(url: &str, pools: Vec<String>, epoch: u64) -> Result<Value> {
    let client = reqwest::Client::builder()
        .timeout(Duration::from_secs(8))
        .build()?;
    let head = rpc(
        &client,
        url,
        "eth_getBlockByNumber",
        json!(["latest", false]),
    )
    .await?;
    let block = head["number"].as_str().context("missing snapshot height")?;
    let states = stream::iter(
        pools
            .into_iter()
            .map(|pool| pool_state(&client, url, pool, block)),
    )
    .buffer_unordered(4)
    .collect::<Vec<_>>()
    .await;
    let verified = rpc(&client, url, "eth_getBlockByNumber", json!([block, false])).await?;
    ensure!(head["hash"] == verified["hash"], "snapshot reorg");
    let (mut pools, mut failed) = (Vec::new(), 0);
    for result in states {
        match result {
            Ok(pool) => pools.push(pool),
            Err(_) => failed += 1,
        }
    }
    Ok(
        json!({"kind":"bin_snapshot","recv_ns":super::now_ns(),"bin_epoch":epoch,
        "block":super::quantity(&head["number"]),"hash":head["hash"],"pools":pools,"failed":failed}),
    )
}
