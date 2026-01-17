"""DEPRECATED: Legacy database configuration.

⚠️  This module is DEPRECATED and should NOT be used.
⚠️  Use app.core.database instead.

Historical note:
  - This was the original database setup before app/core/database.py was created
  - app/core/database.py provides better retry logic, connection pooling, and error handling
  - Kept here for backward compatibility only

Migration path:
  OLD: from app.db.database import get_db, engine, Base
  NEW: from app.core.database import get_db_session, engine, Base
"""

import warnings

# Issue deprecation warning
warnings.warn(
    "app.db.database is deprecated. Use app.core.database instead.",
    DeprecationWarning,
    stacklevel=2
)

# Re-export from app/core/database for backward compatibility
# ⚠️ Only for temporary backward compatibility - DO NOT USE IN NEW CODE
from app.core.database import (
    engine,
    async_session,
    Base,
    get_db,
    get_db_session,
    init_db,
    close_db,
)

__all__ = [
    "engine",
    "async_session",
    "Base",
    "get_db",
    "get_db_session",
    "init_db",
    "close_db",
]
