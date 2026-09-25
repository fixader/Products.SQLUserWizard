"""Opt-in destructive tests: SQLUW_TEST_DSN MUST name an empty disposable DB.

Run directly with Python, with the candidate src on PYTHONPATH and
Products.OpenODBCDA installed. Never point this at an application database.
"""
import json
import os
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from OFS.Folder import Folder
from OFS.SimpleItem import SimpleItem
from Products.ZSQLMethods.SQL import SQL
from Products.OpenODBCDA.db import OpenODBCDatabaseConnection
from Products.SQLUserWizard.config import DEFAULT_TABLES, postgresql_templates
from Products.SQLUserWizard.invitation_sql import invitation_templates


class LabConnection(SimpleItem):
    """Acquisition bridge to the real OpenODBCDA pool used by Z SQL Methods."""
    id = 'lab_db'

    def __init__(self, pool):
        self.pool = pool

    def __call__(self):
        return self.pool

    def sql_quote__(self, value):
        return "'" + value.replace("'", "''") + "'"


class AtomicInvitations(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = OpenODBCDatabaseConnection(os.environ['SQLUW_TEST_DSN'], pool_size=4)
        cls.specs = invitation_templates('postgresql', identity_tables=DEFAULT_TABLES)
        cls.folder = Folder('lab')
        cls.folder._setObject('lab_db', LabConnection(cls.db))
        for spec in cls.specs.values():
            method = SQL(spec['id'], spec['title'], 'lab_db', spec['arguments'], spec['template'])
            method.max_cache_ = 0
            method.cache_time_ = 0
            cls.folder._setObject(spec['id'], method)
        # Refuse existing managed tables before executing any DDL.
        assert not cls.db.query("select tablename from pg_tables where schemaname='public'")[1]
        specs = postgresql_templates()
        for key in ('setup_users', 'setup_profiles', 'setup_roles', 'setup_user_roles'):
            cls.db.query(specs[key]['template'])
        for key in ('setup', 'setup_roles'):
            cls.run_sql(key)

    @classmethod
    def run_sql(cls, key, **values):
        return cls.folder._getOb(cls.specs[key]['id'])(**values)

    def setUp(self):
        self.db.query('truncate pas_invitation_roles, pas_invitations, pas_user_roles, '
                      'pas_user_profiles, pas_roles, pas_users')

    def invite(self, key='one', roles=('Member',)):
        return self.run_sql('create_atomic', invitation_id=key, secret_hash=key,
            email="o'hara@example.invalid", phone='', proposed_user_id='', proposed_login='',
            identity_reference='', creator_id='manager', created_at=int(time.time()),
            expires_at=int(time.time()) + 3600, roles_json=json.dumps(roles))

    def complete(self, key='one', user='new', login=None):
        return self.run_sql('complete_atomic', secret_hash=key, user_id=user,
            login_name=login or user, password='test-hash', password_hash_id='authencoding',
            allowed_roles_json='["Member"]', totp_required=1,
            first_name='Test', last_name='', display_name='', mobile='')

    def count(self, table):
        return self.db.query('select count(*) from ' + table)[1][0][0]

    def test_complete_and_replay(self):
        self.invite()
        self.assertEqual(len(self.complete()), 1)
        self.assertFalse(self.complete(user='replay'))
        for table in DEFAULT_TABLES.values():
            self.assertEqual(self.count(table), 1)
        row = self.db.query('select recovery_email from pas_users '
                            'where totp_required=true and totp_enabled=false')[1][0]
        self.assertEqual(row[0], "o'hara@example.invalid")

    def test_concurrent_completion(self):
        self.invite()
        start = Barrier(4)
        def attempt(n):
            start.wait()
            return self.complete(user='user' + str(n))
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(attempt, range(4)))
        self.assertEqual(sum(bool(r) for r in results), 1)
        self.assertEqual(self.count('pas_users'), 1)

    def test_failures_roll_back_every_write_and_connection_recovers(self):
        self.db.query("create or replace function fail_invitation_test() returns trigger "
                      "language plpgsql as $$ begin raise exception 'injected failure'; end $$")
        for table, event in (('pas_users', 'insert'), ('pas_user_profiles', 'insert'),
                             ('pas_roles', 'insert'), ('pas_user_roles', 'insert'),
                             ('pas_invitations', 'update')):
            with self.subTest(table=table):
                self.setUp()
                self.invite()
                self.db.query('create trigger fail_test before ' + event + ' on ' + table +
                              ' for each row execute function fail_invitation_test()')
                try:
                    with self.assertRaises(Exception):
                        self.complete()
                    self.assertEqual(self.db.query('select 1')[1][0][0], 1)
                    for identity_table in DEFAULT_TABLES.values():
                        self.assertEqual(self.count(identity_table), 0)
                    self.assertEqual(self.db.query('select accepted_at, result_user_id from pas_invitations')[1][0], (None, None))
                finally:
                    self.db.query('drop trigger fail_test on ' + table)
                self.assertEqual(len(self.complete()), 1)

    def test_duplicate_identity_preserves_existing_user_and_invitation(self):
        self.invite()
        self.complete()
        self.invite('two')
        for user, login in (('new', 'different'), ('different', 'new')):
            with self.assertRaises(Exception):
                self.complete('two', user, login)
            self.assertEqual(self.count('pas_users'), 1)
        self.assertEqual(len(self.complete('two', 'unique')), 1)

    def test_invalid_roles_and_revoked_or_expired_invites(self):
        self.invite(roles=('Manager',))
        self.assertFalse(self.complete())
        self.setUp()
        self.invite()
        self.db.query('update pas_invitations set expires_at=1')
        self.assertFalse(self.complete())
        self.db.query('update pas_invitations set expires_at=9999999999, revoked_at=1')
        self.assertFalse(self.complete())
        self.assertEqual(self.count('pas_users'), 0)

    def test_invitation_role_failure_rolls_back_parent(self):
        with self.assertRaises(Exception):
            self.invite(roles=('Member', 'Member'))
        self.assertEqual(self.count('pas_invitations'), 0)
        self.assertEqual(self.count('pas_invitation_roles'), 0)
        self.invite()


if __name__ == '__main__':
    unittest.main(verbosity=2)
