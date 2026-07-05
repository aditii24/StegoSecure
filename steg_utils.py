from PIL import Image

def _bits_from_bytes(b):
    for byte in b:
        for i in range(8):
            yield (byte >> (7 - i)) & 1

def _bytes_from_bits(bits):
    out = bytearray()
    current = 0
    count = 0
    for bit in bits:
        current = (current << 1) | bit
        count += 1
        if count == 8:
            out.append(current)
            current = 0
            count = 0
    return bytes(out)

# 🟩 HIDE message inside PNG image
def hide_message_in_image_file(in_path, secret_text, out_path):
    """
    Hides a UTF-8 text message inside a PNG image using LSB of red channel.
    Stores message length (4 bytes big-endian) + message bytes.
    """
    img = Image.open(in_path)
    img = img.convert("RGBA")
    pixels = list(img.getdata())

    msg_bytes = secret_text.encode("utf-8")
    msg_len = len(msg_bytes)

    if msg_len == 0:
        raise ValueError("Message is empty")

    # Create bits: 32 bits length header + message bits
    header_bits = [(msg_len >> i) & 1 for i in range(31, -1, -1)]
    message_bits = list(_bits_from_bytes(msg_bytes))
    all_bits = header_bits + message_bits

    if len(all_bits) > len(pixels):
        raise ValueError("Message too long for this image")

    new_pixels = []
    bit_index = 0

    for px in pixels:
        r, g, b, a = px
        if bit_index < len(all_bits):
            r = (r & ~1) | all_bits[bit_index]
            bit_index += 1
        new_pixels.append((r, g, b, a))

    img.putdata(new_pixels)
    img.save(out_path, "PNG")
    print(f"✅ Hidden message saved to {out_path}")


# 🟥 EXTRACT message from image
def extract_message_from_image_file(path):
    """
    Extracts a hidden UTF-8 message from a PNG (or converted JPEG).
    Reads 32 bits = message length in bytes, then message bits.
    Uses LSB of red channel.
    """
    img = Image.open(path)
    img = img.convert("RGBA")
    pixels = img.getdata()

    def bit_gen():
        for px in pixels:
            yield px[0] & 1  # LSB of red channel

    g = bit_gen()

    # read 32 bits for length
    length_bits = [next(g) for _ in range(32)]
    msg_len = 0
    for b in length_bits:
        msg_len = (msg_len << 1) | b

    if msg_len <= 0 or msg_len > (img.width * img.height // 8):
        return None

    # read message bits
    msg_bits = [next(g) for _ in range(msg_len * 8)]
    b = _bytes_from_bits(msg_bits)
    try:
        return b.decode("utf-8", errors="replace")
    except Exception:
        return b.decode("latin1", errors="replace")
