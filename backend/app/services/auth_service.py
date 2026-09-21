import hashlib
import hmac
import secrets
from datetime import datetime
from typing import Optional, Tuple
from sqlalchemy.orm import Session
from backend.app.models.database_models import User

class AuthService:
    """
    Secure authentication service using salted PBKDF2-HMAC-SHA256 password hashing
    (OWASP recommended standard) and URL-safe cryptographically secure session tokens.
    """

    @staticmethod
    def hash_password(password: str) -> str:
        """Hashes password using PBKDF2-HMAC-SHA256 with 100,000 iterations and unique 16-byte salt."""
        salt = secrets.token_bytes(16)
        key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100_000)
        return f"{salt.hex()}${key.hex()}"

    @staticmethod
    def verify_password(password: str, stored_hash: str) -> bool:
        """Verifies candidate password against stored salt$hash in constant time."""
        if not stored_hash or "$" not in stored_hash:
            return False
        try:
            salt_hex, key_hex = stored_hash.split("$", 1)
            salt = bytes.fromhex(salt_hex)
            expected_key = bytes.fromhex(key_hex)
            actual_key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100_000)
            return hmac.compare_digest(actual_key, expected_key)
        except Exception:
            return False

    @staticmethod
    def generate_token() -> str:
        """Generates a cryptographically strong URL-safe session token."""
        return secrets.token_urlsafe(32)

    @classmethod
    def seed_default_admin(cls, db: Session) -> User:
        """Ensures an administrative operator exists in the database."""
        admin = db.query(User).filter((User.username == "admin") | (User.email == "admin@gridwise.ai")).first()
        if not admin:
            admin = User(
                username="admin",
                email="admin@gridwise.ai",
                hashed_password=cls.hash_password("GridWise@2026"),
                role="admin",
                is_active=True,
                created_at=datetime.utcnow()
            )
            db.add(admin)
            db.commit()
            db.refresh(admin)
        return admin

    @classmethod
    def authenticate(cls, db: Session, username_or_email: str, password: str) -> Optional[Tuple[User, str]]:
        """Authenticates credentials, generates and persists a new session token."""
        identifier = username_or_email.strip().lower()
        user = db.query(User).filter(
            (User.username == identifier) | (User.email == identifier)
        ).first()

        if not user or not user.is_active or not user.hashed_password:
            return None

        if not cls.verify_password(password, user.hashed_password):
            return None

        # Issue session token
        token = cls.generate_token()
        user.session_token = token
        user.last_login = datetime.utcnow()
        db.commit()
        db.refresh(user)
        return user, token

    @classmethod
    def get_user_by_token(cls, db: Session, token: str) -> Optional[User]:
        """Retrieves user by active session token."""
        if not token:
            return None
        return db.query(User).filter(User.session_token == token, User.is_active == True).first()

    @classmethod
    def logout(cls, db: Session, token: str) -> bool:
        """Invalidates user session token."""
        user = cls.get_user_by_token(db, token)
        if user:
            user.session_token = None
            db.commit()
            return True
        return False
