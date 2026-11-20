//! Offline bytecode-assisted decoder. Stops at external calls unless supplied
//! as getters or explicitly allowlisted proxy/route execution targets. It does NOT assert transaction success or commit state.
#[path = "../src/local_evm.rs"]
mod local_evm;
use anyhow::{Context, Result};
use revm::{
    Database, Evm, Inspector,
    interpreter::{CallInputs, CallOutcome, Gas, InstructionResult, InterpreterResult},
    primitives::{Address, Bytes, SpecId, TxKind, U256},
};
use serde_json::{Value, json};
use std::{
    io::{self, BufRead},
    str::FromStr,
};
// Research opt-in only: Cancun plus EIP-7939 is not a full later-fork model.
fn clz<H: revm::interpreter::Host + ?Sized>(
    interp: &mut revm::interpreter::Interpreter,
    _host: &mut H,
) {
    if !interp.gas.record_cost(5) {
        interp.instruction_result = InstructionResult::OutOfGas;
        return;
    }
    match interp.stack.pop() {
        Ok(value) => {
            let _ = interp.stack.push(U256::from(value.leading_zeros()));
        }
        Err(error) => interp.instruction_result = error,
    }
}

#[derive(Default)]
struct Capture {
    calls: Vec<Value>,
    trace_execution: bool,
    execution_calls: Vec<Value>,
    execution_returns: Vec<Value>,
    storage_reads: Vec<Value>,
    storage_writes: Vec<Value>,
    control_targets: Vec<String>,
    control_ops: Vec<Value>,
    math_targets: Vec<String>,
    math_ops: Vec<Value>,
    trace_hashes: bool,
    trace_calldata: bool,
    calldata_reads: Vec<Value>,
    hash_preimages: Vec<Value>,
    getters: Value,
    getter_positions: std::collections::HashMap<String, usize>,
    l2_block: u64,
    delegate_targets: Vec<String>,
    execute_targets: Vec<String>,
    execute_calls: Vec<String>,
}
impl<DB: Database> Inspector<DB> for Capture {
    fn step(
        &mut self,
        interp: &mut revm::interpreter::Interpreter,
        _ctx: &mut revm::EvmContext<DB>,
    ) {
        let pool = interp.contract.target_address;
        if matches!(interp.current_opcode(), 0x10 | 0x11 | 0x14 | 0x57)
            && self.control_ops.len() < 2048
            && self
                .control_targets
                .contains(&pool.to_string().to_lowercase())
        {
            if let (Ok(a), Ok(b)) = (interp.stack.peek(0), interp.stack.peek(1)) {
                self.control_ops.push(json!({"pc":interp.program_counter(),
                    "address":pool.to_string().to_lowercase(), "depth":_ctx.journaled_state.depth(),
                    "opcode":interp.current_opcode(), "a":a.to_string(), "b":b.to_string()}));
            }
        }
        if matches!(interp.current_opcode(), 0x02 | 0x04 | 0x06)
            && self.math_ops.len() < 2048
            && self.math_targets.contains(&pool.to_string().to_lowercase())
        {
            if let (Ok(a), Ok(b)) = (interp.stack.peek(0), interp.stack.peek(1)) {
                self.math_ops.push(json!({"pc":interp.program_counter(),"opcode":interp.current_opcode(),"a":a.to_string(),"b":b.to_string()}));
            }
        }

        if self.trace_execution
            && interp.current_opcode() == 0x55
            && self.storage_writes.len() < 4096
        {
            if let (Ok(key), Ok(value)) = (interp.stack.peek(0), interp.stack.peek(1)) {
                self.storage_writes.push(json!({"address":pool.to_string().to_lowercase(),"pc":interp.program_counter(),"slot":format!("{key:#x}"),"value":format!("{value:#x}")}));
            }
        }

        if self.trace_execution
            && interp.current_opcode() == 0x54
            && self.storage_reads.len() < 4096
        {
            if let Ok(key) = interp.stack.peek(0) {
                self.storage_reads.push(json!({"address":pool.to_string().to_lowercase(),"pc":interp.program_counter(),"slot":format!("{key:#x}"),"depth":_ctx.journaled_state.depth()}));
            }
        }
        if self.trace_calldata && interp.current_opcode() == 0x35 && self.calldata_reads.len() < 512
        {
            if let Ok(offset) = interp.stack.peek(0) {
                self.calldata_reads
                    .push(json!({"pc":interp.program_counter(), "offset":offset.to_string()}));
            }
        }

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
                        self.hash_preimages.push(json!({"pc":interp.program_counter(),"storage_address":pool.to_string().to_lowercase(),
                            "preimage":format!("0x{}",hex::encode(raw)),"hash":format!("0x{}",hex::encode(Keccak256::digest(raw)))}));
                    }
                }
            }
        }
    }

    fn step_end(
        &mut self,
        interp: &mut revm::interpreter::Interpreter,
        _ctx: &mut revm::EvmContext<DB>,
    ) {
        if self.trace_execution && interp.instruction_result == InstructionResult::OpcodeNotFound {
            self.control_ops.push(json!({"address":interp.contract.target_address.to_string().to_lowercase(), "pc_after":interp.program_counter(), "error":"OpcodeNotFound"}));
        }
    }

    fn call_end(
        &mut self,
        ctx: &mut revm::EvmContext<DB>,
        input: &CallInputs,
        outcome: CallOutcome,
    ) -> CallOutcome {
        if self.trace_execution && self.execution_returns.len() < 1024 {
            self.execution_returns.push(
                json!({"to":input.target_address.to_string().to_lowercase(),
                "selector":format!("0x{}",hex::encode(&input.input[..input.input.len().min(4)])),
                "depth":ctx.journaled_state.depth(),"result":format!("{:?}",outcome.result.result),
                "output":format!("0x{}",hex::encode(&outcome.result.output))}),
            );
        }
        outcome
    }

    fn call(
        &mut self,
        ctx: &mut revm::EvmContext<DB>,
        input: &mut CallInputs,
    ) -> Option<CallOutcome> {
        if self.trace_execution && self.execution_calls.len() < 1024 {
            self.execution_calls.push(json!({"to":input.target_address.to_string().to_lowercase(),"code":input.bytecode_address.to_string().to_lowercase(),"value":input.call_value().to_string(),"data":format!("0x{}",hex::encode(&input.input)),"depth":ctx.journaled_state.depth(),"scheme":format!("{:?}",input.scheme)}));
        }
        if ctx.journaled_state.depth() == 0 {
            return None;
        }
        let to = input.target_address.to_string().to_lowercase();
        // Explicit research allowlist: execute proxy code only until its first
        // non-getter external call. Default behavior remains unchanged.
        let code_address = input.bytecode_address.to_string().to_lowercase();
        if format!("{:?}", input.scheme) == "DelegateCall"
            && self.delegate_targets.contains(&code_address)
        {
            return None;
        }
        if matches!(
            format!("{:?}", input.scheme).as_str(),
            "Call" | "StaticCall"
        ) && (self.execute_targets.contains(&code_address)
            || self.execute_calls.contains(&format!(
                "{}:0x{}",
                code_address,
                hex::encode(&input.input)
            )))
        {
            return None;
        }
        let data = format!("0x{}", hex::encode(&input.input));
        if to == "0x0000000000000000000000000000000000000064"
            && matches!(data.as_str(), "0xa3b1b31d" | "0xd127f54a")
        {
            let n = if data == "0xa3b1b31d" {
                self.l2_block
            } else {
                4663
            };
            return Some(CallOutcome::new(
                InterpreterResult {
                    result: InstructionResult::Return,
                    output: Bytes::from(U256::from(n).to_be_bytes::<32>().to_vec()),
                    gas: Gas::new(input.gas_limit),
                },
                input.return_memory_offset.clone(),
            ));
        }
        let getter = &self.getters[&to][&data];
        let value = if let Some(sequence) = getter.as_array() {
            let position = self
                .getter_positions
                .entry(format!("{to}:{data}"))
                .or_default();
            let value = sequence.get(*position).and_then(Value::as_str);
            *position += 1;
            value
        } else {
            getter.as_str()
        };
        if let Some(value) = value {
            return Some(CallOutcome::new(
                InterpreterResult {
                    result: InstructionResult::Return,
                    output: Bytes::from(hex::decode(value.trim_start_matches("0x")).unwrap()),
                    gas: Gas::new(input.gas_limit),
                },
                input.return_memory_offset.clone(),
            ));
        }
        self.calls.push(json!({"to":to,"data":data,"caller":input.caller.to_string(),"value":input.call_value().to_string(),"scheme":format!("{:?}",input.scheme)}));
        Some(CallOutcome::new(
            InterpreterResult {
                result: InstructionResult::Revert,
                output: Bytes::new(),
                gas: Gas::new(input.gas_limit),
            },
            input.return_memory_offset.clone(),
        ))
    }
}
fn main() -> Result<()> {
    let seed: Value =
        serde_json::from_slice(&std::fs::read(std::env::args().nth(1).context("seed")?)?)?;
    let db = local_evm::State::load(&seed["accounts"])?;
    for line in io::stdin().lock().lines() {
        let tx: Value = serde_json::from_str(&line?)?;
        let from = Address::from_str(tx["from"].as_str().context("from")?)?;
        let mut state = db.clone();
        state.accounts.entry(from).or_default();
        let mut evm = Evm::builder()
            .with_db(state)
            .with_external_context(Capture {
                getters: seed["getters"].clone(),
                trace_execution: seed["trace_execution"].as_bool().unwrap_or(false),
                control_targets: seed["control_targets"]
                    .as_array()
                    .map(|v| {
                        v.iter()
                            .filter_map(|x| x.as_str().map(str::to_lowercase))
                            .collect()
                    })
                    .unwrap_or_default(),
                math_targets: seed["math_targets"]
                    .as_array()
                    .map(|v| {
                        v.iter()
                            .filter_map(|x| x.as_str().map(str::to_lowercase))
                            .collect()
                    })
                    .unwrap_or_default(),
                trace_hashes: seed["trace_hashes"].as_bool().unwrap_or(false),
                trace_calldata: seed["trace_calldata"].as_bool().unwrap_or(false),
                execute_calls: seed["execute_calls"]
                    .as_array()
                    .map(|v| {
                        v.iter()
                            .filter_map(|x| x.as_str().map(str::to_lowercase))
                            .collect()
                    })
                    .unwrap_or_default(),
                execute_targets: seed["execute_targets"]
                    .as_array()
                    .map(|v| {
                        v.iter()
                            .filter_map(|x| x.as_str().map(str::to_lowercase))
                            .collect()
                    })
                    .unwrap_or_default(),
                delegate_targets: seed["delegate_targets"]
                    .as_array()
                    .map(|v| {
                        v.iter()
                            .filter_map(|x| x.as_str().map(str::to_lowercase))
                            .collect()
                    })
                    .unwrap_or_default(),
                l2_block: tx["sequence"]
                    .as_u64()
                    .context("Nitro sequence/L2 height")?,
                ..Default::default()
            })
            .with_spec_id(SpecId::CANCUN)
            .modify_cfg_env(|c| {
                c.chain_id = 4663;
                c.disable_balance_check = true;
                c.disable_block_gas_limit = true;
                c.disable_eip3607 = true;
                c.disable_base_fee = true;
                c.disable_beneficiary_reward = true;
            })
            .modify_block_env(|b| {
                b.number = U256::from(tx["l1_block"].as_u64().unwrap_or(1));
                b.timestamp = U256::from(tx["timestamp"].as_u64().unwrap_or(1));
                b.gas_limit = U256::from(30_000_000);
                b.prevrandao = Some(Default::default());
            })
            .modify_tx_env(|t| {
                t.caller = from;
                t.transact_to =
                    TxKind::Call(Address::from_str(tx["to"].as_str().unwrap()).unwrap());
                t.data = Bytes::from(
                    hex::decode(tx["data"].as_str().unwrap().trim_start_matches("0x")).unwrap(),
                );
                t.value = U256::from_str(tx["value"].as_str().unwrap_or("0x0")).unwrap();
                t.gas_limit = 5_000_000;
                t.gas_price =
                    U256::from_str(tx["research_gas_price"].as_str().unwrap_or("0x0")).unwrap();
            })
            .append_handler_register_box(Box::new({
                let enable_clz = seed["enable_clz"].as_bool().unwrap_or(false);
                move |handler| {
                    if enable_clz {
                        handler.instruction_table.insert(0x1e, clz);
                    }
                }
            }))
            .append_handler_register(revm::inspector_handle_register)
            .build();
        let result = evm.transact();
        let error = result.as_ref().err().map(|e| e.to_string());
        let output = result
            .as_ref()
            .ok()
            .and_then(|o| local_evm::output(&o.result));
        println!(
            "{}",
            json!({"tx":tx["tx"],"calls":evm.context.external.calls,"execution_calls":evm.context.external.execution_calls,"execution_returns":evm.context.external.execution_returns,"storage_reads":evm.context.external.storage_reads,"storage_writes":evm.context.external.storage_writes,"math_ops":evm.context.external.math_ops,"control_ops":evm.context.external.control_ops,"hash_preimages":evm.context.external.hash_preimages,"calldata_reads":evm.context.external.calldata_reads,"error":error,"execution_success":result.as_ref().ok().map(|r|r.result.is_success()),"output":output,"mode":"prefix_only_no_success_claim"})
        );
    }
    Ok(())
}
