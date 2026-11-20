#[path = "../trading/mod.rs"]
mod trading;
use anyhow::{Context, Result};
#[tokio::main(worker_threads = 2)]
async fn main() -> Result<()> {
    let mut args = std::env::args().skip(1);
    let path = args
        .next()
        .context("usage: metric-trader CONFIG [--check-config]")?;
    let c = trading::config::Config::load(std::path::Path::new(&path))?;
    let action=args.next();
    if action.as_deref()==Some("--check-credentials") {
        let credentials=c.credentials()?;
        let wallet=credentials.key.as_ref().map(robin_leadlag::execution::codec::wallet).map(|a|format!("0x{}",hex::encode(a)));
        println!("{}",serde_json::json!({"wallet":wallet,"initial_base_raw":credentials.baseline.initial_base,"declared_hedge_raw":credentials.baseline.declared_exchange_short}));
        return Ok(());
    }
    if action.as_deref() == Some("--check-config") {
        println!(
            "configuration valid: B89, 100 USDG additional cap, {:?}",
            c.mode
        );
        return Ok(());
    }
    trading::run(c).await
}
