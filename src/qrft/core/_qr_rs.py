"""Zero-safe QR codewords for every production frame, avoiding qrcode's glog(0) bug.

Every logarithm operates on a nonzero GF(256) element. Zero coefficients simply
contribute zero; data modes, block tables, padding and symbol rendering stay unchanged.
"""

from functools import lru_cache

from qrcode import base, util
from qrcode.exceptions import DataOverflowError


@lru_cache(maxsize=32)
def _generator(degree):
    """Multiply (x + alpha**i) factors in GF(256), including zero coefficients."""
    coefficients = [1]
    for power in range(degree):
        product = [0] * (len(coefficients) + 1)
        for index, coefficient in enumerate(coefficients):
            product[index] ^= coefficient
            if coefficient:
                product[index + 1] ^= base.gexp(base.glog(coefficient) + power)
        coefficients = product
    return tuple(coefficients)


def _parity(data, degree):
    remainder = [*data, *([0] * degree)]
    divisor = _generator(degree)
    for offset in range(len(data)):
        leading = remainder[offset]
        if not leading:
            continue  # A zero leading coefficient contributes nothing to this division step.
        exponent = base.glog(leading)
        for index, coefficient in enumerate(divisor):
            if coefficient:
                remainder[offset + index] ^= base.gexp(exponent + base.glog(coefficient))
    return remainder[-degree:]


def create_codewords(version, correction, segments):
    """Encode the same QR segments and interleave zero-safe RS parity bytes."""
    blocks = base.rs_blocks(version, correction)
    capacity = sum(block.data_count for block in blocks) * 8
    bits = util.BitBuffer()
    for segment in segments:
        bits.put(segment.mode, 4)
        bits.put(len(segment), util.length_in_bits(segment.mode, version))
        segment.write(bits)
    if len(bits) > capacity:
        raise DataOverflowError("QR data exceeds symbol capacity")
    for _ in range(min(4, capacity - len(bits))):
        bits.put_bit(False)
    while len(bits) % 8:
        bits.put_bit(False)
    for index in range((capacity - len(bits)) // 8):
        bits.put((util.PAD0, util.PAD1)[index % 2], 8)

    data_blocks, parity_blocks = [], []
    position = 0
    for block in blocks:
        end = position + block.data_count
        data = bits.buffer[position:end]
        data_blocks.append(data)
        parity_blocks.append(_parity(data, block.total_count - block.data_count))
        position = end
    result = []
    for group in (data_blocks, parity_blocks):
        for column in range(max(map(len, group))):
            result.extend(words[column] for words in group if column < len(words))
    return result
