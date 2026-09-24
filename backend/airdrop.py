"""Merkle eligibility proofs for the token-claim (airdrop) module.

The project party publishes a single Merkle root inside the claim contract;
each whitelisted address later claims by presenting a Merkle proof.  This
module builds that root and the per-address proofs off-chain, using exactly
the hash scheme the ``merkle_airdrop`` contract template verifies on-chain:

* leaf  = ``sha256(address)``                     (address lower-cased)
* node  = ``sha256(left || right)``               (raw 32-byte digests)
* odd levels duplicate their last element (Bitcoin-style)

Proofs are lists of ``{"dir": "L"|"R", "hash": hex}`` steps — the same shape
:class:`backend.merkle.MerkleTree` produces — which the contract folds with
the injected ``sha256_hex`` helper.
"""

from . import crypto
from .merkle import MerkleTree

MAX_LIST_SIZE = 5000        # guard against pathological request bodies


def normalize_addresses(addresses):
    """Validate, lower-case, de-duplicate, and sort an address list.

    Sorting makes the resulting root independent of the input order, so the
    project party and every claimant derive the *same* tree from the same
    set.  Raises ``ValueError`` on any malformed address.
    """
    if not isinstance(addresses, (list, tuple)):
        raise ValueError("addresses 必须是地址数组")
    if len(addresses) > MAX_LIST_SIZE:
        raise ValueError(f"名单过大（上限 {MAX_LIST_SIZE} 个地址）")
    out = []
    for raw in addresses:
        addr = str(raw).strip().lower()
        if not crypto.is_valid_address(addr):
            raise ValueError(f"无效地址: {raw}")
        out.append(addr)
    return sorted(set(out))


def _tree(addresses):
    leaves = [crypto.sha256(a) for a in addresses]
    return MerkleTree(leaves)


def merkle_root_hex(addresses):
    """Return the hex Merkle root committing to ``addresses`` (normalized)."""
    return _tree(addresses).root.hex()


def proof_for(addresses, address):
    """Return ``(index, proof)`` for ``address`` or ``None`` if not listed."""
    target = str(address).strip().lower()
    try:
        index = addresses.index(target)
    except ValueError:
        return None
    return index, _tree(addresses).proof(index)


def verify_proof(address, proof, root_hex):
    """Off-chain check mirroring the contract's on-chain verification."""
    leaf = crypto.sha256(str(address).strip().lower())
    return MerkleTree.verify(leaf, 0, proof, bytes.fromhex(root_hex))
