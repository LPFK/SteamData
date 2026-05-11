import os
import datetime
import bcrypt
import jwt
from cryptography.fernet import Fernet
from dotenv import load_dotenv

load_dotenv()

JWT_SECRET: str = os.getenv("JWT_SECRET", "")
FERNET_KEY: bytes = os.getenv("FERNET_KEY", "").encode()

if not JWT_SECRET:
    raise EnvironmentError("JWT_SECRET not set in .env")
if not FERNET_KEY:
    raise EnvironmentError("FERNET_KEY not set in .env")

_cipher = Fernet(FERNET_KEY)


def hash_password(password: str) -> str:
    # rounds=12 is the minimum for me
    return bcrypt.hashpw(
        password.encode("utf-8"),
        bcrypt.gensalt(rounds=12)
    ).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    # bcrypt.checkpw handles constant-time comparison internally
    return bcrypt.checkpw(
        password.encode("utf-8"),
        password_hash.encode("utf-8")
    )


def encrypt_field(value: str) -> str:
    # used for any sensitive field stored in the database (email, phone...)
    return _cipher.encrypt(value.encode("utf-8")).decode("utf-8")


def decrypt_field(token: str) -> str:
    # raises InvalidToken if the value was tampered with or the key is wrong
    return _cipher.decrypt(token.encode("utf-8")).decode("utf-8")


def create_token(user_id: int, role: str, expires_minutes: int = 30) -> str:
    payload = {
        "sub": str(user_id),
        "role": role,
        "exp": datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=expires_minutes),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


def verify_token(token: str) -> dict | None:
    # algorithms must be explicit here, otherwise the alg=none attack works
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None
