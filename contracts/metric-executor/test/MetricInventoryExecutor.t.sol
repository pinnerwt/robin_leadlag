// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;
import {MetricInventoryExecutor, IMetricPool} from "../src/MetricInventoryExecutor.sol";
interface Vm { function warp(uint256) external; }
contract Token {
    uint8 public immutable decimals;
    mapping(address=>uint256) public balanceOf;
    mapping(address=>mapping(address=>uint256)) public allowance;
    address public metadata;
    fallback() external { (bool ok,bytes memory out)=metadata.staticcall(msg.data); if(!ok) revert(); assembly("memory-safe"){return(add(out,32),mload(out))} }
    event Transfer(address indexed from,address indexed to,uint256 value);
    constructor(uint8 d){decimals=d;}
    function mint(address a,uint256 n) external {balanceOf[a]+=n;}
    function approve(address a,uint256 n) external returns(bool){allowance[msg.sender][a]=n;return true;}
    function transfer(address to,uint256 n) external returns(bool){balanceOf[msg.sender]-=n;balanceOf[to]+=n;emit Transfer(msg.sender,to,n);return true;}
    function transferFrom(address from,address to,uint256 n) external returns(bool){allowance[from][msg.sender]-=n;balanceOf[from]-=n;balanceOf[to]+=n;emit Transfer(from,to,n);return true;}
}
contract Pool is IMetricPool {
    Token public t0; Token public t1; bool public base0;
    uint256 public price=100e6; bool public partialFill; bool public twice; bool public skip;
    constructor(Token b,Token q,bool b0){base0=b0;t0=b0?b:q;t1=b0?q:b;}
    function getImmutables() external view returns(address,address,address){return(address(this),address(t0),address(t1));}
    function set(uint256 p,bool part,bool two,bool no) external{price=p;partialFill=part;twice=two;skip=no;}
    function swap(address recipient,bool zero,int128 amount,uint128,bytes calldata data,bytes calldata)
        external returns(int128 a,int128 b){
        bool buy=zero!=base0;uint256 qty=uint128(amount<0?-amount:amount);if(partialFill)qty/=2;
        int128 db=buy?-int128(uint128(qty)):int128(uint128(qty));int128 dq=buy?int128(uint128(price)):-int128(uint128(price));
        (a,b)=base0?(db,dq):(dq,db);
        (buy?(base0?t0:t1):(base0?t1:t0)).transfer(recipient,buy?qty:price);
        if(!skip)MetricInventoryExecutor(msg.sender).metricOmmSwapCallback(a,b,data);
        if(twice)MetricInventoryExecutor(msg.sender).metricOmmSwapCallback(a,b,data);
    }
}
contract Intruder{
 function attack(MetricInventoryExecutor e,address p) external returns(bool){(bool ok,)=address(e).call(abi.encodeCall(e.trade,(p,true,uint128(1e17),uint128(100e6),uint64(block.timestamp))));return ok;}
}
contract MetricInventoryExecutorTest {
    MetricInventoryExecutor e;Token b;Token q;Pool p;
    function setUp() public { b=new Token(18);q=new Token(6);e=new MetricInventoryExecutor(address(this));p=new Pool(b,q,true);fund(p);e.configurePool(address(p),address(b),address(q),true,address(p).codehash); }
    function fund(Pool target) internal {b.mint(address(this),1e18);q.mint(address(this),1000e6);b.mint(address(target),100e18);q.mint(address(target),100000e6);b.approve(address(e),type(uint256).max);q.approve(address(e),type(uint256).max);}
    function attempt(bool buy,uint128 lim) internal returns(bool){(bool ok,)=address(e).call(abi.encodeCall(e.trade,(address(p),buy,uint128(1e17),lim,uint64(block.timestamp))));return ok;}
    function testBuySellAndNoCustody() public { e.trade(address(p),true,1e17,100e6,uint64(block.timestamp));require(b.balanceOf(address(this))==11e17&&q.balanceOf(address(this))==900e6);e.trade(address(p),false,1e17,100e6,uint64(block.timestamp));require(b.balanceOf(address(this))==1e18&&q.balanceOf(address(this))==1000e6);require(b.balanceOf(address(e))==0&&q.balanceOf(address(e))==0); }
    function testReverseTokenOrdering() public {Pool r=new Pool(b,q,false);fund(r);e.configurePool(address(r),address(b),address(q),false,address(r).codehash);e.trade(address(r),true,1e17,100e6,uint64(block.timestamp));e.trade(address(r),false,1e17,100e6,uint64(block.timestamp));}
    function testSlippageAndPartialRollback() public {require(!attempt(true,99e6));require(!attempt(false,101e6));p.set(100e6,true,false,false);require(!attempt(true,100e6));require(!attempt(false,100e6));require(b.balanceOf(address(this))==1e18&&q.balanceOf(address(this))==1000e6);}
    function testNoCallbackAndDoubleCallbackRejected() public {p.set(100e6,false,false,true);require(!attempt(true,100e6));p.set(100e6,false,true,false);require(!attempt(true,100e6));}
    function testUnauthorizedAndExpired() public {require(!new Intruder().attack(e,address(p)));(bool ok,)=address(e).call(abi.encodeCall(e.metricOmmSwapCallback,(int256(1),int256(-1),bytes(""))));require(!ok);Vm(address(uint160(uint256(keccak256("hevm cheat code"))))).warp(100);(ok,)=address(e).call(abi.encodeCall(e.trade,(address(p),true,uint128(1e17),uint128(100e6),uint64(99))));require(!ok);}
    function testMissingAllowanceAtomic() public {q.approve(address(e),0);require(!attempt(true,100e6));require(b.balanceOf(address(this))==1e18&&q.balanceOf(address(this))==1000e6);}
    function testUnknownPoolAndBadBinding() public {Pool other=new Pool(b,q,true);(bool ok,)=address(e).call(abi.encodeCall(e.configurePool,(address(other),address(q),address(b),false,address(other).codehash)));require(!ok);(ok,)=address(e).call(abi.encodeCall(e.trade,(address(other),true,uint128(1e17),uint128(100e6),uint64(block.timestamp))));require(!ok);}
    function testFuzzLimit(uint128 price) public {price=uint128(1+uint256(price)%1000e6);p.set(price,false,false,false);require(attempt(true,price));}
}
