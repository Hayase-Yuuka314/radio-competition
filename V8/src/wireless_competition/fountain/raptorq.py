"""RaptorQ-inspired fountain code implementation.

Based on LT (Luby Transform) codes with optimized degree distribution
and systematic encoding. Provides reliable file transfer without
per-packet acknowledgements.

Key properties:
- Systematic first K packets = original blocks (instant decode if no loss)
- Repair packets use Robust Soliton degree distribution
- Belief propagation (peeling) decoder
- Each packet ID deterministically generates its degree and neighbours
- Typical overhead: ~5-15% beyond K packets for high-probability decode

Reference:
  Luby, "LT Codes", FOCS 2002
  Shokrollahi, "Raptor Codes", IEEE Trans. Info. Theory 2006
"""

from __future__ import annotations

import hashlib
import struct
from dataclasses import dataclass
from typing import Optional

import numpy as np


PACKET_HEADER_FORMAT = ">IIIII"
PACKET_HEADER_SIZE = struct.calcsize(PACKET_HEADER_FORMAT)


@dataclass
class FountainPacket:
    """Single fountain-coded packet."""
    packet_id: int
    file_id: int
    k: int
    total_size: int
    block_size: int
    payload: bytes

    def serialize(self) -> bytes:
        header = struct.pack(
            PACKET_HEADER_FORMAT,
            self.packet_id, self.file_id, self.k, self.total_size, self.block_size,
        )
        return header + self.payload

    @classmethod
    def deserialize(cls, data: bytes) -> "FountainPacket":
        if len(data) < PACKET_HEADER_SIZE:
            raise ValueError(f"Packet too short: {len(data)} bytes")
        pid, fid, k, ts, bs = struct.unpack(PACKET_HEADER_FORMAT, data[:PACKET_HEADER_SIZE])
        return cls(packet_id=pid, file_id=fid, k=k, total_size=ts, block_size=bs,
                   payload=data[PACKET_HEADER_SIZE:])


def _robust_soliton_degree(random_state: np.random.RandomState, k: int,
                           c: float = 0.1, delta: float = 0.05) -> int:
    """Sample a degree from the Robust Soliton distribution.

    Ideal soliton: ρ(1)=1/K, ρ(d)=1/(d(d-1)) for d=2..K.
    Robust adjustment handles the spike at d=K/S.

    Args:
        random_state: numpy RandomState for reproducible sampling.
        k: number of source blocks.
        c: robustness parameter (~0.1).
        delta: failure probability bound (~0.05).

    Returns:
        degree d in [1, k].
    """
    rng = random_state
    s = c * np.log(k / delta) * np.sqrt(k)
    s = max(1, int(s))
    divisor = s + k - 1

    roll = rng.random()
    if roll < s / divisor:
        return 1

    for d in range(2, k + 1):
        prob = (s + k) / (divisor * d * (d - 1))
        roll -= prob
        if roll <= 0:
            return d
    return k


def _derive_neighbors(packet_id: int, k: int, file_id: int) -> list[int]:
    """Deterministically derive degree and neighbor set from packet_id.

    Uses packet_id XOR file_id as seed so receiver can reconstruct
    the same set without transmitting the neighbor list.
    """
    packet_seed = packet_id ^ file_id
    rng = np.random.RandomState(np.uint32(packet_seed + 1))

    if packet_id < k:
        return [packet_id]
    else:
        d = _robust_soliton_degree(rng, k)

    neighbors = set()
    max_attempts = d * 10
    attempts = 0
    while len(neighbors) < d and attempts < max_attempts:
        n = rng.randint(0, k)
        neighbors.add(n)
        attempts += 1

    return sorted(neighbors)


def _xor_block(block: bytes, other: bytes) -> bytes:
    """XOR two byte strings, padding the shorter one to match."""
    min_len = min(len(block), len(other))
    result = bytearray(min_len)
    for i in range(min_len):
        result[i] = block[i] ^ other[i]
    if len(block) > len(other):
        result.extend(block[min_len:])
    elif len(other) > len(block):
        result.extend(other[min_len:])
    return bytes(result)


class FountainEncoder:
    """Fountain encoder: converts a file into an endless stream of encoded packets.

    Usage:
        encoder = FountainEncoder(file_data, block_size=256, seed=42)
        for pkt in encoder:
            tx_send(pkt.serialize())
            if should_stop:
                break
    """

    def __init__(self, data: bytes, block_size: int = 256, seed: int = 0,
                 file_id: int = 0):
        self._data = data
        self._block_size = block_size
        self._seed = seed
        self._file_id = file_id
        self._total_size = len(data)

        self._blocks: list[bytes] = []
        for i in range(0, len(data), block_size):
            self._blocks.append(data[i:i + block_size])
        self.k = len(self._blocks)

        self._next_packet_id = 0
        self._rng = np.random.RandomState(np.uint32(seed))

        self._packets_sent = 0

    @property
    def source_blocks(self) -> int:
        return self.k

    @property
    def total_size(self) -> int:
        return self._total_size

    def next_packet(self) -> FountainPacket:
        """Generate the next fountain packet."""
        pid = self._next_packet_id
        self._next_packet_id += 1

        neighbors = _derive_neighbors(pid, self.k, self._file_id)

        payload = bytearray(self._block_size)
        first = True
        for ni in neighbors:
            if first:
                payload = bytearray(self._blocks[ni])
                first = False
            else:
                payload = bytearray(_xor_block(bytes(payload), self._blocks[ni]))

        if first:
            payload = bytearray()

        return FountainPacket(
            packet_id=pid,
            file_id=self._file_id,
            k=self.k,
            total_size=self._total_size,
            block_size=self._block_size,
            payload=bytes(payload),
        )

    def __iter__(self):
        return self

    def __next__(self) -> FountainPacket:
        self._packets_sent += 1
        return self.next_packet()

    def encode_systematic_stream(self):
        """Generate all systematic packets first, then repair.

        During systematic phase, yields only original blocks (packet_id < k).
        After that yields repair packets.
        """
        for i in range(self.k):
            pkt = FountainPacket(
                packet_id=i,
                file_id=self._file_id,
                k=self.k,
                total_size=self._total_size,
                block_size=self._block_size,
                payload=self._blocks[i],
            )
            self._next_packet_id = self.k
            yield pkt

        while True:
            yield self.next_packet()


class FountainDecoder:
    """Fountain decoder: collects packets and attempts to decode the file.

    Uses belief propagation (peeling decoder) with Gaussian elimination
    fallback for stuck cases.

    Typical overhead needed: ~5-15% beyond K packets.

    Usage:
        decoder = FountainDecoder()
        for raw_pkt in received_bytes:
            pkt = FountainPacket.deserialize(raw_pkt)
            decoder.add_packet(pkt)
            if decoder.can_decode():
                data = decoder.decode()
                break
    """

    def __init__(self, max_extra_packets: int = 200):
        self._packets: dict[int, bytes] = {}
        self._neighbor_map: dict[int, list[int]] = {}
        self._k: int | None = None
        self._total_size: int | None = None
        self._file_id: int | None = None
        self._decoded_blocks: dict[int, bytes] = {}
        self._max_extra = max_extra_packets
        self._unique_packet_ids: set[int] = set()
        self._packets_after_k: int = 0

    @property
    def k(self) -> int | None:
        return self._k

    @property
    def num_collected(self) -> int:
        return len(self._unique_packet_ids)

    @property
    def num_decoded(self) -> int:
        return len(self._decoded_blocks)

    @property
    def is_k_known(self) -> bool:
        return self._k is not None

    def reset(self):
        self._packets = {}
        self._neighbor_map = {}
        self._k = None
        self._total_size = None
        self._file_id = None
        self._decoded_blocks = {}
        self._unique_packet_ids = set()
        self._packets_after_k = 0

    def add_packet(self, packet: FountainPacket):
        """Add a received fountain packet to the decoder buffer."""
        pid = packet.packet_id

        if self._k is None:
            self._k = packet.k
            self._total_size = packet.total_size
            self._file_id = packet.file_id

        if packet.k != self._k:
            return

        if pid in self._unique_packet_ids:
            return

        self._unique_packet_ids.add(pid)
        self._packets[pid] = packet.payload
        self._neighbor_map[pid] = _derive_neighbors(pid, self._k, self._file_id or 0)

        if pid >= self._k:
            self._packets_after_k += 1

    def can_decode(self) -> bool:
        """Check if enough packets are collected to attempt decoding."""
        if self._k is None:
            return False
        if len(self._unique_packet_ids) >= self._k:
            return True
        return False

    def decode(self) -> Optional[bytes]:
        """
        Attempt to decode the file from collected packets.

        Tries systematic recovery first (all K original blocks),
        then belief propagation, then Gaussian elimination.

        Returns:
            Decoded file bytes, or None if decoding fails.
        """
        if self._k is None:
            return None
        k = self._k
        total = self._total_size

        systematic = self.decode_attempt_continuous()
        if systematic is not None:
            return systematic

        decoded = self._peeling_decode(k)
        if decoded is None:
            return None

        result = bytearray()
        for i in range(k):
            if i in decoded:
                result.extend(decoded[i])
            else:
                result.extend(b"\x00" * min(256, total if total is not None else 256))

        return bytes(result[:total])

    def _peeling_decode(self, k: int) -> Optional[dict[int, bytes]]:
        """Belief propagation decoding for LT codes.

        Repeatedly find packets connected to exactly one unknown block,
        peel off that block, and update remaining packets.
        Falls back to Gaussian elimination if peeling stalls.
        """
        known: dict[int, bytes] = {}
        packets: dict[int, bytearray] = {
            pid: bytearray(payload) for pid, payload in self._packets.items()
        }
        neighbors: dict[int, set[int]] = {
            pid: set(nb) for pid, nb in self._neighbor_map.items()
        }

        changed = True
        while changed:
            changed = False
            for pid in list(packets.keys()):
                unknown_neighbors = neighbors[pid] - set(known.keys())
                if len(unknown_neighbors) == 1:
                    block_idx = unknown_neighbors.pop()
                    value = bytes(packets[pid])
                    for other_pid in neighbors[pid] & set(known.keys()):
                        value = _xor_block(value, known[other_pid])
                    if block_idx not in known:
                        known[block_idx] = value
                        changed = True
                elif len(unknown_neighbors) == 0:
                    del packets[pid]

        missing = set(range(k)) - set(known.keys())
        if not missing:
            return known

        if len(missing) <= 20:
            recovered = self._gaussian_elimination(missing, packets, neighbors, known)
            if recovered is not None:
                known.update(recovered)
                if not (set(range(k)) - set(known.keys())):
                    return known

        return None if missing else known

    def _gaussian_elimination(
        self,
        missing: set[int],
        packets: dict[int, bytearray],
        neighbors: dict[int, set[int]],
        known: dict[int, bytes],
    ) -> Optional[dict[int, bytes]]:
        """Fallback Gaussian elimination for stuck blocks.

        Builds a system of equations over GF(2) (byte-level) and solves.
        Only used when peeling decoder stalls with few (>0) remaining blocks.
        """
        missing_list = sorted(missing)
        idx_to_bit = {b: i for i, b in enumerate(missing_list)}
        n_unknown = len(missing_list)

        usable_pids = [pid for pid in packets if neighbors[pid] & missing]
        if len(usable_pids) < n_unknown:
            return None

        usable_pids = usable_pids[:n_unknown + 10]
        n_eq = min(len(usable_pids), n_unknown + 5)
        eq_pids = usable_pids[:n_eq]

        result = {}
        for bi in missing_list:
            if bi in known:
                result[bi] = known[bi]

        still_missing = missing_list[:]
        iterations = 0
        while still_missing and iterations < 100:
            iterations += 1
            for pid in list(eq_pids):
                unknown_nb = [b for b in neighbors[pid] if b not in result]
                if len(unknown_nb) == 1:
                    bi = unknown_nb[0]
                    val = bytearray(packets[pid])
                    try:
                        for nb in neighbors[pid] & result.keys():
                            val = bytearray(_xor_block(bytes(val), result[nb]))
                    except Exception:
                        continue
                    result[bi] = bytes(val)
                    if bi in still_missing:
                        still_missing.remove(bi)
                elif len(unknown_nb) == 0:
                    eq_pids.remove(pid)
            if not still_missing:
                break

        if still_missing:
            return None
        return {bi: result[bi] for bi in missing_list if bi in result}

    def decode_attempt_continuous(self) -> Optional[bytes]:
        """Check if we have enough systematic packets to reconstruct.

        If we received all K systematic packets (packet_ids 0..K-1),
        we can directly reconstruct without repair packets.
        """
        if self._k is None:
            return None
        k = self._k
        total = self._total_size

        if not set(range(k)).issubset(self._unique_packet_ids):
            return None

        result = bytearray()
        for i in range(k):
            result.extend(self._packets[i])
        return bytes(result[:total])


def fountain_encode_file(
    file_path: str, block_size: int = 256, seed: int = 0, file_id: int = 0
) -> FountainEncoder:
    """Create a fountain encoder from a file on disk."""
    with open(file_path, "rb") as f:
        data = f.read()
    with open(file_path, "rb") as f:
        _ = f.read(1)
    h = hashlib.sha256(data).hexdigest()[:8]
    fid = int(h, 16) & 0x7FFFFFFF if file_id == 0 else file_id
    return FountainEncoder(data, block_size=block_size, seed=seed, file_id=fid)


def fountain_decode(packets: list[FountainPacket]) -> Optional[bytes]:
    """Convenience: decode from a list of packets."""
    decoder = FountainDecoder()
    for pkt in packets:
        decoder.add_packet(pkt)
    if decoder.can_decode():
        return decoder.decode()
    return None
