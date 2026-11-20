import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from router_registry import refresh_registry
R='0x'+'11'*20;D='0x'+'22'*20;I='0x'+'33'*20

class RegistryTests(unittest.TestCase):
    def setUp(self):
        self.template=dict(routers={R:dict(code_hash='01',dependencies=[dict(address=D,code_hash='02',implementation_slot='0x9',implementation=I,implementation_code_hash='03',required_storage={'0x1':'0x44'})])})
        self.calls=[];self.code={R:'0x01',D:'0x02',I:'0x03'};self.storage={'0x9':I,'0x1':'0x44'};self.hash='anchor'
    def rpc(self,method,args):
        self.calls.append((method,args))
        if method=='eth_getCode':return self.code[args[0]]
        if method=='eth_getStorageAt':return self.storage[args[1]]
        if method=='eth_getBlockByNumber':return dict(hash=self.hash)
        raise AssertionError(method)
    def refresh(self):
        return refresh_registry(self.template,dict(number='0x123',hash='anchor'),self.rpc,code_hash=lambda b:b.hex())
    def test_nested_dependencies_same_block_and_template_immutable(self):
        before=copy.deepcopy(self.template);r=self.refresh()
        self.assertEqual(self.template,before);self.assertEqual(r['anchor_hash'],'anchor')
        for method,args in self.calls:self.assertEqual(args[0] if method=='eth_getBlockByNumber' else args[-1],'0x123')
        self.assertIn(('eth_getCode',[I,'0x123']),self.calls)
    def test_nested_implementation_change_rejects(self):
        self.storage['0x9']=R
        with self.assertRaisesRegex(ValueError,'implementation changed'):self.refresh()
    def test_adapter_routing_change_rejects(self):
        self.storage['0x1']='0x45'
        with self.assertRaisesRegex(ValueError,'routing configuration'):self.refresh()
    def test_code_or_anchor_change_rejects(self):
        self.code[D]='0xff'
        with self.assertRaisesRegex(ValueError,'bytecode changed'):self.refresh()
        self.code[D]='0x02';self.hash='changed'
        with self.assertRaisesRegex(ValueError,'anchor changed'):self.refresh()

if __name__=='__main__':unittest.main()
