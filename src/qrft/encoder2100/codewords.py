"""Zero-safe QR Reed-Solomon codewords, scoped to the independent encoder.

qrcode 8.2's Polynomial constructor retains one zero for an all-zero block,
then Polynomial.__mod__ calls glog(0). Use iterative GF(256) division, with
zero coefficients explicitly skipped. No monkey patch or change to old encoders.
"""


def create_codewords(qr):
    from qrcode import base, exceptions, util

    bits = util.BitBuffer()
    for data in qr.data_list:
        bits.put(data.mode, 4)
        bits.put(len(data), util.length_in_bits(data.mode, qr.version))
        data.write(bits)
    blocks = base.rs_blocks(qr.version, qr.error_correction)
    capacity = sum(block.data_count for block in blocks) * 8
    if len(bits) > capacity:
        raise exceptions.DataOverflowError("Version 40-L alphanumeric capacity exceeded")
    bits.put(0, min(4, capacity - len(bits)))
    bits.put(0, (-len(bits)) % 8)
    for i in range((capacity - len(bits)) // 8):
        bits.put(0xEC if i % 2 == 0 else 0x11, 8)
    offset, data_blocks, correction_blocks = 0, [], []
    for block in blocks:
        data = bits.buffer[offset : offset + block.data_count]
        offset += block.data_count
        count = block.total_count - block.data_count
        # qrcode's published QR generator-polynomial table; no mutable globals.
        polynomial = util.LUT.rsPoly_LUT[count]
        work = data + [0] * count
        for i in range(len(data)):
            coefficient = work[i]
            if not coefficient:
                continue
            exponent = base.glog(coefficient)
            for j, factor in enumerate(polynomial):
                if factor:
                    work[i + j] ^= base.gexp(exponent + base.glog(factor))
        data_blocks.append(data)
        correction_blocks.append(work[-count:])
    result = []
    for groups in (data_blocks, correction_blocks):
        for i in range(max(map(len, groups))):
            result.extend(block[i] for block in groups if i < len(block))
    return result
