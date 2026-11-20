"""Speculative V3 spot price from Nitro feed calldata, ahead of pushed logs.

The base (sqrtPrice, liquidity) is always the newest Swap log of the pool; a
Swap log is a fact about the pool after that swap, so it needs no barrier.
Feed transactions the log stream has not passed yet are decoded and folded
over the base in sequencer order:

* decoded swap, price not yet past its limit -> move to min(full move, limit)
* decoded swap, price already past its limit -> the pool reverts (SPL): no move
* known toucher that cannot be decoded -> `uncertain` until logs pass it
* everything else -> ignored; its log corrects the base when it arrives

Every prediction is scored when the log stream passes its transaction. `log`
returns True on a surprise (mismatch, undecoded touch) so the caller can
schedule a background pinned RPC check; nothing here blocks or does I/O.
Liquidity is the last logged value, so a move across an initialized tick is
approximate until its log arrives.

Offline scoring against a recorder tape extract:
    python3 scripts/v3_feed_overlay.py replay TAPE.jsonl [REGISTRY [TOUCHERS]]
"""
import collections
import json
import os
import sys

from v3_calldata import decode
from v3_state import next_price, tick_sqrt

SWAP = '0xc42079f94a6350d7e6235f29174924f928cc2ac818eb64fed8004e115fbcca67'
MIN_SQRT, MAX_SQRT = 4295128739, 1461446703485210103287273052203988822378723970342
HOP_ROUTERS = {'0x65050a9b7e5075a2ba5ced7b1b64ee66262c40dc': '4d819a2a'}


def _signed(h):
    v = int(h, 16)
    return v - (1 << 256) if v >> 255 else v


def parse_swap(log):
    d = log['data'][2:]
    if len(d) != 320:
        raise ValueError('V3 Swap data length')
    return dict(sqrt=int(d[128:192], 16), liquidity=int(d[192:256], 16), tick=_signed(d[256:320]))


def hop_route(to, data, pools):
    """Aggregator hop list (unverified layout, scored against logs): only a
    first-hop exact-input V3 swap has an amount known from calldata; a tracked
    pool on a later hop raises so the transaction is marked unknown."""
    if HOP_ROUTERS.get(to) != data[2:10]:
        return None
    w = [int(data[i:i + 64], 16) for i in range(10, len(data) - 63, 64)]
    base = w[0] // 32
    ops = []
    for i in range(w[base]):
        hop = base + 1 + w[base + 1 + i] // 32
        kind, token_in, pool = w[hop], w[hop + 1], '0x' + format(w[hop + 3], '040x')
        if pool not in pools:
            continue
        if i or kind != 1 or not 0 < w[2] < 1 << 255:
            raise ValueError('hop route amount not known from calldata')
        ops.append(dict(kind='swap', pool=pool, zero='0x' + format(token_in, '040x') == pools[pool]['tokens'][0],
                        amount=w[2], limit=None, constraint=None, decoder='hop-route-unverified'))
    return ops


class Overlay:
    def __init__(self, pool, meta, routers, registry, touchers=(), tolerance_bps=0.05, max_txs=4000):
        self.pool = pool.lower()
        self.pools = {self.pool: meta}
        self.fee = meta['fee']
        self.routers, self.registry = routers, registry
        self.touchers = {a.lower() for a in touchers}
        self.tolerance = tolerance_bps
        self.max_txs = max_txs
        self.sqrt = self.liquidity = None         # newest Swap log of the pool
        self.txs = collections.OrderedDict()      # order -> entry, not yet passed by logs
        self.mismatches = collections.deque(maxlen=200)
        self.counts = collections.Counter()
        self.detail = None                        # per-caller breakdown; replay only
        self._cache = None

    def feed_tx(self, tx, to, data, order):
        """Record one feed transaction; `order` increases in sequencer order."""
        to = (to or '').lower()
        data = data or '0x'
        entry = dict(tx=tx, to=to, order=order, ops=[], unknown=False, key=to[:8] + '/' + data[2:10], why=None)
        try:
            ops = (hop_route(to, data, self.pools) or
                   decode(to, data, self.pools, self.routers, packed_registry=self.registry)) if to else []
            entry['ops'] = [o for o in ops if o['pool'] == self.pool and o['kind'] == 'swap']
            entry['unknown'] = any(o['pool'] == self.pool and o['kind'] != 'swap' for o in ops)
        except Exception as exc:
            entry['unknown'] = to in self.touchers
            entry['why'] = str(exc)[:48]
        if not entry['ops'] and not entry['unknown']:
            return
        self.txs[order] = entry
        self._cache = None
        if len(self.txs) > self.max_txs:
            raise ValueError('V3 overlay backlog exceeded')

    def log(self, order, swap=None, to=None):
        """A pushed log of feed transaction `order` arrived (None: not seen on
        the feed). `swap` is the log itself when it is this pool's Swap.
        Returns True when the caller should schedule an RPC check."""
        surprise = False
        if order is not None:
            while self.txs and next(iter(self.txs)) < order:     # passed without a pool swap
                surprise |= self._score(self.txs.popitem(last=False)[1], None, None)
        if swap is not None:
            state = parse_swap(swap)
            surprise |= self._score(self.txs.pop(order, None), state, (to or '').lower())
            self.sqrt, self.liquidity = state['sqrt'], state['liquidity']
        self._cache = None
        return surprise

    def _score(self, entry, swap, to):
        c = self.counts
        if entry is None:                           # second swap of a transaction, or never queued
            c['touch_unqueued'] += 1
            if to and to not in self.touchers:
                self.touchers.add(to)
                c['touchers_learned'] += 1
            return bool(to)
        if not entry['ops']:
            c['unknown_touched' if swap else 'unknown_untouched'] += 1
            if self.detail is not None:
                self.detail[entry['key'], entry['why'], bool(swap)] += 1
            return bool(swap)
        if self.sqrt is None:
            return False
        want = self._apply(self.sqrt, self.liquidity, entry)
        have = swap['sqrt'] if swap else self.sqrt
        error = abs(want / have - 1) * 2e4
        moved, real = want != self.sqrt, bool(swap)
        c['pred_swap' if moved and real else 'pred_revert' if not moved and not real
          else 'false_swap' if moved else 'false_revert'] += 1
        if self.detail is not None:
            self.detail[entry['key'], 'decoded', 'ok' if error <= self.tolerance else 'bad'] += 1
        if error <= self.tolerance:
            return False
        c['mismatch'] += 1
        self.mismatches.append(dict(tx=entry['tx'], to=entry['to'], error_bps=round(error, 4)))
        return True

    def _apply(self, sqrt, liquidity, entry):
        start = sqrt
        for op in entry['ops']:
            zero, amount = op['zero'], op['amount']
            limit = op.get('limit') or (MIN_SQRT + 1 if zero else MAX_SQRT - 1)
            if (sqrt <= limit) if zero else (sqrt >= limit):
                return start                            # SPL: whole transaction reverts
            exact = amount > 0
            amount = abs(amount)
            if exact:
                amount = amount * (10**6 - self.fee) // 10**6
            try:
                new = next_price(sqrt, liquidity, amount, zero, exact)
            except ValueError:
                if not op.get('limit'):
                    return start                        # cannot fill in range and no limit
                new = limit
            sqrt = max(new, limit) if zero else min(new, limit)
        return sqrt

    def view(self):
        """(sqrtPriceX96 at the feed frontier, uncertain, queued transactions)."""
        if self._cache is None:
            sqrt, uncertain = self.sqrt, False
            if sqrt is not None:
                for entry in self.txs.values():
                    uncertain = uncertain or entry['unknown']
                    if entry['ops']:
                        sqrt = self._apply(sqrt, self.liquidity, entry)
            self._cache = (sqrt, uncertain, len(self.txs))
        return self._cache

    def pseudo_log(self, timestamp_hex):
        """A Swap-shaped log carrying the speculative price for the state worker."""
        sqrt = self.view()[0]
        word = lambda v: format(v & ((1 << 256) - 1), '064x')
        return dict(address=self.pool, topics=[SWAP, '0x' + '0' * 64, '0x' + '0' * 64], removed=False,
                    data='0x' + word(0) + word(0) + word(sqrt) + word(self.liquidity) + word(tick_sqrt(sqrt)),
                    blockNumber='0xffffffffffff', transactionIndex='0x0', logIndex='0x0',
                    blockTimestamp=timestamp_hex)


def load_meta(pool, amm_path='config/amm.json'):
    for p in json.load(open(amm_path))['pools']:
        if p['pool'].lower() == pool.lower():
            fee = {'0.01%': 100, '0.05%': 500, '0.3%': 3000, '1%': 10000}[p['pair'].split()[-1]]
            return dict(p, fee=fee, tokens=sorted((t.lower() for t in p['tokens']), key=lambda t: int(t, 16)))
    raise ValueError('pool not in catalog')


def load_touchers(path='config/v3-touchers.json'):
    try:
        return json.load(open(path))['touchers']
    except FileNotFoundError:
        return []


def build(pool, registry_path='config/optimistic-router-template.json', touchers_path='config/v3-touchers.json'):
    from amm_feed_state import ROUTERS
    return Overlay(pool, load_meta(pool), ROUTERS, json.load(open(registry_path)), load_touchers(touchers_path))


def replay(path, registry_path='config/optimistic-router-template.json', touchers_path='config/v3-touchers.json'):
    """Score the overlay causally on a tape extract: nitro_push rows, the
    pool's chain_log rows, and one {'kind':'blk','blockHash'} row at the first
    other log of each block. At every feed block arrival the overlay price and
    the newest-log price are compared with the true price after that block."""
    import statistics
    import subprocess
    pool = '0x52e65b17fb6e5ba00ed806f37afcd2daa50271ca'
    ov = build(pool, registry_path, touchers_path)
    ov.detail = collections.Counter()
    worker = subprocess.Popen([os.environ.get('STATE_WORKER', 'target/release/metric-live-state'), '--provider-full'],
                              stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1)
    rows = [json.loads(l) for l in open(path)]
    blocks, truth, last = [], {}, None
    swaps = collections.defaultdict(list)
    for r in rows:
        if r['kind'] == 'chain_log' and r['payload']['topics'][0] == SWAP:
            swaps[r['payload']['blockHash']].append(r['payload'])
        elif r['kind'] == 'nitro_push':
            for m in r['payload'].get('messages') or []:
                if m['blockHash'] not in truth:
                    truth[m['blockHash']] = None
                    blocks.append(m['blockHash'])
    for h in blocks:                                # truth: pool price after each block
        if swaps.get(h):
            last = parse_swap(swaps[h][-1])['sqrt']
        truth[h] = last
    seen, first, orders, tx_to, order, samples = set(), {}, {}, {}, 0, []
    for r in rows:
        if r['kind'] == 'nitro_push':
            for m in r['payload'].get('messages') or []:
                h = m['blockHash']
                if h in seen:
                    continue
                seen.add(h)
                first[h] = order + 1
                worker.stdin.write(json.dumps({'kind': 'decode', 'row': {'payload': {'messages': [m]},
                                   'recv_ns': r['recv_ns'], 'mono_ns': r['mono_ns']}}) + '\n')
                worker.stdin.flush()
                for t in json.loads(worker.stdout.readline()).get('result', {}).get('transactions', []):
                    if 'tx' in t:
                        order += 1
                        orders[t['tx']], tx_to[t['tx']] = order, t.get('to')
                        ov.feed_tx(t['tx'], t.get('to'), t.get('data'), order)
                if ov.sqrt is not None and truth.get(h):
                    bps = lambda a: abs(a / truth[h] - 1) * 2e4
                    sqrt, uncertain, _ = ov.view()
                    samples.append((bps(sqrt), bps(ov.sqrt), uncertain, bool(swaps.get(h))))
        elif r['kind'] == 'chain_log':
            p = r['payload']
            ov.log(orders.get(p['transactionHash']), p if p['topics'][0] == SWAP else None, tx_to.get(p['transactionHash']))
        elif r.get('blockHash') in first:
            ov.log(first[r['blockHash']])
    worker.terminate()
    if os.environ.get('DETAIL'):
        for k, n in ov.detail.most_common(40):
            print(n, k, file=sys.stderr)
        for m in sorted(ov.mismatches, key=lambda m: -m['error_bps'])[:8]:
            print(m, file=sys.stderr)

    def stats(v):
        v = sorted(v)
        if not v:
            return None
        q = lambda p: round(v[min(len(v) - 1, int(p * len(v)))], 3)
        return dict(n=len(v), mean=round(statistics.mean(v), 3), p50=q(.5), p90=q(.9), p99=q(.99), max=round(v[-1], 3),
                    within_0_1bp=round(sum(x <= .1 for x in v) / len(v), 3))
    moved = [s for s in samples if s[3]]
    return dict(blocks=len(samples), blocks_with_pool_swap=len(moved), counts=dict(ov.counts),
                error_bps_at_feed_arrival=dict(
                    overlay_all=stats([s[0] for s in samples]), logs_only_all=stats([s[1] for s in samples]),
                    overlay_swap_blocks=stats([s[0] for s in moved]), logs_only_swap_blocks=stats([s[1] for s in moved]),
                    overlay_when_certain=stats([s[0] for s in samples if not s[2]]),
                    overlay_when_uncertain=stats([s[0] for s in samples if s[2]])),
                uncertain_fraction=round(sum(s[2] for s in samples) / max(1, len(samples)), 3)), sorted(ov.touchers)


if __name__ == '__main__':
    if len(sys.argv) >= 3 and sys.argv[1] == 'replay':
        report, touchers = replay(*sys.argv[2:])
        print(json.dumps(report, indent=1))
        if os.environ.get('WRITE_TOUCHERS'):
            json.dump(dict(pool='0x52e65b17fb6e5ba00ed806f37afcd2daa50271ca', touchers=touchers),
                      open(os.environ['WRITE_TOUCHERS'], 'w'), indent=1)
    else:
        print(__doc__)
