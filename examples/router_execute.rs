//! Offline full-call dependency experiment. No external-call interception except
//! two ArbSys getters. No networking and no production-equivalence claim.
//! Default: independent probes. --commit: stop on the first execution error.
#[path = "../src/arbos_block.rs"]
mod arbos_block;
#[path = "../src/arbos_deposit.rs"]
mod arbos_deposit;
#[path = "../src/arbos_report.rs"]
mod arbos_report;
#[path = "../src/arbos_units.rs"]
mod arbos_units;
#[path = "../src/local_evm.rs"]
mod local_evm;
use anyhow::{Context, Result};
use revm::{
    Database, DatabaseCommit, Evm, Inspector,
    interpreter::{CallInputs, CallOutcome, Gas, InstructionResult, InterpreterResult},
    primitives::{Address, Bytes, SpecId, TxKind, U256},
};
use serde_json::{Value, json};
use std::{
    collections::HashSet,
    io::{self, BufRead},
    str::FromStr,
};
#[derive(Default)]
struct Capture {
    calls: Vec<Value>,
    l2_block: u64,
    unsupported_precompile: Option<String>,
    v3_pools: HashSet<Address>,
    mapping_preimages: Vec<Value>,
    mapping_seen: HashSet<(Address, U256)>,
    trace_hashes: bool,
    hash_preimages: Vec<Value>,
}
impl<DB: Database> Inspector<DB> for Capture {
    fn step(
        &mut self,
        interp: &mut revm::interpreter::Interpreter,
        _ctx: &mut revm::EvmContext<DB>,
    ) {
        let pool = interp.contract.target_address;
        if self.trace_hashes && interp.current_opcode() == 0x20 && self.hash_preimages.len() < 256 {
            if let (Ok(offset), Ok(size)) = (interp.stack.peek(0), interp.stack.peek(1)) {
                if let (Ok(offset), Ok(size)) = (usize::try_from(offset), usize::try_from(size)) {
                    if size <= 1024
                        && offset
                            .checked_add(size)
                            .is_some_and(|end| end <= interp.shared_memory.len())
                    {
                        use sha3::{Digest, Keccak256};
                        let raw = interp.shared_memory.slice(offset, size);
                        self.hash_preimages.push(json!({"storage_address":pool.to_string().to_lowercase(),
                            "preimage":format!("0x{}",hex::encode(raw)),"hash":format!("0x{}",hex::encode(Keccak256::digest(raw)))}));
                    }
                }
            }
        }
        if interp.current_opcode() != 0x20 || !self.v3_pools.contains(&pool) {
            return;
        }
        let (Ok(offset), Ok(size)) = (interp.stack.peek(0), interp.stack.peek(1)) else {
            return;
        };
        if size != U256::from(64) {
            return;
        }
        let Ok(offset) = usize::try_from(offset) else {
            return;
        };
        if offset
            .checked_add(64)
            .is_none_or(|end| end > interp.shared_memory.len())
        {
            return;
        }
        let raw = interp.shared_memory.slice(offset, 64);
        let slot = U256::from_be_slice(&raw[32..]);
        if ![U256::from(5), U256::from(6), U256::from(7)].contains(&slot) {
            return;
        }
        use sha3::{Digest, Keccak256};
        let key = U256::from_be_slice(&Keccak256::digest(raw));
        if self.mapping_seen.insert((pool, key)) {
            self.mapping_preimages.push(json!({"pool":pool.to_string().to_lowercase(),"slot":slot.to::<u64>(),"index":format!("0x{}",hex::encode(&raw[..32])),"key":format!("{key:#x}")}));
        }
    }

    fn call(
        &mut self,
        ctx: &mut revm::EvmContext<DB>,
        input: &mut CallInputs,
    ) -> Option<CallOutcome> {
        let to = input.target_address.to_string().to_lowercase();
        let data = format!("0x{}", hex::encode(&input.input));
        if to == "0x0000000000000000000000000000000000000064"
            && input.bytecode_address == input.target_address
            && input.call_value() == U256::ZERO
            && matches!(data.as_str(), "0xa3b1b31d" | "0xd127f54a")
        {
            let n = if data == "0xa3b1b31d" {
                self.l2_block
            } else {
                4663
            };
            let mut gas = Gas::new(input.gas_limit);
            let affordable = gas.record_cost(803); // ArbOS version SLOAD (800) + one output word (3)
            if !affordable {
                gas.spend_all();
            }
            return Some(CallOutcome::new(
                InterpreterResult {
                    result: if affordable {
                        InstructionResult::Return
                    } else {
                        InstructionResult::PrecompileOOG
                    },
                    output: Bytes::from(U256::from(n).to_be_bytes::<32>().to_vec()),
                    gas,
                },
                input.return_memory_offset.clone(),
            ));
        }
        let address = input.bytecode_address.as_slice();
        if address[..19].iter().all(|b| *b == 0) && address[19] >= 0x64 {
            self.unsupported_precompile = Some(format!(
                "unsupported Arbitrum precompile {} selector {}",
                input.bytecode_address, data
            ));
        }
        if ctx.journaled_state.depth() == 0 {
            return None;
        }
        self.calls.push(json!({"to":to,"code_address":input.bytecode_address.to_string().to_lowercase(),"data":data,"caller":input.caller.to_string(),"scheme":format!("{:?}",input.scheme)}));
        None
    }
}
fn main() -> Result<()> {
    let seed: Value =
        serde_json::from_slice(&std::fs::read(std::env::args().nth(1).context("seed")?)?)?;
    let commit = std::env::args().any(|s| s == "--commit");
    let trace_hashes = std::env::args().any(|s| s == "--trace-hashes");
    let units_mode =
        std::env::args().find_map(|s| s.strip_prefix("--units-mode=").map(str::to_owned));
    anyhow::ensure!(
        units_mode
            .as_deref()
            .is_none_or(|s| s == "probe" || s == "signed"),
        "invalid units mode"
    );
    let block_mode = std::env::args().any(|s| s == "--block-mode");
    let require_filter_state = std::env::args().any(|s| s == "--require-filter-state");
    anyhow::ensure!(
        !require_filter_state || block_mode,
        "filter gate requires block mode"
    );
    anyhow::ensure!(
        !block_mode || (commit && units_mode.as_deref() == Some("signed")),
        "block mode requires signed commit"
    );
    let mut parent = seed["parent_header"].clone();
    anyhow::ensure!(
        !block_mode || parent.is_object(),
        "block mode requires parent_header checkpoint"
    );
    let mut active: Option<Value> = None;
    let mut remaining = 0u64;
    let mut local_fee = U256::ZERO;
    let quantity = |v: &Value| -> Result<u64> {
        match v {
            Value::String(s) => Ok(u64::from_str_radix(s.trim_start_matches("0x"), 16)?),
            _ => v.as_u64().context("block quantity"),
        }
    };
    let v3_pools: HashSet<Address> = seed["pools"]
        .as_array()
        .into_iter()
        .flatten()
        .map(|p| Address::from_str(p["pool"].as_str().unwrap()))
        .collect::<std::result::Result<_, _>>()?;
    let mut db = local_evm::State::load(&seed["accounts"])?;
    for line in io::stdin().lock().lines() {
        let mut tx: Value = serde_json::from_str(&line?)?;
        if block_mode {
            match tx["kind"].as_str() {
                Some("feed_block") => {
                    anyhow::ensure!(remaining == 0, "incomplete previous block transactions");
                    let number = quantity(&tx["sequence"])?;
                    anyhow::ensure!(
                        number == quantity(&parent["number"])? + 1,
                        "block sequence discontinuity"
                    );
                    // Nitro createNewHeader clamps delayed-message timestamps
                    // to the previous L2 header's time.
                    let block_timestamp =
                        quantity(&tx["timestamp"])?.max(quantity(&parent["timestamp"])?);
                    let (fee, writes) = arbos_block::start(
                        &db,
                        number,
                        block_timestamp,
                        quantity(&parent["timestamp"])?,
                        quantity(&tx["l1_block"])?,
                        revm::primitives::B256::from_str(
                            parent["hash"].as_str().context("parent hash")?,
                        )?,
                    )?;
                    let mut block_writes = json!({});
                    for ((address, key), value) in &writes {
                        block_writes[address.to_string().to_lowercase()][format!("{key:#x}")] =
                            json!(format!("{value:#x}"));
                    }
                    for (key, value) in writes {
                        db.slots.insert(key, value);
                    }
                    local_fee = fee;
                    remaining = quantity(&tx["transaction_count"])?;
                    parent = json!({"number":number,"timestamp":block_timestamp,"hash":tx["block_hash"]});
                    println!(
                        "{}",
                        json!({"kind":"block_state","checkpoint_hash":seed["anchor"]["hash"],"sequence":number,"block_hash":tx["block_hash"],"block_base_fee":format!("{fee:#x}"),"changed_storage":block_writes,"executable":false,"context_source":"nitro_push_and_initial_checkpoint"})
                    );
                    active = Some(tx);
                    continue;
                }
                Some("feed_tx") | Some("feed_system_tx") => {
                    let b = active.as_ref().context("transaction before block marker")?;
                    anyhow::ensure!(
                        remaining > 0
                            && tx["sequence"] == b["sequence"]
                            && tx["block_hash"] == b["block_hash"]
                            && tx["timestamp"] == b["timestamp"]
                            && tx["l1_block"] == b["l1_block"],
                        "transaction block context mismatch"
                    );
                    remaining -= 1;
                    tx["block_base_fee"] = json!(format!("{local_fee:#x}"));
                    tx["message_timestamp"] = tx["timestamp"].clone();
                    tx["timestamp"] = parent["timestamp"].clone();
                }
                _ => anyhow::bail!(
                    "block-mode input must contain only feed_block/feed_tx/feed_system_tx"
                ),
            }
        }
        if tx["kind"] == "feed_system_tx" {
            anyhow::ensure!(block_mode, "system transaction requires block mode");
            let (next, filtered) = if tx["system_kind"] == "eth_deposit" {
                let (next, filtered, _) = arbos_deposit::apply(&db, &tx)?;
                (next, filtered)
            } else {
                (
                    arbos_report::apply(&db, &tx, quantity(&tx["timestamp"])?)?,
                    false,
                )
            };
            let mut storage = json!({});
            let mut accounts = json!({});
            for ((address, key), value) in &next.slots {
                if db.slots.get(&(*address, *key)) != Some(value) {
                    storage[address.to_string().to_lowercase()][format!("{key:#x}")] =
                        json!(format!("{value:#x}"));
                }
            }
            for (address, account) in &next.accounts {
                if db.accounts.get(address).map(|a| a.balance) != Some(account.balance) {
                    accounts[address.to_string().to_lowercase()] = json!({"balance":format!("{:#x}",account.balance),"nonce":account.nonce,"destroyed":false});
                }
            }
            db = next;
            println!(
                "{}",
                json!({"kind":"system_state","checkpoint_hash":seed["anchor"]["hash"],
                "sequence":tx["sequence"],"system_kind":tx["system_kind"],"timestamp":tx["timestamp"],
                "recv_ns":tx["recv_ns"],"mono_ns":tx["mono_ns"],"changed_storage":storage,"accounts":accounts,
                "committed":true,"success":!filtered,"filtered":filtered,"error":null,"production_ready":false})
            );
            continue;
        }
        if require_filter_state {
            anyhow::ensure!(
                !arbos_deposit::transaction_filtered(
                    &db,
                    tx["tx"].as_str().context("transaction hash")?
                )?,
                "filtered ordinary transaction execution unsupported; state not committed"
            );
        }
        let from = Address::from_str(tx["from"].as_str().context("from")?)?;
        let execution_started = std::time::Instant::now();
        let units_update = if let Some(mode) = &units_mode {
            let (a, k, old, quality) = arbos_units::parameters(&db)?;
            Some((
                a,
                k,
                old.wrapping_add(arbos_units::increment(&tx, quality, mode == "probe")?),
            ))
        } else {
            None
        };
        let basefee = if units_mode.as_deref() == Some("signed") {
            U256::from_str(
                tx["block_base_fee"]
                    .as_str()
                    .context("signed execution requires locally reconstructed block base fee")?,
            )?
        } else {
            U256::ZERO
        };
        let fee_recipients = if units_mode.as_deref() == Some("signed") {
            anyhow::ensure!(
                U256::from_str(tx["max_fee_per_gas"].as_str().context("max fee")?)? >= basefee,
                "fee cap below block base fee"
            );
            arbos_units::fee_recipients(&db, basefee)?
        } else {
            Vec::new()
        };
        // Never invent a caller account or its balance.
        let mut evm = Evm::builder()
            // Database reads do not mutate State. REVM journals writes until
            // we explicitly commit the returned outcome below.
            .with_db(&mut db)
            .with_external_context(Capture {
                v3_pools: v3_pools.clone(),
                trace_hashes,
                l2_block: tx["sequence"]
                    .as_u64()
                    .context("Nitro sequence/L2 height")?,
                ..Default::default()
            })
            .with_spec_id(SpecId::CANCUN)
            .modify_cfg_env(|c| {
                c.chain_id = 4663;
                c.disable_balance_check = false;
                c.disable_block_gas_limit = true;
                c.disable_eip3607 = false;
                c.disable_base_fee = true;
                c.disable_beneficiary_reward = true;
            })
            .modify_block_env(|b| {
                b.number = U256::from(tx["l1_block"].as_u64().unwrap_or(1));
                b.timestamp = U256::from(tx["timestamp"].as_u64().unwrap_or(1));
                b.gas_limit = U256::from(30_000_000);
                b.prevrandao = Some(Default::default());
                b.basefee = basefee;
            })
            .modify_tx_env(|t| {
                t.caller = from;
                t.gas_price = basefee;
                t.transact_to = match tx["to"].as_str() {
                    Some(a) => TxKind::Call(Address::from_str(a).unwrap()),
                    None => TxKind::Create,
                };
                t.data = Bytes::from(
                    hex::decode(tx["data"].as_str().unwrap().trim_start_matches("0x")).unwrap(),
                );
                t.value = U256::from_str(tx["value"].as_str().unwrap_or("0x0")).unwrap();
                t.gas_limit = tx["gas_limit"].as_u64().unwrap_or(30_000_000);
                t.nonce = tx["nonce"].as_u64();
            })
            .append_handler_register(revm::inspector_handle_register)
            .build();
        evm.context
            .evm
            .journaled_state
            .warm_preloaded_addresses
            .insert(Address::from_str(
                "0x0000000000000000000000000000000000000064",
            )?);
        let mut result = evm.transact();
        let capture = std::mem::take(&mut evm.context.external);
        drop(evm);
        anyhow::ensure!(
            capture.unsupported_precompile.is_none(),
            "{}",
            capture
                .unsupported_precompile
                .as_deref()
                .unwrap_or("unsupported precompile")
        );
        if let Ok(outcome) = &mut result {
            let gas = U256::from(outcome.result.gas_used());
            for (receiver, rate) in fee_recipients {
                if rate == U256::ZERO {
                    continue;
                }
                let account = outcome.state.entry(receiver).or_insert_with(|| {
                    revm::primitives::Account::from(db.accounts[&receiver].clone())
                });
                account.mark_touch();
                account.info.balance = account
                    .info
                    .balance
                    .checked_add(rate.checked_mul(gas).context("fee overflow")?)
                    .context("fee balance overflow")?;
            }
        }
        let success = result.as_ref().ok().map(|o| o.result.is_success());
        let logs: Vec<Value> = result.as_ref().ok().map(|o| o.result.logs().iter().map(|l| json!({"address":l.address.to_string(),"topics":l.data.topics().iter().map(|t|format!("{t:#x}")).collect::<Vec<_>>(),"data":format!("0x{}",hex::encode(&l.data.data))})).collect()).unwrap_or_default();
        let gas_used = result.as_ref().ok().map(|o| o.result.gas_used());
        let mut accounts = serde_json::Map::new();
        let mut storage = serde_json::Map::new();
        if let Ok(outcome) = &result {
            for (address, account) in &outcome.state {
                if account.is_touched() {
                    accounts.insert(address.to_string().to_lowercase(),json!({"balance":format!("{:#x}",account.info.balance),"nonce":account.info.nonce,"destroyed":account.is_selfdestructed()}));
                }
                let slots: serde_json::Map<String, Value> = account
                    .storage
                    .iter()
                    .filter(|(_, value)| value.is_changed())
                    .map(|(key, value)| {
                        (
                            format!("{key:#x}"),
                            json!(format!("{:#x}", value.present_value())),
                        )
                    })
                    .collect();
                if !slots.is_empty() {
                    storage.insert(address.to_string().to_lowercase(), Value::Object(slots));
                }
            }
        }
        let backlog = if result.is_ok() && units_mode.as_deref() == Some("signed") {
            arbos_units::grow_backlog(&db, gas_used.context("gas used")?)?
        } else {
            Vec::new()
        };
        if result.is_ok() {
            if let Some((a, k, new)) = units_update {
                storage.insert(
                    a.to_string().to_lowercase(),
                    json!({format!("{k:#x}"):format!("0x{new:x}")}),
                );
            }
        }
        if !backlog.is_empty() {
            let target = storage
                .get_mut(arbos_units::ACCOUNT)
                .context("units write missing")?
                .as_object_mut()
                .unwrap();
            for (k, v) in &backlog {
                target.insert(format!("{k:#x}"), json!(format!("{v:#x}")));
            }
        }
        let error = result.as_ref().err().map(|e| e.to_string());
        let output = result
            .as_ref()
            .ok()
            .and_then(|o| local_evm::output(&o.result));
        println!(
            "{}",
            json!({"checkpoint_hash":seed["anchor"]["hash"],"sequence":tx["sequence"],"timestamp":tx["timestamp"],"recv_ns":tx["recv_ns"],"mono_ns":tx["mono_ns"],"tx":tx["tx"],"calls":capture.calls,"hash_preimages":capture.hash_preimages,"error":error,"output":output,"success":success,"logs":logs,"changed_storage":storage,"mapping_preimages":capture.mapping_preimages,"accounts":accounts,"gas_used":gas_used,"local_compute_ns":execution_started.elapsed().as_nanos(),"mode":"full_call_experiment_not_nitro_equivalent","units_mode":units_mode,"native_filter_checked":require_filter_state,"committed":commit && error.is_none(),"production_ready":false})
        );
        if commit {
            let outcome = result.map_err(|e| anyhow::anyhow!("strict continuity stopped: {e}"))?;
            db.commit(outcome.state);
            for (k, v) in backlog {
                db.slots
                    .insert((Address::from_str(arbos_units::ACCOUNT)?, k), v);
            }
            if let Some((a, k, new)) = units_update {
                db.slots.insert((a, k), U256::from(new));
            }
        }
    }
    anyhow::ensure!(!block_mode || remaining == 0, "truncated final block");
    Ok(())
}
