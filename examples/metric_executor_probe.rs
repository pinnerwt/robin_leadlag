//! Offline integration: archived real pool/provider bytecode + synthetic ERC20 balances/code.
//! No RPC, no deployment, no claim of token/allowance parity with the live chain.
#[path = "../src/local_evm.rs"]
mod local_evm;
use anyhow::{Context, Result, ensure};
use revm::primitives::{Address, U256, keccak256};
use robin_leadlag::execution::{Amount, Intent, Side, codec, metric};
use serde_json::{Value, json};
use std::str::FromStr;
fn runtime(path: &str, immutable: U256) -> Result<String> {
    let a: Value = serde_json::from_slice(&std::fs::read(path)?)?;
    let mut b = hex::decode(
        a["deployedBytecode"]["object"]
            .as_str()
            .context("bytecode")?
            .trim_start_matches("0x"),
    )?;
    for refs in a["deployedBytecode"]["immutableReferences"]
        .as_object()
        .context("immutables")?
        .values()
    {
        for r in refs.as_array().unwrap() {
            let start = r["start"].as_u64().unwrap() as usize;
            ensure!(r["length"] == 32, "immutable width");
            b[start..start + 32].copy_from_slice(&immutable.to_be_bytes::<32>());
        }
    }
    Ok(format!("0x{}", hex::encode(b)))
}
fn map(address: Address, slot: U256) -> U256 {
    let mut b = [0; 64];
    b[12..32].copy_from_slice(address.as_slice());
    b[32..].copy_from_slice(&slot.to_be_bytes::<32>());
    U256::from_be_bytes(keccak256(b).0)
}
fn run(
    db: &mut local_evm::State,
    h: &Value,
    to: Address,
    from: Address,
    data: Vec<u8>,
) -> Result<revm::primitives::ExecutionResult> {
    let r=db.run(h,&json!({"to":to.to_string(),"from":from.to_string(),"data":format!("0x{}",hex::encode(data))}),true)?;
    ensure!(r.is_success(), "EVM revert {:?}", local_evm::output(&r));
    Ok(r)
}
fn main() -> Result<()> {
    let args: Vec<_> = std::env::args().collect();
    let seed: Value = serde_json::from_slice(&std::fs::read(args.get(1).context("seed")?)?)?;
    let p = &seed["pools"][0];
    let h = &seed["anchor"];
    let owner = Address::from([0x11; 20]);
    let executor = Address::from([0x22; 20]);
    let pool = Address::from_str(p["pool"].as_str().unwrap())?;
    let base = Address::from_str(p["tokens"][0].as_str().unwrap())?;
    let quote = Address::from_str(p["tokens"][1].as_str().unwrap())?;
    let mut accounts = seed["accounts"].clone();
    let eruntime = runtime(
        "contracts/metric-executor/out/MetricInventoryExecutor.sol/MetricInventoryExecutor.json",
        U256::from_be_slice(owner.as_slice()),
    )?;
    accounts[executor.to_string().to_lowercase()] = json!({"code":eruntime,"storage":{}});
    accounts[owner.to_string().to_lowercase()] = json!({"code":"0x","storage":{}});
    for (t, d) in [(base, 18), (quote, 6)] {
        let alias = Address::from([if d == 18 { 0x33 } else { 0x44 }; 20]);
        accounts[alias.to_string().to_lowercase()] = accounts[t.to_string().to_lowercase()].clone();
        accounts[t.to_string().to_lowercase()] = json!({"code":runtime("contracts/metric-executor/out/MetricInventoryExecutor.t.sol/Token.json",U256::from(d))?,"storage":{}});
    }
    let mut db = local_evm::State::load(&accounts)?;
    for i in 0..32 {
        db.slots.insert((executor, U256::from(i)), U256::ZERO);
    }
    let root = map(pool, U256::ZERO);
    for i in 0..8 {
        db.slots
            .insert((executor, root + U256::from(i)), U256::ZERO);
    }
    for t in [base, quote] {
        db.slots.insert(
            (t, U256::from(2)),
            U256::from_be_slice(
                Address::from([if t == base { 0x33 } else { 0x44 }; 20]).as_slice(),
            ),
        );
        for who in [owner, pool, executor] {
            db.slots.insert(
                (t, map(who, U256::ZERO)),
                if who == executor {
                    U256::ZERO
                } else {
                    U256::from(10).pow(U256::from(30))
                },
            );
        }
        db.slots
            .insert((t, map(executor, map(owner, U256::from(1)))), U256::MAX);
    }
    let mut a = codec::address(pool.into_array());
    a.extend(codec::address(base.into_array()));
    a.extend(codec::address(quote.into_array()));
    a.extend(codec::word(1));
    a.extend(db.accounts[&pool].code_hash.as_slice());
    run(
        &mut db,
        h,
        executor,
        owner,
        codec::call("configurePool(address,address,address,bool,bytes32)", a),
    )?;
    let text = p["quote_checks"]
        .as_array()
        .unwrap()
        .iter()
        .filter(|r| r["seed_only"] == false)
        .filter_map(|r| r["size_tokens"].as_str())
        .last()
        .unwrap_or("0.1");
    let q = robin_leadlag::execution::baseline::parse_quantity(text, 18)?.0;
    let mut access_assumptions = vec![];
    if args.iter().any(|a| a == "--assume-pool-access") {
        let oracle = Address::from_str("0x30a88bf894d1b806125a23ebf23d715496fd7102")?;
        let blacklisted = map(pool, U256::from(10));
        db.slots.insert((oracle, blacklisted), U256::ZERO);
        let feed = p["aux_feed_id"].as_u64().context("aux_feed_id")?;
        let mut preimage = [0u8; 64];
        preimage[..32].copy_from_slice(&U256::from(feed).to_be_bytes::<32>());
        preimage[63] = 11;
        let registered = map(pool, U256::from_be_bytes(keccak256(preimage).0));
        db.slots.insert((oracle, registered), U256::from(1));
        access_assumptions.push(json!({"oracle":oracle.to_string(),"pool_blacklist_slot":format!("{blacklisted:#x}"),"blacklisted":false,"registered_slot":format!("{registered:#x}"),"registered":true,"feed":feed}));
    }
    let mut rows = vec![];
    for side in [Side::Buy, Side::Sell] {
        let beforebase = db.known_storage(base, map(owner, U256::ZERO)).unwrap();
        let beforecash = db.known_storage(quote, map(owner, U256::ZERO)).unwrap();
        let intent = Intent {
            side,
            opening: true,
            quantity: Amount(q),
            quote_usdg: Amount(0),
            limit_usdg: Amount(if side == Side::Buy { 1_000_000_000 } else { 1 }),
            signal_ns: 0,
            valid_until_ns: u64::from_str_radix(
                h["timestamp"].as_str().unwrap().trim_start_matches("0x"),
                16,
            )? * 1_000_000_000,
            epoch: 0,
            state_version: 0,
        };
        let result = run(
            &mut db,
            h,
            executor,
            owner,
            metric::trade(pool.into_array(), &intent)?,
        )?;
        let afterbase = db.known_storage(base, map(owner, U256::ZERO)).unwrap();
        let aftercash = db.known_storage(quote, map(owner, U256::ZERO)).unwrap();
        ensure!(
            if side == Side::Buy {
                afterbase == beforebase + U256::from(q)
            } else {
                beforebase == afterbase + U256::from(q)
            },
            "owner base delta mismatch"
        );
        let log_values:Vec<_>=result.logs().iter().map(|l|json!({"address":l.address.to_string(),"topics":l.data.topics().iter().map(|t|format!("{t:#x}")).collect::<Vec<_>>(),"data":format!("0x{}",hex::encode(&l.data.data))})).collect();
        let pending = robin_leadlag::execution::portfolio::WalletPending {
            ticker: "PROBE".into(),
            pool: pool.into_array(),
            order: robin_leadlag::execution::Pending {
                intent: intent.clone(),
                nonce: 0,
                hash: [1; 32],
                raw: vec![],
            },
        };
        let receipt = json!({"transactionHash":format!("0x{}",hex::encode([1;32])),"from":owner.to_string(),"to":executor.to_string(),"blockNumber":"0x1","blockHash":format!("0x{}",hex::encode([2;32])),"status":"0x1","logs":log_values});
        let before = robin_leadlag::execution::Inventory {
            base: Amount(beforebase.try_into()?),
            cash: Amount(beforecash.try_into()?),
        };
        let evidence = robin_leadlag::execution::receipt::decode(
            &receipt,
            &pending,
            owner.into_array(),
            executor.into_array(),
            base.into_array(),
            quote.into_array(),
            &before,
            [2; 32],
            1,
        )?;
        ensure!(
            evidence.balances.base.0 == u128::try_from(afterbase)?
                && evidence.balances.cash.0 == u128::try_from(aftercash)?,
            "receipt proof balance mismatch"
        );
        let mut bad = receipt.clone();
        bad["logs"]
            .as_array_mut()
            .unwrap()
            .retain(|l| l["address"] != base.to_string());
        ensure!(
            robin_leadlag::execution::receipt::decode(
                &bad,
                &pending,
                owner.into_array(),
                executor.into_array(),
                base.into_array(),
                quote.into_array(),
                &before,
                [2; 32],
                1
            )
            .is_err(),
            "missing transfer accepted"
        );
        ensure!(
            robin_leadlag::execution::receipt::decode(
                &receipt,
                &pending,
                owner.into_array(),
                executor.into_array(),
                base.into_array(),
                quote.into_array(),
                &before,
                [3; 32],
                1
            )
            .is_err(),
            "noncanonical receipt accepted"
        );
        rows.push(json!({"side":side,"quantity":q.to_string(),"usdg_amount":if side==Side::Buy{(beforecash-aftercash).to_string()}else{(aftercash-beforecash).to_string()},"gas_used":result.gas_used(),"logs":result.logs().len(),"receipt_proof_verified":true,"tampered_transfer_and_reorg_rejected":true}));
    }
    println!(
        "{}",
        json!({"symbol":p["binance_symbol"],"pool":pool.to_string(),"scope":"archived pool/provider code; synthetic ERC20 code, balances and approvals; local executor injected, not deployed","cases":rows,"access_assumptions":access_assumptions})
    );
    Ok(())
}
