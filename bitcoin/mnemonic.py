#!/usr/bin/python
from bitcoin.main import *
from bitcoin.pyspecials import safe_hexlify, safe_unhexlify, from_str_to_bytes, st, by, changebase
import string, unicodedata, random, hmac, re


def _get_directory():
    return os.path.join(os.path.dirname(__file__), 'wordlist')

def _get_wordlists():
    # TODO: add foreign languages for BIP39, https://github.com/bitcoin/bips/blob/master/bip-0039/bip-0039-wordlists.md
    # Try to access local lists, otherwise download text lists
    # Return tuple of wordlists: (ELECTRUM, BIP39)
    try:
        from bitcoin._electrum1wordlist import ELECTRUM_WORDS as ELEC
        from bitcoin._bip39wordlist import BIP0039_WORDLIST as BIP39
        from bitcoin._bip39japanese import BIP39JAP
    except ImportError:
        from bitcoin.bci import make_request
        ELEC, BIP39, BIP39JAP = map(
            lambda u: make_request(u).strip().split(),
            ("https://gist.githubusercontent.com/anonymous/f58f57780245db3cafc4/raw/" \
                + "1b5a9e81c0a356373e9e13aa720baef89d8fa856/electrum1_english_words",
             "https://github.com/bitcoin/bips/blob/master/bip-0039/english.txt",
             'https://github.com/bitcoin/bips/blob/master/bip-0039/japanese.txt'))
    finally:
        assert (len(BIP39) == 2048 and len(ELEC) == 1626)
    return ELEC, BIP39, BIP39JAP

global ELECWORDS, BIP39LIST
ELECWORDS, BIP39LIST, BIP39JAP = _get_wordlists()

def bip39_hex_to_mn(hexstr):
    if isinstance(hexstr, string_or_bytes_types) and re.match('^[0-9a-fA-F]*$', hexstr):
        hexstr = from_str_to_bytes(hexstr)
    else:
        raise TypeError("Enter a hex string!")

    if len(hexstr) not in xrange(4, 125, 4):
        raise Exception("32 < entropy < 992 bits only!")

    BIP39 = BIP39LIST   #if not lang else lang  # TODO: fix language debacle
    hexstr = safe_unhexlify(hexstr)
    cs = sha256(hexstr)     # sha256 hexdigest
    bstr = (changebase(safe_hexlify(hexstr), 16, 2, len(hexstr)*8) +
            changebase(cs, 16, 2, 256)[ : len(hexstr) * 8 // 32])
    return " ".join([BIP39[int(x, 2)] for x in [bstr[i:i + 11] for i in range(0, len(bstr), 11)]])

def bip39_mn_to_hex(mnemonic, saltpass='', lang=None):
    # TODO: add language functionality
    if isinstance(mnemonic, list):
        mn_norm_str = ' '.join(mnemonic)
    mn_norm_str = from_str_to_bytes(unicodedata.normalize('NKFD', mnemonic))

    assert bip39_check(mn_norm_str)
    return pbkdf2_hmac_sha512(mn_norm_str, b'mnemonic'+from_str_to_bytes(saltpass))

def bip39_check(mnemonic):
    """Assert mnemonic is BIP39 standard"""
    if isinstance(mnemonic, string_types):
        mn_array = from_str_to_bytes(mnemonic).split(" ")
    elif isinstance(mnemonic, list):
        mn_array = mnemonic
    else:
        raise TypeError

    # TODO: fix language integration
    BIP39 = BIP39LIST #if lang is None else lang

    assert len(mn_array) in range(3, 124, 3)
    assert len(mn_array) % 4 == 0
    assert all(map(lambda x: x in BIP39, mn_array))  # check all words are in list

    binstr = ''.join([changebase(st(BIP39.index(x)), 10, 2, 11) for x in mn_array])
    L = len(binstr)
    bd = binstr[:L // 33 * 32]
    cs = binstr[-L // 33:]
    hexd = safe_unhexlify(changebase(bd, 2, 16, L // 33 * 8))
    hexd_cs = changebase(hashlib.sha256(hexd).hexdigest(), 16, 2, 256)[:L // 33]
    return cs == hexd_cs

def random_bip39_pair(bits=128):
    """Generates a tuple of (hex seed, mnemonic)"""
    # TODO: add language functionality
    if bits % 32 != 0:
        raise Exception('%d not divisible by 32! Try 128 bits' % bits)
    hexseed = safe_hexlify(by(random_key()[:bits // 8]))       # CHECK FOR PY3
    return hexseed, bip39_hex_to_mn(hexseed)

def random_bip39_seed(bits=128):
    return random_bip39_pair(bits)[0]

def random_bip39_mn(bits=128, lang=None):
    # TODO: add language
    return random_bip39_pair(bits)[-1]

def elec1_mn_decode(mnemonic):
    """Decodes Electrum 1.x mnemonic phrase to hex seed"""
    if isinstance(mnemonic, string_types):
        mn_wordlist = from_str_to_bytes(mnemonic).lower().strip().split(" ")
    elif isinstance(mnemonic, list):
        mn_wordlist = mnemonic[:]

    wlist, words, n = mn_wordlist, ELECWORDS, 1626
    output = ''
    for i in range(len(wlist)//3):
        word1, word2, word3 = wlist[3*i:3*i+3]
        w1 =  words.index(word1)
        w2 = (words.index(word2))%n
        w3 = (words.index(word3))%n
        x = w1 + n*((w2-w1)%n) + n*n*((w3-w2)%n)
        output += '%08x' % x
    return output

def elec1_mn_encode(hexstr):
    if isinstance(hexstr, string_types) and re.match('^[0-9a-fA-F]*$', hexstr):
        hexstr = from_str_to_bytes(hexstr)
    else:
        raise TypeError("Bad input: hex string req!")

    message, words, n = hexstr, ELECWORDS, 1626
    assert len(message) % 8 == 0
    out = []
    for i in range(len(message)//8):
        word = message[8*i:8*i+8]
        x = int(word, 16)
        w1 = (x%n)
        w2 = ((x//n) + w1)%n
        w3 = ((x//n//n) + w2)%n
        out += [words[w1], words[w2], words[w3]]
    return ' '.join(out)

def generate_elec2_seed(num_bits=128, prefix='01', custom_entropy=1):
    # TODO: https://github.com/spesmilo/electrum/blob/feature/newsync/lib/bitcoin.py#L155
    import random, math
    n = int(math.ceil(math.log(custom_entropy, 2)))
    k = len(prefix)*4                            # amount of lost entropy from '01' req
    n_added = max(16, k + num_bits - n)          # 136 - lost = 128 bits entropy
    entropy = random.randrange(pow(2, n_added))  # decode(os.urandom((1+len("%x"%pow(2,n_added))//2)),256)

    nonce = 0
    while True:     # cycle thru values until HMAC == 0x01...cdef ...
        nonce += 1
        i = custom_entropy * (entropy + nonce)
        mn_seed = elec2_mn_encode(i)
        assert i == elec2_mn_decode(mn_seed)
        if is_elec1_seed(mn_seed): continue         # ensure seed NOT elec1 compatible
        if is_elec2_seed(mn_seed, prefix): break
    return mn_seed

random_electrum2_seed = random_elec2_seed = generate_elec2_seed

def elec2_mn_encode(i):
    """Encodes int, i, as Electrum 2 mnemonic"""
    n = len(BIP39LIST)
    words = []
    while i:
        x = i%n
        i //= n
        words.append(BIP39LIST[x])
    return ' '.join(words)

def elec2_mn_decode(mn_seed, lang=None):
    words = prepare_elec2_seed(mn_seed).split()
    wordlist = BIP39LIST if not lang else BIP39JAP
    n = 2048
    i = 0
    while words:
        w = words.pop()
        k = wordlist.index(w)
        i = i*n + k
    return i

def elec2_check_seed(mn_seed, custom_entropy=1):
    assert is_elec2_seed(mn_seed)
    i = elec2_mn_decode(mn_seed)
    return i % custom_entropy == 0

def is_elec2_seed(seed, prefix='01'):
    assert prefix in ('01', '101')
    hmac_sha_512 = lambda x, y: hmac.new(x, y, hashlib.sha512).hexdigest()
    s = hmac_sha_512('Seed version', seed)
    return s.startswith(prefix)

def is_elec1_seed(seed):
    words = seed.strip().split()
    try:
        elec1_mn_decode(words)
        uses_electrum_words = True
    except Exception:
        uses_electrum_words = False
    try:
        safe_unhexlify(seed)
        is_hex = (len(seed) == 32 or len(seed) == 64)
    except Exception:
        is_hex = False
    return is_hex or (uses_electrum_words and (len(words) == 12 or len(words) == 24))

def prepare_elec2_seed(seed):
    # normalize
    seed = unicodedata.normalize('NFKD', unicode(seed)) \
        if is_python2 else unicodedata.normalize('NFKD', seed)
    seed = seed.lower()         # lower
    seed = u''.join([c for c in seed if not unicodedata.combining(c)])  # remove accents
    seed = u' '.join(seed.split())          # normalize whitespaces
    seed = u''.join([seed[i] for i in range(len(seed))
                    if not (seed[i] in string.whitespace and
                    is_CJK(seed[i-1]) and is_CJK(seed[i+1]))])
    return seed

def is_CJK(c):
        # http://www.asahi-net.or.jp/~ax2s-kmtn/ref/unicode/e_asia.html
        CJK_INTERVALS = [(0x4E00, 0x9FFF, 'CJK Unified Ideographs'), (0x3400, 0x4DBF, 'CJK Unified Ideographs Extension A'), (0x20000, 0x2A6DF, 'CJK Unified Ideographs Extension B'), (0x2A700, 0x2B73F, 'CJK Unified Ideographs Extension C'), (0x2B740, 0x2B81F, 'CJK Unified Ideographs Extension D'), (0xF900, 0xFAFF, 'CJK Compatibility Ideographs'), (0x2F800, 0x2FA1D, 'CJK Compatibility Ideographs Supplement'), (0x3190, 0x319F , 'Kanbun'), (0x2E80, 0x2EFF, 'CJK Radicals Supplement'), (0x2F00, 0x2FDF, 'CJK Radicals'), (0x31C0, 0x31EF, 'CJK Strokes'), (0x2FF0, 0x2FFF, 'Ideographic Description Characters'), (0xE0100, 0xE01EF, 'Variation Selectors Supplement'), (0x3100, 0x312F, 'Bopomofo'), (0x31A0, 0x31BF, 'Bopomofo Extended'), (0xFF00, 0xFFEF, 'Halfwidth and Fullwidth Forms'), (0x3040, 0x309F, 'Hiragana'), (0x30A0, 0x30FF, 'Katakana'), (0x31F0, 0x31FF, 'Katakana Phonetic Extensions'), (0x1B000, 0x1B0FF, 'Kana Supplement'), (0xAC00, 0xD7AF, 'Hangul Syllables'), (0x1100, 0x11FF, 'Hangul Jamo'), (0xA960, 0xA97F, 'Hangul Jamo Extended A'), (0xD7B0, 0xD7FF, 'Hangul Jamo Extended B'), (0x3130, 0x318F, 'Hangul Compatibility Jamo'), (0xA4D0, 0xA4FF, 'Lisu'), (0x16F00, 0x16F9F, 'Miao'), (0xA000, 0xA48F, 'Yi Syllables'), (0xA490, 0xA4CF, 'Yi Radicals'),]
        n = ord(c)
        for i_min, i_max, name in CJK_INTERVALS:
            if i_max >= n >= i_min:
                return True
        return False