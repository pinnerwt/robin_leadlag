"""c2 equality against ArbSys.arbBlockNumber, not EVM L1 NUMBER."""
def decode(raw,offset,stop,end,data_end):
 c=raw[offset:stop]
 if len(c)!=3 or c[0]!=194:raise ValueError('invalid c2 profile')
 p=int.from_bytes(c[1:],'big')
 if not end<=p<=data_end-16:raise ValueError('c2 operand bounds')
 number=int.from_bytes(raw[p:p+16],'big')
 if number>=1<<64:raise ValueError('c2 block exceeds uint64')
 return dict(opcode=194,block_number=number,offset=offset)

def failed(guard,block_number):
 if type(block_number) is not int or not 0<=block_number<1<<64:raise ValueError('missing or invalid Arbitrum block number')
 return block_number!=guard['block_number']
