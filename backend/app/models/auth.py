"""fastapi-users User model.

PDPL note: user account data (email, password hash) is the only PII in
this system. For v0 with internal users only, it sits in the same Postgres
instance as the analytical data. When external Saudi-resident users are
onboarded, this table must migrate to a KSA-resident Postgres instance
(STC Cloud, SalamCloud, or AWS me-central-1) per PDPL Article 29 and the
August 2024 Transfer Regulations. Document the split decision in the DR runbook
before any external user touches the system.
"""

from __future__ import annotations

from fastapi_users_db_sqlalchemy import SQLAlchemyBaseUserTableUUID

from app.core.database import Base


class User(SQLAlchemyBaseUserTableUUID, Base):
    """Application user — inherits id (UUID), email, hashed_password,
    is_active, is_superuser, is_verified from SQLAlchemyBaseUserTableUUID.

    Extend here with role, distribution_list membership, etc. as needed.
    """

    __tablename__ = "users"
