//! Strict offline EVM: an absent slot is an error, never an implicit zero/RPC read.
use anyhow::{Context, Result, ensure};
use revm::{
    Database, DatabaseCommit, Evm,
    primitives::{
        Account, AccountInfo, Address, B256, Bytecode, Bytes, ExecutionResult, HashMap, SpecId,
        TxKind, U256,
    },
};
use serde_json::Value;
use std::{
    collections::{HashMap as Map, HashSet},
    io,
    str::FromStr,
};

#[derive(Clone, Default)]
pub struct State {
    pub accounts: Map<Address, AccountInfo>,
    // Other reducers changed these accounts without exporting their full EVM state.
    pub unavailable_accounts: HashSet<Address>,
    pub slots: Map<(Address, U256), U256>,
    // Only populated by a root-verified, complete startup trie snapshot.
    pub complete_hashed_storage: Map<Address, Map<B256, U256>>,
    codes: Map<B256, Bytecode>,
    pub last_quote: Option<Vec<u8>>,
    pub trace_reads: bool,
    pub price_cursors: Map<Address, (u64, u64, u64)>,
}
fn missing(s: String) -> io::Error {
    io::Error::new(io::ErrorKind::NotFound, s)
}
pub fn uint(s: &str) -> Result<U256> {
    Ok(U256::from_str(s)?)
}
impl State {
    pub fn known_storage(&self, address: Address, key: U256) -> Option<U256> {
        self.slots.get(&(address, key)).copied().or_else(|| {
            self.complete_hashed_storage.get(&address).map(|entries| {
                let hash = revm::primitives::keccak256(key.to_be_bytes::<32>());
                entries.get(&hash).copied().unwrap_or(U256::ZERO)
            })
        })
    }
    pub fn load(value: &Value) -> Result<Self> {
        let mut db = Self::default();
        for (a, v) in value.as_object().context("accounts object")? {
            let address = Address::from_str(a)?;
            let code = Bytecode::new_raw(Bytes::from(hex::decode(
                v["code"].as_str().unwrap_or("0x").trim_start_matches("0x"),
            )?));
            let code = revm::interpreter::analysis::to_analysed(code);
            let hash = code.hash_slow();
            let info = AccountInfo::new(
                uint(v["balance"].as_str().unwrap_or("0x0"))?,
                match &v["nonce"] {
                    Value::Null => 0,
                    Value::String(s) => uint(s)?.try_into().context("nonce overflow")?,
                    n => n.as_u64().context("invalid nonce")?,
                },
                hash,
                code.clone(),
            );
            db.codes.insert(hash, code);
            db.accounts.insert(address, info);
            if let Some(entries) = v["complete_hashed_storage"].as_object() {
                let mut hashed = Map::new();
                for (k, v) in entries {
                    hashed.insert(
                        B256::from_str(k)?,
                        uint(v.as_str().context("hashed storage value")?)?,
                    );
                }
                db.complete_hashed_storage.insert(address, hashed);
            }
            if let Some(slots) = v["storage"].as_object() {
                for (k, v) in slots {
                    db.slots.insert(
                        (address, uint(k)?),
                        uint(v.as_str().context("slot value")?)?,
                    );
                }
            }
        }
        Ok(db)
    }
    pub fn run(&mut self, header: &Value, call: &Value, commit: bool) -> Result<ExecutionResult> {
        self.run_mode(header, call, commit, false)
    }
    pub fn run_mode(
        &mut self,
        header: &Value,
        call: &Value,
        commit: bool,
        persist_simulation: bool,
    ) -> Result<ExecutionResult> {
        ensure!(
            !persist_simulation
                || call["data"]
                    .as_str()
                    .is_some_and(|s| s.starts_with("0x658b6cb7")),
            "persist is restricted to simulateSwapAndRevert"
        );
        let block_number = uint(
            header["l1BlockNumber"]
                .as_str()
                .context("missing L1 block context")?,
        )?;
        let timestamp = uint(header["timestamp"].as_str().context("missing timestamp")?)?;
        let caller = Address::from_str(
            call["from"]
                .as_str()
                .unwrap_or("0x0000000000000000000000000000000000000000"),
        )?;
        // Caller account is a simulation context, not inferred contract storage.
        self.accounts.entry(caller).or_default();
        let mut evm = Evm::builder()
            .with_db(&mut *self)
            .with_external_context(SimulationExit {
                enabled: persist_simulation,
                trace: call["trace"].as_bool().unwrap_or(false),
                ..Default::default()
            })
            .with_spec_id(SpecId::CANCUN)
            .modify_cfg_env(|cfg| {
                cfg.chain_id = 4663;
                cfg.disable_balance_check = true;
                cfg.disable_block_gas_limit = true;
                cfg.disable_eip3607 = true;
                cfg.disable_base_fee = true;
                cfg.disable_beneficiary_reward = true;
            })
            .modify_block_env(|block| {
                block.number = block_number;
                block.timestamp = timestamp;
                block.gas_limit = uint(header["gasLimit"].as_str().unwrap_or("0x1c9c380")).unwrap();
                block.basefee = uint(header["baseFeePerGas"].as_str().unwrap_or("0x0")).unwrap();
                block.coinbase = Address::from_str(
                    header["miner"]
                        .as_str()
                        .unwrap_or("0x0000000000000000000000000000000000000000"),
                )
                .unwrap();
                block.prevrandao = Some(B256::ZERO);
            })
            .modify_tx_env(|tx| {
                tx.caller = caller;
                tx.transact_to =
                    TxKind::Call(Address::from_str(call["to"].as_str().unwrap()).unwrap());
                tx.data = Bytes::from(
                    hex::decode(call["data"].as_str().unwrap().trim_start_matches("0x")).unwrap(),
                );
                tx.gas_limit = 30_000_000;
                tx.gas_price = U256::ZERO;
                tx.value = U256::ZERO;
                tx.nonce = None;
            })
            .append_handler_register(revm::inspector_handle_register)
            .build();
        let outcome = evm.transact().map_err(|e| anyhow::anyhow!("{e}"))?;
        evm.context.evm.db.last_quote = evm.context.external.quote.clone();
        if commit && outcome.result.is_success() {
            evm.context.evm.db.commit(outcome.state);
        }
        Ok(outcome.result)
    }
}
impl Database for State {
    type Error = io::Error;
    fn basic(&mut self, address: Address) -> std::result::Result<Option<AccountInfo>, Self::Error> {
        if self.unavailable_accounts.contains(&address) {
            return Err(missing(format!(
                "unsynchronized upstream account {address}"
            )));
        }
        if let Some(info) = self.accounts.get(&address) {
            return Ok(Some(info.clone()));
        }
        Err(missing(format!("unknown account {address}")))
    }
    fn code_by_hash(&mut self, hash: B256) -> std::result::Result<Bytecode, Self::Error> {
        self.codes
            .get(&hash)
            .cloned()
            .ok_or_else(|| missing(format!("unknown code {hash}")))
    }
    fn storage(&mut self, address: Address, index: U256) -> std::result::Result<U256, Self::Error> {
        if self.unavailable_accounts.contains(&address) {
            return Err(missing(format!(
                "unsynchronized upstream storage {address}"
            )));
        }
        if self.trace_reads { eprintln!("storage {address} {index:#x}"); }
        self.known_storage(address, index)
            .ok_or_else(|| missing(format!("unknown slot {address} {index:#x}")))
    }
    fn block_hash(&mut self, number: u64) -> std::result::Result<B256, Self::Error> {
        Err(missing(format!("unseeded blockhash {number}")))
    }
}
impl DatabaseCommit for State {
    fn commit(&mut self, changes: HashMap<Address, Account>) {
        for (address, account) in changes {
            if !account.is_touched() {
                continue;
            }
            if account.is_selfdestructed() {
                self.accounts.remove(&address);
                self.slots.retain(|(a, _), _| *a != address);
                self.complete_hashed_storage.remove(&address);
                continue;
            }
            if let Some(code) = &account.info.code {
                self.codes.insert(account.info.code_hash, code.clone());
            }
            self.accounts.insert(address, account.info);
            for (key, value) in account.storage {
                self.slots.insert((address, key), value.present_value());
            }
        }
    }
}
// Only the outer known simulation success sentinel is converted. Real reverts stay reverts.
#[derive(Default)]
struct SimulationExit {
    enabled: bool,
    trace: bool,
    quote: Option<Vec<u8>>,
}
impl<DB: Database> revm::Inspector<DB> for SimulationExit {
    fn call_end(
        &mut self,
        _context: &mut revm::EvmContext<DB>,
        inputs: &revm::interpreter::CallInputs,
        outcome: revm::interpreter::CallOutcome,
    ) -> revm::interpreter::CallOutcome {
        if self.trace { eprintln!("call {:?} {} {} input=0x{} output=0x{}", inputs.scheme, inputs.target_address, inputs.bytecode_address, hex::encode(&inputs.input), hex::encode(&outcome.result.output)); }
        if inputs.input.as_ref() == [0x17, 0x17, 0x55, 0xb1]
            && outcome.result.result.is_ok()
            && outcome.result.output.len() == 96
        {
            self.quote = Some(outcome.result.output.to_vec());
        }
        outcome
    }
    fn step_end(
        &mut self,
        interp: &mut revm::interpreter::Interpreter,
        context: &mut revm::EvmContext<DB>,
    ) {
        use revm::interpreter::{InstructionResult, InterpreterAction};
        if !self.enabled || context.journaled_state.depth() != 1 {
            return;
        }
        if let InterpreterAction::Return { result } = &mut interp.next_action {
            if result.result == InstructionResult::Revert
                && result.output.len() == 68
                && result.output[..4] == [0x1f, 0x60, 0x53, 0xde]
            {
                result.result = InstructionResult::Return;
                interp.instruction_result = InstructionResult::Return;
            }
        }
    }
}
pub fn output(result: &ExecutionResult) -> Option<String> {
    result.output().map(|b| format!("0x{}", hex::encode(b)))
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;
    #[test]
    fn only_simulation_success_sentinel_can_commit() {
        let a = "0x1111111111111111111111111111111111111111";
        let initial = serde_json::json!({a:{"code":"0x6001600055631f6053de60e01b60005260446000fd","storage":{"0x0":"0x0"}}});
        let mut db = State::load(&initial).unwrap();
        let h = serde_json::json!({"l1BlockNumber":"0x1","timestamp":"0x1"});
        let c = serde_json::json!({"to":a,"data":"0x658b6cb7"});
        assert!(!db.run(&h, &c, true).unwrap().is_success());
        assert_eq!(
            db.slots[&(Address::from_str(a).unwrap(), U256::ZERO)],
            U256::ZERO
        );
        assert!(db.run_mode(&h, &c, true, true).unwrap().is_success());
        assert_eq!(
            db.slots[&(Address::from_str(a).unwrap(), U256::ZERO)],
            U256::from(1)
        );
        let mut bad = initial.clone();
        bad[a]["code"] = serde_json::json!("0x600160005563aabbccdd60e01b60005260446000fd");
        let mut db = State::load(&bad).unwrap();
        assert!(!db.run_mode(&h, &c, true, true).unwrap().is_success());
        assert_eq!(
            db.slots[&(Address::from_str(a).unwrap(), U256::ZERO)],
            U256::ZERO
        );
    }

    #[test]
    fn upstream_account_barrier_rejects_even_seeded_state() {
        let a = Address::from_str("0x1111111111111111111111111111111111111111").unwrap();
        let mut db =
            State::load(&json!({a.to_string():{"code":"0x00","storage":{"0x0":"0x1"}}})).unwrap();
        assert!(db.basic(a).unwrap().is_some());
        db.unavailable_accounts.insert(a);
        assert!(
            db.basic(a)
                .unwrap_err()
                .to_string()
                .contains("unsynchronized")
        );
        assert!(
            db.storage(a, U256::ZERO)
                .unwrap_err()
                .to_string()
                .contains("unsynchronized")
        );
        assert!(db.clone().unavailable_accounts.contains(&a));
    }

    #[test]
    fn missing_storage_fails_closed_and_explicit_zero_succeeds() {
        let a = "0x1111111111111111111111111111111111111111";
        let mut db = State::load(&json!({a:{"code":"0x60005460005260206000f3"}})).unwrap();
        let header = json!({"l1BlockNumber":"0x1","timestamp":"0x1"});
        let call = json!({"to":a,"data":"0x"});
        assert!(
            db.run(&header, &call, false)
                .unwrap_err()
                .to_string()
                .contains("unknown slot")
        );
        db.slots
            .insert((Address::from_str(a).unwrap(), U256::ZERO), U256::ZERO);
        let result = db.run(&header, &call, false).unwrap();
        assert!(result.is_success());
        assert_eq!(result.output().unwrap().len(), 32);
    }
}
