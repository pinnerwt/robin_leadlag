// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

interface IMetricPool {
    function swap(address recipient, bool zeroForOne, int128 amountSpecified,
        uint128 priceLimitX64, bytes calldata callbackData, bytes calldata extensionData)
        external returns (int128 amount0Delta, int128 amount1Delta);
}
interface IERC20Minimal {
    function balanceOf(address) external view returns (uint256);
    function decimals() external view returns (uint8);
}

/// @notice Owner-funded single-hop Metric executor. Inventory stays in owner's wallet.
/// @dev No custody, routing, delegated caller, arbitrary call, or user-selected recipient.
contract MetricInventoryExecutor {
    address public immutable owner;
    struct Binding { address base; address quote; bool baseIsToken0; bytes32 codehash; }
    mapping(address => Binding) public pools;
    address private activePool;
    bool private buy;
    bool private paid;
    uint128 private quantity;
    uint128 private limit;
    int256 private callbackBase;
    int256 private callbackQuote;
    error Unauthorized(); error Busy(); error InvalidPool(); error Expired();
    error InvalidFill(); error InvalidPayment(); error TransferFailed();
    event PoolConfigured(address indexed pool, address base, address quote, bool baseIsToken0, bytes32 codehash);
    event Executed(address indexed pool, address indexed wallet, bool buy, uint128 baseQuantity, uint128 usdgAmount);
    constructor(address owner_) { if (owner_ == address(0)) revert Unauthorized(); owner = owner_; }
    modifier onlyOwner() { if (msg.sender != owner) revert Unauthorized(); _; }
    modifier idle() { if (activePool != address(0)) revert Busy(); _; }

    function configurePool(address pool, address base, address quote, bool baseIsToken0, bytes32 codehash)
        external onlyOwner idle {
        if (pool.code.length == 0 || pool.codehash != codehash || base == quote || base == address(0)
            || quote == address(0) || IERC20Minimal(quote).decimals() != 6) revert InvalidPool();
        // Archived and public Metric getImmutables starts with factory, token0, token1.
        (bool ok, bytes memory result) = pool.staticcall(abi.encodeWithSignature("getImmutables()"));
        if (!ok || result.length < 96) revert InvalidPool();
        (,address token0,address token1) = abi.decode(result,(address,address,address));
        if (token0 != (baseIsToken0 ? base : quote) || token1 != (baseIsToken0 ? quote : base)) revert InvalidPool();
        pools[pool] = Binding(base, quote, baseIsToken0, codehash);
        emit PoolConfigured(pool,base,quote,baseIsToken0,codehash);
    }
    function removePool(address pool) external onlyOwner idle { delete pools[pool]; }

    /// @param buy_ true: exact base output with max USDG input; false: exact base input with min USDG output.
    function trade(address pool, bool buy_, uint128 baseQuantity, uint128 usdgLimit, uint64 deadline)
        external onlyOwner idle returns (uint128 usdgAmount) {
        if (block.timestamp > deadline) revert Expired();
        Binding memory b = pools[pool];
        if (b.base == address(0) || pool.codehash != b.codehash) revert InvalidPool();
        if (baseQuantity == 0 || baseQuantity > uint128(type(int128).max) || usdgLimit == 0) revert InvalidFill();
        uint256 baseBefore = IERC20Minimal(b.base).balanceOf(owner);
        uint256 quoteBefore = IERC20Minimal(b.quote).balanceOf(owner);
        activePool = pool; buy = buy_; paid = false; quantity = baseQuantity; limit = usdgLimit;
        bool zeroForOne = buy_ ? !b.baseIsToken0 : b.baseIsToken0;
        (int128 d0, int128 d1) = IMetricPool(pool).swap(owner, zeroForOne,
            buy_ ? -int128(baseQuantity) : int128(baseQuantity),
            zeroForOne ? 1 : type(uint128).max, "", "");
        int256 db = b.baseIsToken0 ? int256(d0) : int256(d1);
        int256 dq = b.baseIsToken0 ? int256(d1) : int256(d0);
        if (!paid || db != callbackBase || dq != callbackQuote) revert InvalidFill();
        usdgAmount = uint128(uint256(buy_ ? dq : -dq));
        uint256 baseAfter = IERC20Minimal(b.base).balanceOf(owner);
        uint256 quoteAfter = IERC20Minimal(b.quote).balanceOf(owner);
        if (buy_) {
            if (baseAfter != baseBefore + baseQuantity || quoteBefore != quoteAfter + usdgAmount) revert InvalidFill();
        } else {
            if (baseBefore != baseAfter + baseQuantity || quoteAfter != quoteBefore + usdgAmount) revert InvalidFill();
        }
        activePool = address(0); paid = false;
        emit Executed(pool, owner, buy_, baseQuantity, usdgAmount);
    }
    function metricOmmSwapCallback(int256 d0, int256 d1, bytes calldata data) external {
        if (msg.sender != activePool || activePool == address(0) || paid || data.length != 0) revert Unauthorized();
        Binding memory b = pools[msg.sender];
        int256 db = b.baseIsToken0 ? d0 : d1;
        int256 dq = b.baseIsToken0 ? d1 : d0;
        if (buy) {
            if (db != -int256(uint256(quantity)) || dq <= 0 || uint256(dq) > limit) revert InvalidFill();
        } else {
            if (db != int256(uint256(quantity)) || dq >= 0 || dq < type(int128).min || uint256(-dq) < limit) revert InvalidFill();
        }
        paid = true; callbackBase = db; callbackQuote = dq;
        address token = buy ? b.quote : b.base;
        uint256 owed = buy ? uint256(dq) : uint256(db);
        (bool ok, bytes memory result) = token.call(abi.encodeWithSignature("transferFrom(address,address,uint256)",owner,msg.sender,owed));
        if (!ok || (result.length != 0 && (result.length != 32 || !abi.decode(result,(bool))))) revert TransferFailed();
    }
}
