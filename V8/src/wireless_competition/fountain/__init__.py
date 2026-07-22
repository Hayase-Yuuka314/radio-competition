"""Fountain code module for reliable one-way file transfer.

Uses LT codes with Robust Soliton degree distribution to enable
no-ACK transmission where the receiver needs only ~K+epsilon packets
to recover K source blocks.
"""

from .raptorq import FountainEncoder, FountainDecoder, fountain_encode_file, fountain_decode

__all__ = ["FountainEncoder", "FountainDecoder", "fountain_encode_file", "fountain_decode"]
