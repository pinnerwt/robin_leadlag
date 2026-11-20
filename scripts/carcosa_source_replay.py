"""Decode direct CompressedOracle updates or validate the SPCX source against traces."""
import argparse
import json
from collections import Counter
from pathlib import Path

ORACLE = "0xe844701934d9c6085b292e428f41b911cc0b3872"
SOURCE = "0x0049bce28d8f04d51365cfafe2c87b1ad46873a0"
PROVIDER = "0x8a2414038ee7a77a3bb141f33ba2dc53e5ddfe50"
FEED = "0x8dfdc825dd0453e7c80b1c1d32ae910e35d6efe9000000000000000012375400"
TOPIC = "0x29e088dffd7bf6815d088137a59f364d6747163baa7ff4bc47f316a1ad1b9586"
Q64 = 1 << 64


def quote(price_e8, spread_e6):
    bid = price_e8 * Q64 * (1_000_000 - spread_e6) // 10**14
    ask = -(-price_e8 * Q64 * (1_000_000 + spread_e6) // 10**14)
    return bid, ask, price_e8 * Q64 // 10**8


def decode(log, tx, codebook):
    if (log["address"].lower() != ORACLE or log["topics"] != [TOPIC, FEED]
            or log.get("removed") or tx["hash"] != log["transactionHash"]
            or tx["to"].lower() != ORACLE):
        raise ValueError("update requires a matching accepted direct transaction")
    payload = bytes.fromhex(tx["input"][2:])
    if len(payload) < 33 or (len(payload) - 1) % 32:
        raise ValueError("unexpected compressed calldata length")
    words = [payload[i:i+32] for i in range(1, len(payload), 32)]
    slot = max((w for w in words if w[-1] == 0x54), key=lambda w: w[24:31])
    publish_ms = int.from_bytes(slot[24:31], "big")
    if slot[4:6] == b"\xff\xff":
        return dict(publish_ms=publish_ms, stalled=True)
    raw = int.from_bytes(slot[:4], "big")
    price = (raw & ((1 << 27) - 1)) << (raw >> 27)
    spread = codebook[slot[4]]
    bid, ask, mid = quote(price, spread)
    return dict(publish_ms=publish_ms, price_e8=price, spread_e6=spread,
                source_bid_x64=str(bid), source_ask_x64=str(ask), source_mid_x64=str(mid))


def calls(node):
    yield node
    for child in node.get("calls", []):
        yield from calls(child)


def values(call):
    data = call["output"][2:]
    return tuple(int(data[i:i+64], 16) for i in range(0, len(data), 64))


def verify(directory):
    counts = Counter()
    for path in sorted(directory.glob("*.json")):
        try:
            payload = json.loads(path.read_text())
            tree = list(calls(payload.get("result") or payload))
            source, provider, raw = (
                next(c for c in tree if c.get("to", "").lower() == address
                     and c.get("input", "").startswith(selector))
                for address, selector in [(SOURCE, "0x171755b1"), (PROVIDER, "0x171755b1"),
                                          (ORACLE, "0xb5e4b813" + FEED[2:])])
        except (ValueError, StopIteration):
            counts["unavailable"] += 1
            continue
        result = quote(*values(raw)[:2])
        counts["checked"] += 1
        counts["source_exact"] += result == values(source)
        counts["provider_edges_exact"] += result[:2] == values(provider)[:2]
    return counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--traces", type=Path, action="append", default=[])
    parser.add_argument("--logs", type=Path)
    parser.add_argument("--transactions", type=Path)
    args = parser.parse_args()
    if bool(args.logs) != bool(args.transactions):
        parser.error("--logs and --transactions must be given together")
    report = {"traces": {p.name: verify(p) for p in args.traces}}
    if args.logs:
        codebook = json.loads(Path(__file__).with_name("metric_spread_codebook.json").read_text())
        txs = {tx["hash"]: tx for tx in map(json.loads, args.transactions.read_text().splitlines())}
        report["updates"] = [
            dict(tx=log["transactionHash"], block=int(log["blockNumber"], 16),
                 **decode(log, txs[log["transactionHash"]], codebook))
            for log in json.loads(args.logs.read_text())]
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
