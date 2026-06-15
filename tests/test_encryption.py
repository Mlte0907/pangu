"""盘古 encryption.py 测试 — E2E 加密模块"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestEncryption:
    """E2E 加密测试"""

    def test_encrypt_decrypt(self):
        from pangu.memory.encryption import encrypt, decrypt
        plaintext = '测试加密内容'
        ciphertext = encrypt(plaintext)
        assert ciphertext != plaintext
        assert ciphertext.startswith('gAAAAA')
        decrypted = decrypt(ciphertext)
        assert decrypted == plaintext

    def test_encrypt_empty(self):
        from pangu.memory.encryption import encrypt, decrypt
        result = encrypt('')
        # 空字符串加密后应可解密还原
        decrypted = decrypt(result)
        assert decrypted == ''

    def test_decrypt_plaintext(self):
        from pangu.memory.encryption import decrypt
        # 解密未加密的文本应直接返回
        result = decrypt('这是明文')
        assert result == '这是明文'

    def test_is_enabled(self):
        from pangu.memory.encryption import is_enabled
        result = is_enabled()
        assert isinstance(result, bool)

    def test_encrypt_unicode(self):
        from pangu.memory.encryption import encrypt, decrypt
        plaintext = '中文测试 🔐'
        ciphertext = encrypt(plaintext)
        decrypted = decrypt(ciphertext)
        assert decrypted == plaintext

    def test_encrypt_long_text(self):
        from pangu.memory.encryption import encrypt, decrypt
        plaintext = '这是一段很长的文本' * 100
        ciphertext = encrypt(plaintext)
        decrypted = decrypt(ciphertext)
        assert decrypted == plaintext
