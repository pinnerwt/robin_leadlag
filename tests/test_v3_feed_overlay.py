import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from v3_feed_overlay import Overlay, SWAP, hop_route, parse_swap
from v3_state import next_price, tick_sqrt
from metric_live_observer import Projection

POOL = '0x52e65b17fb6e5ba00ed806f37afcd2daa50271ca'
T0, T1 = '0x0bd7d308f8e1639fab988df18a8011f41eacad73', '0x5fc5360d0400a0fd4f2af552add042d716f1d168'
META = dict(fee=100, tokens=[T0, T1])
SQRT, LIQ = 3317000000000000000000000, 1200000000000000000
word = lambda v: format(v & ((1 << 256) - 1), '064x')


def swap_log(sqrt, liquidity=LIQ, **extra):
    return dict(address=POOL, topics=[SWAP, '0x0', '0x0'], data='0x' + word(1) + word(-1) + word(sqrt) + word(liquidity) + word(tick_sqrt(sqrt)), **extra)


def direct(zero, amount, limit):
    # Direct pool swap(recipient, zeroForOne, amountSpecified, sqrtPriceLimitX96, data)
    return '0x128acb08' + word(1) + word(int(zero)) + word(amount) + word(limit) + word(160) + word(0)


def overlay(touchers=()):
    o = Overlay(POOL, META, {}, {'routers': {}}, touchers)
    o.log(None, swap_log(SQRT))
    return o


class OverlayTests(unittest.TestCase):
    def test_decoded_swap_moves_price_before_its_log_and_scores_exact(self):
        o = overlay()
        amount = 10**18
        o.feed_tx('a', POOL, direct(True, amount, SQRT * 99 // 100), 1)
        want = next_price(SQRT, LIQ, amount * (10**6 - 100) // 10**6, True, True)
        self.assertEqual(o.view(), (want, False, 1))
        self.assertLess(want, SQRT)
        self.assertFalse(o.log(1, swap_log(want), POOL))
        self.assertEqual((o.view(), o.counts['pred_swap'], o.counts['mismatch']), ((want, False, 0), 1, 0))

    def test_limit_clamps_and_price_past_limit_is_a_revert(self):
        o = overlay()
        limit = SQRT - SQRT // 100000
        o.feed_tx('a', POOL, direct(True, 10**21, limit), 1)
        self.assertEqual(o.view()[0], limit)
        o.feed_tx('b', POOL, direct(True, 10**21, limit), 2)       # price now at its limit: SPL
        self.assertEqual(o.view()[0], limit)
        o.feed_tx('c', POOL, direct(False, 10**15, SQRT // 2), 3)  # wrong side of the limit
        self.assertEqual(o.view()[0], limit)
        self.assertFalse(o.log(1, swap_log(limit), POOL))
        self.assertFalse(o.log(9))                                   # logs passed b and c without a swap
        self.assertEqual((o.counts['pred_swap'], o.counts['pred_revert'], len(o.txs)), (1, 2, 0))

    def test_mismatch_and_unknown_touch_request_a_check(self):
        o = overlay(touchers=['0xdead'])
        o.feed_tx('a', POOL, direct(True, 10**18, SQRT * 99 // 100), 1)
        self.assertTrue(o.log(1, swap_log(SQRT - 5 * SQRT // 10**6), POOL))
        self.assertEqual(o.counts['mismatch'], 1)
        o.feed_tx('b', '0xdead', '0x12345678', 2)
        self.assertTrue(o.view()[1])
        self.assertTrue(o.log(2, swap_log(SQRT), '0xdead'))
        self.assertFalse(o.view()[1])
        self.assertTrue(o.log(3, swap_log(SQRT + 1), '0xbeef'))      # never queued: learn the address
        self.assertIn('0xbeef', o.touchers)
        o.feed_tx('c', '0xbeef', '0x12345678', 4)
        self.assertTrue(o.view()[1])
        self.assertFalse(o.log(5))
        self.assertEqual(o.counts['unknown_untouched'], 1)

    def test_irrelevant_transactions_are_not_queued(self):
        o = overlay()
        o.feed_tx('a', '0xfeed', '0x12345678', 1)
        o.feed_tx('b', None, None, 2)
        self.assertEqual(o.view(), (SQRT, False, 0))

    def test_pseudo_log_round_trips(self):
        o = overlay()
        o.feed_tx('a', POOL, direct(False, 10**9, SQRT * 2), 1)
        log = o.pseudo_log('0x10')
        self.assertEqual(parse_swap(log), dict(sqrt=o.view()[0], liquidity=LIQ, tick=tick_sqrt(o.view()[0])))
        self.assertEqual((len(log['topics']), log['blockTimestamp']), (3, '0x10'))

    def test_hop_route_only_trusts_a_first_hop(self):
        to = '0x65050a9b7e5075a2ba5ced7b1b64ee66262c40dc'
        hop = lambda pool: [1, int(T0, 16), int(T1, 16), int(pool, 16), 100, 1, 0, 0x140, 0, 0, 0]
        def call(pools):
            offsets = [32 * len(pools) + 32 * 11 * i for i in range(len(pools))]
            words = [0xa0, 0, 5 * 10**15, 1, 2, len(pools)] + offsets + [x for p in pools for x in hop(p)]
            return '0x4d819a2a' + ''.join(word(x) for x in words)
        ops = hop_route(to, call([POOL, '0x' + '11' * 20]), {POOL: META})
        self.assertEqual([(o['zero'], o['amount'], o['limit']) for o in ops], [(True, 5 * 10**15, None)])
        with self.assertRaisesRegex(ValueError, 'not known'):
            hop_route(to, call(['0x' + '11' * 20, POOL]), {POOL: META})
        self.assertIsNone(hop_route('0xfeed', call([POOL]), {POOL: META}))


class Worker:
    def __init__(self): self.requests = []; self.transactions = []
    def call(self, **r):
        self.requests.append(r)
        if r['kind'] == 'decode': return {'transactions': self.transactions}
        if r['kind'] == 'quote': return {'quote': {'bid_raw': '1', 'ask_raw': '2'}}
        return {'update': {}}


class ObserverOverlayTests(unittest.TestCase):
    def make(self):
        w = Worker(); p = Projection(w)
        p.initialize({'anchor': {'number': '0x1', 'hash': 'a', 'timestamp': '0x1', 'l1BlockNumber': '0x1'}, 'pools': [{'v3_price_pools': [POOL]}]})
        p.overlays[POOL] = Overlay(POOL, META, {}, {'routers': {}})
        p.anchor_seen = True; p.heads['b'] = {'number': '0x2'}
        return p, w

    def nitro(self, p, w, seq, txs):
        w.transactions = [dict(tx=tx, to=POOL, data=data, block_hash='b') for tx, data in txs]
        p.update('nitro', {'messages': [{'sequenceNumber': seq, 'blockHash': 'b', 'message': {'message': {'header': {'timestamp': 2, 'blockNumber': 2}}}}]}, 10**9)
        p.last_head = 10**9

    def test_quote_uses_calldata_price_and_own_swap_log_does_not_block(self):
        p, w = self.make()
        self.nitro(p, w, 1, [('seed', direct(True, 1, SQRT // 2))])
        p.update('log', swap_log(SQRT, transactionHash='seed', blockHash='b', blockNumber='0x2', transactionIndex='0x0', logIndex='0x0'), 10**9)
        self.assertEqual(len(p.logs), 1)                          # no barrier yet for the worker
        quote = p.quote(10**18, 10**9)
        pending = w.requests[-1]['pending']
        self.assertEqual([u['kind'] for u in pending], ['v3_price'])     # worker has not applied the log yet
        self.assertEqual(parse_swap(pending[0]['log'])['sqrt'], SQRT)
        self.nitro(p, w, 2, [('next', direct(True, 10**18, SQRT * 99 // 100))])
        quote = p.quote(10**18, 10**9)
        want = next_price(SQRT, LIQ, 10**18 * (10**6 - 100) // 10**6, True, True)
        self.assertEqual(parse_swap(w.requests[-1]['pending'][0]['log'])['sqrt'], want)
        self.assertTrue(quote['v3_speculative'])
        p.overlay_on = False                                         # RPC check disagreed: logs only
        self.assertIsNone(p.quote(10**18, 10**9))

    def test_confirmed_price_needs_no_overlay(self):
        p, w = self.make()
        p.metadata['b'] = {'timestamp': '0x2', 'l1BlockNumber': '0x2'}
        row = dict(blockHash='b', blockNumber='0x2')
        p.update('log', swap_log(SQRT, transactionHash='seed', transactionIndex='0x0', logIndex='0x0', **row), 10**9)
        p.update('log', dict(address='0xother', topics=['0x1'], data='0x', transactionHash='later', transactionIndex='0x1', logIndex='0x1', **row), 10**9)
        self.assertEqual(p.v3_sqrt, {POOL: SQRT})
        p.last_head = p.last_nitro = 10**9
        quote = p.quote(10**18, 10**9)
        self.assertEqual(w.requests[-1]['pending'], [])
        self.assertFalse(quote['v3_speculative'])


if __name__ == '__main__':
    unittest.main()
