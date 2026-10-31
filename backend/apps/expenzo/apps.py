from django.apps import AppConfig
from django.db.backends.signals import connection_created


def configure_sqlite_connection(sender, connection, **kwargs):
    """
    Optimize SQLite for multi-worker web environments (such as LSAPI on cPanel).
    - WAL journal mode: readers do not block writers and writers do not block readers.
    - synchronous NORMAL: fast, safe write operations without unnecessary fsync delays.
    - busy_timeout 20000: wait up to 20 seconds for locks instead of failing immediately.
    - cache_size -2000: 2MB in-memory page cache per connection.
    """
    if connection.vendor == 'sqlite':
        with connection.cursor() as cursor:
            cursor.execute("PRAGMA journal_mode = WAL;")
            cursor.execute("PRAGMA synchronous = NORMAL;")
            cursor.execute("PRAGMA busy_timeout = 20000;")
            cursor.execute("PRAGMA cache_size = -2000;")


class ExpenzoConfig(AppConfig):
    name = 'apps.expenzo'
    label = 'expenzo'

    def ready(self):
        connection_created.connect(configure_sqlite_connection)
