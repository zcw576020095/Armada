from django.db.backends.signals import connection_created
from django.dispatch import receiver


@receiver(connection_created)
def setup_sqlite_pragmas(sender, connection, **kwargs):
    """为每个 SQLite 连接设置 PRAGMA，提升并发写性能"""
    if connection.vendor == 'sqlite':
        cursor = connection.cursor()
        # WAL 模式：读写不互斥，写者之间靠 busy_timeout 排队
        cursor.execute('PRAGMA journal_mode=WAL;')
        cursor.execute('PRAGMA synchronous=NORMAL;')
        cursor.execute('PRAGMA busy_timeout=30000;')  # 30 秒
        cursor.execute('PRAGMA temp_store=MEMORY;')
        cursor.close()
