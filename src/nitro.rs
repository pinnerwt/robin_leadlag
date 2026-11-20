use alloy_consensus::{Transaction, TxEnvelope};
use alloy_eips::eip2718::Decodable2718;
use alloy_rlp::{Encodable, Header};
use anyhow::{Context, Result, ensure};
use base64::{Engine, engine::general_purpose::STANDARD};
use serde_json::{Value, json};
use sha3::{Digest, Keccak256};
fn visit(message: &[u8], depth: u8, out: &mut Vec<Vec<u8>>) -> Result<()> {
    ensure!(depth <= 16, "nitro batch depth");
    match message.split_first() {
        Some((4, raw)) => out.push(raw.to_vec()),
        Some((3, mut batch)) => {
            while !batch.is_empty() {
                let len = u64::from_be_bytes(batch.get(..8).context("batch length")?.try_into()?)
                    as usize;
                batch = &batch[8..];
                let (child, rest) = batch.split_at_checked(len).context("batch data")?;
                visit(child, depth + 1, out)?;
                batch = rest;
            }
        }
        _ => anyhow::bail!("unsupported L2 message kind {:?}", message.first()),
    }
    Ok(())
}
pub fn transactions(row: &Value) -> Result<Vec<Value>> {
    parse_transactions(row, true)
}
/// Offline price-feed extraction needs signed transaction hashes and calldata,
/// but not sender recovery. Callers must not use this path to learn sender aliases.
pub fn transactions_without_sender(row: &Value) -> Result<Vec<Value>> {
    parse_transactions(row, false)
}
fn parse_transactions(row: &Value, recover_sender: bool) -> Result<Vec<Value>> {
    let mut output = Vec::new();
    for item in row["payload"]["messages"].as_array().into_iter().flatten() {
        let msg = &item["message"]["message"];
        if msg["header"]["kind"] == 9 {
            output.push(submit_retryable(row, item, msg)?);
            continue;
        }
        if msg["header"]["kind"] == 12 {
            // Nitro parseEthDepositMessage: 20-byte recipient, 32-byte value.
            // Decoding is not execution support: the follower must still apply
            // deposit mint/transfer and onchain filtering, or reject this kind.
            let bytes = STANDARD.decode(msg["l2Msg"].as_str().context("deposit data")?)?;
            ensure!(bytes.len() == 52, "unsupported deposit payload length");
            let request = msg["header"]["requestId"]
                .as_str()
                .context("deposit missing L1 request id")?;
            let request_bytes =
                hex::decode(request.strip_prefix("0x").context("request id prefix")?)?;
            ensure!(request_bytes.len() == 32, "deposit request id length");
            let sender = msg["header"]["sender"]
                .as_str()
                .context("deposit missing sender")?;
            let sender_bytes = hex::decode(sender.strip_prefix("0x").context("sender prefix")?)?;
            ensure!(sender_bytes.len() == 20, "deposit sender length");
            // geth ArbitrumDepositTx: type 0x64 followed by RLP of these fields.
            let mut body = Vec::new();
            4663u64.encode(&mut body);
            request_bytes.as_slice().encode(&mut body);
            sender_bytes.as_slice().encode(&mut body);
            bytes[..20].encode(&mut body);
            let value = &bytes[20..];
            let first = value.iter().position(|b| *b != 0).unwrap_or(value.len());
            value[first..].encode(&mut body);
            let mut raw = vec![0x64];
            Header {
                list: true,
                payload_length: body.len(),
            }
            .encode(&mut raw);
            raw.extend(body);
            output.push(json!({"kind":"feed_system_tx","system_kind":"eth_deposit",
                "from":sender,"to":format!("0x{}",hex::encode(&bytes[..20])),
                "value":format!("0x{}",hex::encode(&bytes[20..])),"l1_request_id":request,
                "tx":format!("0x{}",hex::encode(Keccak256::digest(&raw))),"raw_transaction":format!("0x{}",hex::encode(raw)),
                "block_hash":item["blockHash"],"sequence":item["sequenceNumber"],
                "timestamp":msg["header"]["timestamp"],"l1_block":msg["header"]["blockNumber"],
                "mono_ns":row["mono_ns"],"recv_ns":row["recv_ns"]}));
            continue;
        }
        if msg["header"]["kind"] == 13 {
            let bytes = STANDARD.decode(msg["l2Msg"].as_str().context("batch report data")?)?;
            ensure!(
                bytes.len() == 148 || bytes.len() == 156,
                "batch report length"
            );
            ensure!(
                bytes[84..108].iter().all(|v| *v == 0),
                "batch number exceeds uint64"
            );
            let stats = &msg["batchDataTokens"];
            let length = stats["length"]
                .as_u64()
                .context("batch report missing length")?;
            let nonzeros = stats["nonzeros"]
                .as_u64()
                .context("batch report missing nonzeros")?;
            ensure!(nonzeros <= length, "batch report nonzeros exceeds length");
            let extra = if bytes.len() == 156 {
                u64::from_be_bytes(bytes[148..156].try_into()?)
            } else {
                0
            };
            output.push(
                json!({"kind":"feed_system_tx","system_kind":"batch_posting_report_v2",
                "batch_timestamp":format!("0x{}",hex::encode(&bytes[..32])),
                "batch_poster":format!("0x{}",hex::encode(&bytes[32..52])),
                "batch_hash":format!("0x{}",hex::encode(&bytes[52..84])),
                "batch_number":u64::from_be_bytes(bytes[108..116].try_into()?),
                "l1_base_fee":format!("0x{}",hex::encode(&bytes[116..148])),
                "extra_gas":extra,"calldata_length":length,"calldata_nonzeros":nonzeros,
                "block_hash":item["blockHash"],"sequence":item["sequenceNumber"],
                "timestamp":msg["header"]["timestamp"],"l1_block":msg["header"]["blockNumber"],
                "mono_ns":row["mono_ns"],"recv_ns":row["recv_ns"]}),
            );
            continue;
        }
        ensure!(
            msg["header"]["kind"] == 3,
            "unsupported L1 message kind {} at sequence {}",
            msg["header"]["kind"],
            item["sequenceNumber"]
        );
        let bytes = STANDARD.decode(msg["l2Msg"].as_str().context("l2Msg")?)?;
        let mut raws = Vec::new();
        visit(&bytes, 0, &mut raws)?;
        for raw in raws {
            let tx = TxEnvelope::decode_2718(&mut raw.as_slice())?;
            let to = tx.to().map(|address| address.to_string());
            ensure!(tx.chain_id() == Some(4663), "unexpected chain");
            let from = if recover_sender {
                tx.recover_signer()?.to_string()
            } else {
                "unrecovered".to_owned()
            };
            output.push(json!({"kind":"feed_tx","to":to,"nonce":tx.nonce(),"gas_limit":tx.gas_limit(),"max_fee_per_gas":format!("{:#x}",tx.max_fee_per_gas()),"max_priority_fee_per_gas":tx.max_priority_fee_per_gas().map(|v| format!("{v:#x}")),"raw_transaction":format!("0x{}",hex::encode(&raw)),"from":from.to_string(),"data":format!("0x{}",hex::encode(tx.input())),"value":format!("{:#x}",tx.value()),"tx":tx.tx_hash().to_string(),"block_hash":item["blockHash"],"sequence":item["sequenceNumber"],"timestamp":msg["header"]["timestamp"],"l1_block":msg["header"]["blockNumber"],"mono_ns":row["mono_ns"],"recv_ns":row["recv_ns"]}));
        }
    }
    Ok(output)
}

// Nitro arbos/parse_l2.go + geth ArbitrumSubmitRetryableTx RLP field order.
// Submission is NOT redemption: do not expose retry_data as a direct feed_tx.
fn submit_retryable(row: &Value, item: &Value, msg: &Value) -> Result<Value> {
    fn fixed(v: &Value, n: usize) -> Result<Vec<u8>> {
        let s = v.as_str().context("retryable hex field")?;
        let b = hex::decode(s.strip_prefix("0x").context("hex prefix")?)?;
        ensure!(b.len() == n, "retryable field width");
        Ok(b)
    }
    fn integer(v: &[u8], out: &mut Vec<u8>) {
        let n = v.iter().position(|x| *x != 0).unwrap_or(v.len());
        v[n..].encode(out);
    }
    let b = STANDARD.decode(msg["l2Msg"].as_str().context("retryable payload")?)?;
    ensure!(b.len() >= 288, "truncated retryable header");
    let w = |i: usize| &b[i * 32..(i + 1) * 32];
    ensure!(
        w(6)[..24].iter().all(|v| *v == 0),
        "retryable gas exceeds uint64"
    );
    ensure!(
        w(8)[..24].iter().all(|v| *v == 0),
        "retryable length exceeds uint64"
    );
    let n = u64::from_be_bytes(w(8)[24..].try_into()?) as usize;
    ensure!(
        n <= 256 * 1024 && b.len() == 288 + n,
        "retryable data length mismatch"
    );
    let request = fixed(&msg["header"]["requestId"], 32)?;
    let sender = fixed(&msg["header"]["sender"], 20)?;
    let fv = &msg["header"]["baseFeeL1"];
    let fee = if let Some(n) = fv.as_u64() {
        n.to_be_bytes().to_vec()
    } else {
        let fee = fv
            .as_str()
            .context("retryable L1 base fee")?
            .strip_prefix("0x")
            .context("L1 fee hex")?;
        hex::decode(if fee.len() % 2 == 0 {
            fee.to_owned()
        } else {
            format!("0{fee}")
        })?
    };
    ensure!(fee.len() <= 32, "L1 fee overflow");
    let to = &w(0)[12..];
    let target = if to.iter().all(|v| *v == 0) {
        None
    } else {
        Some(format!("0x{}", hex::encode(to)))
    };
    let mut body = Vec::new();
    4663u64.encode(&mut body);
    request.as_slice().encode(&mut body);
    sender.as_slice().encode(&mut body);
    integer(&fee, &mut body);
    integer(w(2), &mut body);
    integer(w(7), &mut body);
    integer(w(6), &mut body);
    if target.is_none() {
        (&[] as &[u8]).encode(&mut body)
    } else {
        to.encode(&mut body)
    }
    integer(w(1), &mut body);
    w(5)[12..].encode(&mut body);
    integer(w(3), &mut body);
    w(4)[12..].encode(&mut body);
    b[288..].encode(&mut body);
    let mut raw = vec![0x69];
    Header {
        list: true,
        payload_length: body.len(),
    }
    .encode(&mut raw);
    raw.extend(body);
    Ok(
        json!({"kind":"feed_system_tx","system_kind":"submit_retryable","from":format!("0x{}",hex::encode(sender)),"to":"0x000000000000000000000000000000000000006e","value":"0x0",
      "retry_to":target,"retry_data":format!("0x{}",hex::encode(&b[288..])),"retry_value":format!("0x{}",hex::encode(w(1))),"deposit_value":format!("0x{}",hex::encode(w(2))),
      "gas_limit":u64::from_be_bytes(w(6)[24..].try_into()?),"max_fee_per_gas":format!("0x{}",hex::encode(w(7))),"max_submission_fee":format!("0x{}",hex::encode(w(3))),
      "fee_refund_address":format!("0x{}",hex::encode(&w(4)[12..])),"beneficiary":format!("0x{}",hex::encode(&w(5)[12..])),"l1_request_id":msg["header"]["requestId"],
      "tx":format!("0x{}",hex::encode(Keccak256::digest(&raw))),"raw_transaction":format!("0x{}",hex::encode(raw)),"block_hash":item["blockHash"],"sequence":item["sequenceNumber"],"timestamp":msg["header"]["timestamp"],"l1_block":msg["header"]["blockNumber"],"mono_ns":row["mono_ns"],"recv_ns":row["recv_ns"],"execution_semantics":"ticket submission only; redemption requires separate execution evidence"}),
    )
}

#[cfg(test)]
mod retryable_tests {
    use super::*;
    fn fixture() -> Value {
        serde_json::from_str(include_str!(
            "../tests/fixtures/nitro_submit_retryable.json"
        ))
        .unwrap()
    }
    fn payload(r: &Value) -> Vec<u8> {
        STANDARD
            .decode(
                r["payload"]["messages"][0]["message"]["message"]["l2Msg"]
                    .as_str()
                    .unwrap(),
            )
            .unwrap()
    }
    fn with_payload(mut r: Value, b: Vec<u8>) -> Value {
        r["payload"]["messages"][0]["message"]["message"]["l2Msg"] = json!(STANDARD.encode(b));
        r
    }
    #[test]
    fn recorded_retryable_hash_and_submission_semantics() {
        let r = fixture();
        let ts = transactions_without_sender(&r).unwrap();
        assert_eq!(
            ts[0]["tx"],
            "0xecc2d4e7f351325c06508a6c325f9813f2e96c822496f94ae2e5dab623280edb"
        );
        assert_eq!(ts[0]["system_kind"], "submit_retryable");
        assert_eq!(ts[0]["to"], "0x000000000000000000000000000000000000006e");
        assert!(ts[0].get("data").is_none());
        assert_eq!(transactions(&r).unwrap(), ts);
    }
    #[test]
    fn retryable_rejects_truncation_lengths_and_overflow() {
        let r = fixture();
        let b = payload(&r);
        for size in [0, 287, b.len() - 1] {
            assert!(
                transactions_without_sender(&with_payload(r.clone(), b[..size].to_vec())).is_err()
            );
        }
        let mut bad = b.clone();
        bad[192] = 1;
        assert!(transactions_without_sender(&with_payload(r.clone(), bad)).is_err());
        let mut bad = b.clone();
        bad[256] = 1;
        assert!(transactions_without_sender(&with_payload(r.clone(), bad)).is_err());
        let mut bad = b;
        bad.push(0);
        assert!(transactions_without_sender(&with_payload(r.clone(), bad)).is_err());
        let mut r = r;
        r["payload"]["messages"][0]["message"]["message"]["header"]["requestId"] = Value::Null;
        assert!(transactions_without_sender(&r).is_err());
    }
    #[test]
    fn retryable_contract_creation_and_mixed_messages() {
        let r = fixture();
        let mut b = payload(&r);
        b[..32].fill(0);
        let v = transactions_without_sender(&with_payload(r.clone(), b)).unwrap();
        assert!(v[0]["retry_to"].is_null());
        let mut mixed: Value =
            serde_json::from_str(include_str!("../tests/fixtures/nitro_two_messages.json"))
                .unwrap();
        let count = transactions_without_sender(&mixed).unwrap().len();
        mixed["payload"]["messages"]
            .as_array_mut()
            .unwrap()
            .extend(r["payload"]["messages"].as_array().unwrap().clone());
        assert_eq!(
            transactions_without_sender(&mixed).unwrap().len(),
            count + 1
        );
    }
}
