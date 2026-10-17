from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.infrastructure.database.session import get_engine


def check_database_connection() -> bool:
    """Check whether the database can execute a simple query."""
    try:
        with get_engine().connect() as connection:
            connection.execute(text("SELECT 1"))

        return True

    except SQLAlchemyError:
        return False
