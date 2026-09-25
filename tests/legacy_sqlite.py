"""Disposable adapter shared with the old-release export subprocess."""
import sqlite3
from OFS.SimpleItem import SimpleItem


class SQLiteConnection(SimpleItem):
    id = "test_db"
    title = "Upgrade test database"
    meta_type = "Test Database Connection"

    def __init__(self):
        self._v_db = sqlite3.connect(":memory:")

    def __call__(self):
        return self

    def sql_quote__(self, value):
        return "'" + str(value).replace("'", "''") + "'"

    def query(self, sql, max_rows=1000):
        cursor = self._v_db.execute(sql)
        columns = [dict(name=c[0], type="s", width=0, null=True) for c in cursor.description or ()]
        return columns, cursor.fetchmany(max_rows) if columns else []
