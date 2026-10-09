"""认证纯函数（无任何数据库/文件依赖，服务端账户体系与桌面本地单用户认证共用）

- 密码：scrypt$<hex盐>$<hex哈希>，参数与旧 Node 版 crypto.scryptSync 互通（16384/8/1/64）
- 会话：HMAC-SHA256 签名的 base64url 无状态令牌 {uid, iat, exp}；密钥由调用方注入
  （服务端复用 data/users.db.secret，桌面本地端用 data/local.secret）
"""
import base64
import hashlib
import hmac
import json
import secrets
import time

SESSION_TTL = 7 * 24 * 3600  # 7 天（秒）
SCRYPT_N, SCRYPT_R, SCRYPT_P, SCRYPT_DKLEN = 16384, 8, 1, 64  # 与 Node crypto.scryptSync 默认参数一致


# ---------- 密码哈希 ----------
def hash_password(password):
    salt = secrets.token_hex(16)
    digest = hashlib.scrypt(
        str(password).encode('utf-8'),
        salt=salt.encode('utf-8'),
        n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, dklen=SCRYPT_DKLEN,
        maxmem=64 * 1024 * 1024,
    ).hex()
    return f'scrypt${salt}${digest}'


def verify_password(password, stored):
    try:
        scheme, salt, digest = str(stored or '').split('$')
        if scheme != 'scrypt' or not salt or not digest:
            return False
        test = hashlib.scrypt(
            str(password).encode('utf-8'),
            salt=salt.encode('utf-8'),
            n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, dklen=SCRYPT_DKLEN,
            maxmem=64 * 1024 * 1024,
        ).hex()
        return hmac.compare_digest(test, digest)
    except Exception:
        return False


# ---------- 会话令牌 ----------
def _base64url(data):
    if isinstance(data, str):
        data = data.encode('utf-8')
    return base64.urlsafe_b64encode(data).decode('ascii').rstrip('=')


def _base64url_decode(text):
    return base64.urlsafe_b64decode(text + '=' * (-len(text) % 4))


def sign_session(uid, secret, ttl=SESSION_TTL):
    """签发会话令牌：base64url(payload).base64url(HMAC-SHA256)"""
    now = int(time.time() * 1000)
    payload = _base64url(json.dumps({'uid': uid, 'iat': now, 'exp': now + ttl * 1000}))
    sig = _base64url(hmac.new(secret.encode('utf-8'), payload.encode('utf-8'), hashlib.sha256).digest())
    return f'{payload}.{sig}'


def verify_session_token(token, secret):
    """校验令牌签名与有效期，返回 {uid, iat, exp} 或 None"""
    if not token or not isinstance(token, str) or '.' not in token:
        return None
    payload, sig = token.rsplit('.', 1)
    expect = _base64url(hmac.new(secret.encode('utf-8'), payload.encode('utf-8'), hashlib.sha256).digest())
    if not hmac.compare_digest(sig, expect):
        return None
    try:
        data = json.loads(_base64url_decode(payload))
        if not data.get('uid') or not data.get('exp') or data['exp'] < int(time.time() * 1000):
            return None
        return data
    except Exception:
        return None


def token_sig(token):
    """令牌的签名段（服务端吊销表 / 桌面本地内存吊销集的 key）"""
    if not token or not isinstance(token, str) or '.' not in token:
        return None
    return token.rsplit('.', 1)[1]
