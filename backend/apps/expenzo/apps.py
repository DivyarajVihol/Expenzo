import logging

from django.apps import AppConfig
from django.db import OperationalError
from django.db.backends.signals import connection_created

logger = logging.getLogger(__name__)


def configure_sqlite_connection(sender, connection, **kwargs):
    """Apply per-connection SQLite settings without breaking app startup."""
    if connection.vendor != "sqlite":
        return

    try:
        with connection.cursor() as cursor:
            # Set the timeout before attempting any pragma that may need a lock.
            cursor.execute("PRAGMA busy_timeout = 20000;")
            try:
                # WAL is persistent at the database level; setting it on every
                # connection can race with other workers during startup.
                cursor.execute("PRAGMA journal_mode = WAL;")
            except OperationalError:
                logger.warning(
                    "Could not set SQLite WAL mode on this connection; "
                    "continuing with the database's existing journal mode.",
                    exc_info=True,
                )
            cursor.execute("PRAGMA synchronous = NORMAL;")
            cursor.execute("PRAGMA cache_size = -2000;")
    except OperationalError:
        # A transient lock while configuring optional performance pragmas
        # must not prevent a user's request from opening the database.
        logger.warning(
            "Could not apply all SQLite connection pragmas.",
            exc_info=True,
        )


class ExpenzoConfig(AppConfig):
    name = "apps.expenzo"
    label = "expenzo"

    def ready(self):
        connection_created.connect(
            configure_sqlite_connection,
            dispatch_uid="expenzo.configure_sqlite_connection",
        )
