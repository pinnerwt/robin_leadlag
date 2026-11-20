# Metric raw capture checkpoint recovery

Run `python3 scripts/capture_metric_session.py captures/<unique-name> --seconds 86400`.
Settings are in `config/checkpoint-recovery.json`. Normal capture only consumes
WebSocket pushes. RPC is used for startup/recovery snapshots, outside the decision
path. This supervisor records raw inputs; it does not run a live quote consumer.

A chain/Nitro disconnect, sequence gap, conflicting head, or removed log invalidates
the current generation immediately. Recording continues. A redundant Binance
connection failure does not invalidate pool state. An in-flight snapshot from an
older generation is discarded. Recovery pins one block B and refreshes known
account code, balances, nonces and storage at B. It verifies pool immutables and
compares local EVM provider/swap outputs against fresh RPC fixtures, including
0.02 tokens, 0.1 tokens and approximately 500 USDG token quantity in both directions.
The large seed fixture is retained for compatibility with checkpoint validation.

The known-slot backend needs no tracing API or full Nitro node. It is sparse:
missing slots reported by local EVM quote validation are fetched at the same block
(up to 32 rounds / 256 slots). Unknown accounts and non-slot mismatches fail. Other
unexercised dependencies are not discovered automatically. Exact parity at
tested sizes does not prove arbitrary future execution parity. Failed parity
never publishes a checkpoint. Public RPC limits can make recovery take minutes;
bounded retries and timeouts leave the session unavailable if recovery fails.

`checkpoint-recovery.json` and `status.json` identify the current phase, checkpoint,
and historical intervals. The compressed binary tape also stores
`checkpoint_recovery` markers. Snapshot files are generation-specific. `replay_ready`
means the verified snapshot anchor matches pushed head and Nitro block hashes and
has a contiguous subsequent buffer. It does **not** mean a live consumer has
applied the buffer: `state_valid` and `decision_ready` remain false.

A replay consumer must load the selected generation checkpoint after block B,
skip state events at or below B, apply subsequent events in block/transaction/log
order, and stop at the next invalidation. It must not join across gaps using the
old snapshot, or backdate availability of a recovery snapshot. A future live
consumer must explicitly acknowledge catch-up before enabling decisions. Existing
single-checkpoint backtests do not automatically consume these multiple intervals.

For a bounded fault-injection test, send SIGUSR1 only to the test session's relay
PID (`status.json: children.relay`). The relay closes its downstream sockets and
stays running; the capture should reconnect and create a new generation. SIGTERM
to the capture supervisor stops cleanly and finalizes the compressed binary tape.
