from jose import JWTError, jwt
from datetime import datetime, timedelta
from typing import Optional

from src.config import settings


class JWTHandler:
    def __init__(self):
        self.secret = settings.jwt_secret
        self.algorithm = settings.jwt_algorithm
        self.expiration_days = settings.jwt_expiration_days

    def create_token(self, kiosk_id: str) -> str:
        """Generate JWT token for a kiosk"""
        expires_at = datetime.utcnow() + timedelta(days=self.expiration_days)

        payload = {
            "kiosk_id": kiosk_id,
            "iat": datetime.utcnow(),
            "exp": expires_at
        }

        token = jwt.encode(payload, self.secret, algorithm=self.algorithm)
        return token

    def verify_token(self, token: str) -> Optional[str]:
        """Verify JWT token and return kiosk_id if valid"""
        try:
            payload = jwt.decode(token, self.secret, algorithms=[self.algorithm])
            kiosk_id: str = payload.get("kiosk_id")

            if kiosk_id is None:
                return None

            return kiosk_id
        except JWTError:
            return None


# Global JWT handler instance
jwt_handler = JWTHandler()
