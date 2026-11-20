//! Parse untrusted receipt/log JSON into identity-checked executor evidence.
//! Canonical hash/head are supplied by the independent canonical observer, not the receipt itself.
use super::{Amount, Inventory, ReceiptEvidence, Side, codec, portfolio::WalletPending};
use anyhow::{Context, Result, ensure};
use serde_json::Value;
fn bytes<const N: usize>(v: &Value) -> Result<[u8; N]> {
    let x = hex::decode(
        v.as_str()
            .context("hex string")?
            .strip_prefix("0x")
            .context("hex prefix")?,
    )?;
    x.try_into().map_err(|_| anyhow::anyhow!("hex length"))
}
fn address_topic(v: &Value) -> Result<[u8; 20]> {
    let b = bytes::<32>(v)?;
    ensure!(b[..12] == [0; 12], "address padding");
    Ok(b[12..].try_into()?)
}
fn uint(v: &Value) -> Result<u64> {
    u64::from_str_radix(
        v.as_str()
            .context("quantity")?
            .strip_prefix("0x")
            .context("quantity prefix")?,
        16,
    )
    .map_err(Into::into)
}
pub fn decode(
    r: &Value,
    p: &WalletPending,
    wallet: [u8; 20],
    executor: [u8; 20],
    base_token: [u8; 20],
    quote_token: [u8; 20],
    before: &Inventory,
    canonical_hash: [u8; 32],
    canonical_head: u64,
) -> Result<ReceiptEvidence> {
    ensure!(
        bytes::<32>(&r["transactionHash"])? == p.order.hash
            && bytes::<20>(&r["from"])? == wallet
            && bytes::<20>(&r["to"])? == executor,
        "receipt transaction mismatch"
    );
    let block = uint(&r["blockNumber"])?;
    let hash = bytes::<32>(&r["blockHash"])?;
    ensure!(
        hash == canonical_hash && hash != [0; 32] && canonical_head >= block,
        "receipt not canonical"
    );
    let status = uint(&r["status"])?;
    ensure!(status <= 1, "invalid receipt status");
    let mut proof = ReceiptEvidence {
        hash: p.order.hash,
        wallet,
        pool: p.pool,
        nonce: p.order.nonce,
        block_hash: hash,
        canonical_hash,
        confirmations: canonical_head - block + 1,
        success: status == 1,
        matched_swap: false,
        usdg_amount: Amount(0),
        balances: before.clone(),
    };
    let logs = r["logs"].as_array().context("receipt logs")?;
    if status == 0 {
        ensure!(logs.is_empty(), "revert with logs");
        return Ok(proof);
    }
    let executed = codec::hash(b"Executed(address,address,bool,uint128,uint128)");
    let swap = codec::hash(b"Swap(address,address,uint256,uint256,uint256)");
    let transfer = codec::hash(b"Transfer(address,address,uint256)");
    let mut own = None;
    let mut swaps = vec![];
    let (mut bin_, mut bout, mut qin, mut qout) = (0u128, 0u128, 0u128, 0u128);
    for l in logs {
        ensure!(l["removed"] != true, "removed log");
        if !l["transactionHash"].is_null() {
            ensure!(
                bytes::<32>(&l["transactionHash"])? == p.order.hash,
                "log tx mismatch"
            );
        }
        if !l["blockHash"].is_null() {
            ensure!(bytes::<32>(&l["blockHash"])? == hash, "log block mismatch");
        }
        let a = bytes::<20>(&l["address"])?;
        let topics = l["topics"].as_array().context("topics")?;
        if topics.is_empty() {
            continue;
        }
        let topic = bytes::<32>(&topics[0])?;
        let data = hex::decode(
            l["data"]
                .as_str()
                .context("log data")?
                .strip_prefix("0x")
                .context("data prefix")?,
        )?;
        if a == executor && topic == executed {
            ensure!(
                topics.len() == 3 && data.len() == 96 && own.is_none(),
                "invalid executor log"
            );
            ensure!(
                address_topic(&topics[1])? == p.pool && address_topic(&topics[2])? == wallet,
                "executor log identity"
            );
            let buy = codec::uint(&data[..32])?;
            ensure!(
                buy <= 1 && (buy == 1) == (p.order.intent.side == Side::Buy),
                "wrong side"
            );
            ensure!(
                codec::uint(&data[32..64])? == p.order.intent.quantity.0,
                "wrong executed quantity"
            );
            own = Some(codec::uint(&data[64..96])?);
        }
        if a == p.pool && topic == swap {
            ensure!(
                topics.len() == 3
                    && data.len() == 96
                    && address_topic(&topics[1])? == executor
                    && address_topic(&topics[2])? == wallet,
                "pool swap identity"
            );
            let db = i128::from_be_bytes(data[32..48].try_into()?);
            let dq = i128::from_be_bytes(data[48..64].try_into()?);
            swaps.push((db, dq));
        }
        if (a == base_token || a == quote_token) && topic == transfer {
            ensure!(topics.len() == 3 && data.len() == 32, "invalid transfer");
            let from = address_topic(&topics[1])?;
            let to = address_topic(&topics[2])?;
            let amount = codec::uint(&data)?;
            let (input, output) = if a == base_token {
                (&mut bin_, &mut bout)
            } else {
                (&mut qin, &mut qout)
            };
            if to == wallet {
                *input = input.checked_add(amount).context("transfer overflow")?;
            }
            if from == wallet {
                *output = output.checked_add(amount).context("transfer overflow")?;
            }
        }
    }
    let amount = own.context("missing executor event")?;
    ensure!(
        amount > 0 && swaps.len() == 1,
        "missing/ambiguous pool swap"
    );
    let quantity = i128::try_from(p.order.intent.quantity.0)?;
    let amount_i = i128::try_from(amount)?;
    // Stock catalog is token0=stock/token1=USDG; reversed pools are rejected at catalog loading.
    let expected = match p.order.intent.side {
        Side::Buy => (-quantity, amount_i),
        Side::Sell => (quantity, -amount_i),
    };
    ensure!(swaps[0] == expected, "pool/executor deltas disagree");
    let expected_transfers = match p.order.intent.side {
        Side::Buy => (quantity as u128, 0, 0, amount),
        Side::Sell => (0, quantity as u128, amount, 0),
    };
    ensure!(
        (bin_, bout, qin, qout) == expected_transfers,
        "wallet transfers disagree"
    );
    proof.balances = Inventory {
        base: Amount(
            before
                .base
                .0
                .checked_add(bin_)
                .and_then(|x| x.checked_sub(bout))
                .context("base balance underflow")?,
        ),
        cash: Amount(
            before
                .cash
                .0
                .checked_add(qin)
                .and_then(|x| x.checked_sub(qout))
                .context("cash balance underflow")?,
        ),
    };
    proof.usdg_amount = Amount(amount);
    proof.matched_swap = true;
    Ok(proof)
}
