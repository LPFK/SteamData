
from app.models import init_db, get_session, User
from app.auth import (
    hash_password,
    verify_password,
    encrypt_field,
    decrypt_field,
    create_token,
    verify_token,
)


def main() -> None:
    print("step 1 | init database")
    init_db()

    print("step 2 | register user")

    raw_email    = "lilian@datastory.local"
    raw_password = "S3cur3P@ssw0rd!"

    session = get_session()

    existing = session.query(User).filter_by(username="lilian").first()
    if existing:
        print("  user already exists, skipping insert")
        user = existing
    else:
        user = User(
            username        = "lilian",
            email_encrypted = encrypt_field(raw_email),
            password_hash   = hash_password(raw_password),
            role            = "admin",
        )
        session.add(user)
        session.commit()
        print(f"  inserted: {user}")

    print("step 3 | read from DB and decrypt email")

    fetched = session.query(User).filter_by(username="lilian").one()
    decrypted_email = decrypt_field(fetched.email_encrypted)

    print(f"  stored  : {fetched.email_encrypted[:40]}...")
    print(f"  decoded : {decrypted_email}")
    assert decrypted_email == raw_email

    print("step 4 | verify password")

    ok     = verify_password(raw_password, fetched.password_hash)
    not_ok = verify_password("wrongpassword", fetched.password_hash)

    print(f"  correct password : {ok}")
    print(f"  wrong password   : {not_ok}")
    assert ok is True
    assert not_ok is False

    print("step 5 | JWT create and verify")

    token = create_token(user_id=fetched.id, role=fetched.role, expires_minutes=30)
    print(f"  token   : {token[:40]}...")

    payload = verify_token(token)
    print(f"  payload : {payload}")
    assert payload is not None
    assert payload["role"] == "admin"

    invalid = verify_token("this.is.not.a.real.token")
    assert invalid is None
    print("  invalid token correctly rejected")

    session.close()
    print("all checks passed")


if __name__ == "__main__":
    main()
