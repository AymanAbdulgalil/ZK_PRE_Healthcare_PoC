// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @title AccessControl
/// @notice Append-only audit ledger (paper §5.4, requirements R3-R5). Stores only
/// addresses, a content hash and lifecycle state: no PHI, keys, capsules or proofs.
/// @dev Authorised by msg.sender alone: grants are looked up under the caller's
/// address, so anyone else finds no grant and reverts. Audit through the events.
contract AccessControl {
    struct Grant {
        address owner;
        address provider;
        bytes32 recordHash;   // keccak256 pointer to the ciphertext blob in object storage
        uint64 grantedAt;
        bool acknowledged;    // set by the provider's own transaction
        uint64 revokedAt;     // 0 while active
    }

    /// @dev Append-only: a re-grant is a new record, never an overwrite.
    Grant[] private grants;

    /// owner => provider => recordHash => latest grant index + 1 (0 = none).
    mapping(address => mapping(address => mapping(bytes32 => uint256))) private latestGrant;

    event AccessGranted(
        uint256 indexed grantId,
        address indexed owner,
        address indexed provider,
        bytes32 recordHash,
        uint64 grantedAt
    );
    event AccessAcknowledged(
        uint256 indexed grantId,
        address indexed owner,
        address indexed provider,
        uint64 acknowledgedAt
    );
    event AccessRevoked(
        uint256 indexed grantId,
        address indexed owner,
        address indexed provider,
        uint64 revokedAt
    );

    error GrantAlreadyExists();
    error GrantNotFound();
    error AlreadyAcknowledged();
    error AlreadyRevoked();

    /// @notice Caller (the owner) grants `provider` access to `recordHash`. Reverts if
    /// the triple has a live grant; after revocation a re-grant starts un-acknowledged.
    function grantAccess(address provider, bytes32 recordHash) external returns (uint256 grantId) {
        uint256 idx = latestGrant[msg.sender][provider][recordHash];
        if (idx != 0 && grants[idx - 1].revokedAt == 0) revert GrantAlreadyExists();

        grants.push(Grant({
            owner: msg.sender,
            provider: provider,
            recordHash: recordHash,
            grantedAt: uint64(block.timestamp),
            acknowledged: false,
            revokedAt: 0
        }));

        grantId = grants.length - 1;
        latestGrant[msg.sender][provider][recordHash] = grantId + 1;
        emit AccessGranted(grantId, msg.sender, provider, recordHash, uint64(block.timestamp));
    }

    /// @notice Caller (the named provider) acknowledges; anyone else gets GrantNotFound.
    function acknowledgeGrant(address owner, bytes32 recordHash) external {
        uint256 idx = latestGrant[owner][msg.sender][recordHash];
        if (idx == 0) revert GrantNotFound();

        Grant storage g = grants[idx - 1];
        if (g.revokedAt != 0) revert AlreadyRevoked();
        if (g.acknowledged) revert AlreadyAcknowledged();

        g.acknowledged = true;
        emit AccessAcknowledged(idx - 1, owner, msg.sender, uint64(block.timestamp));
    }

    /// @notice Caller (the grantor) ends `provider`'s access, effective on the next
    /// proxy request. Monotonic: restoring access takes a fresh grantAccess.
    function revokeAccess(address provider, bytes32 recordHash) external {
        uint256 idx = latestGrant[msg.sender][provider][recordHash];
        if (idx == 0) revert GrantNotFound();

        Grant storage g = grants[idx - 1];
        if (g.revokedAt != 0) revert AlreadyRevoked();

        g.revokedAt = uint64(block.timestamp);
        emit AccessRevoked(idx - 1, msg.sender, provider, uint64(block.timestamp));
    }

    /// @notice True only if the grant exists, is acknowledged and is not revoked.
    /// Every proxy checks this before re-encrypting.
    function isAccessActive(address owner, address provider, bytes32 recordHash) external view returns (bool) {
        uint256 idx = latestGrant[owner][provider][recordHash];
        if (idx == 0) return false;

        Grant storage g = grants[idx - 1];
        return g.acknowledged && g.revokedAt == 0;
    }
}
