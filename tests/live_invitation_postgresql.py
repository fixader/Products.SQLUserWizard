"""Opt-in destructive tests: SQLUW_TEST_DSN MUST name an empty disposable DB.

Run directly with Python, with the candidate src on PYTHONPATH and
Products.OpenODBCDA installed. Never point this at an application database.
"""
import os
import unittest
import transaction
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from OFS.Folder import Folder
from OFS.SimpleItem import SimpleItem
from Products.ZSQLMethods.SQL import SQL
from Products.OpenODBCDA.connection import OpenODBCConnection
from Products.SQLUserWizard.config import DEFAULT_TABLES, postgresql_templates
from Products.SQLUserWizard.invitation_sql import invitation_templates
from Products.SQLUserWizard.provisioning import SQLUserProvisioning


class NoFallbackUsers(SimpleItem):
    # The database uniqueness constraints are deliberately authoritative here.
    def getUserById(self, user_id):
        return None

    def getUser(self, login):
        return None


class DatabaseTestController(SQLUserProvisioning):
    # Permission/CSRF/PAS placement are covered by the local integration suite.
    # This harness executes the production controller's database workflow.
    def _check(self, *args, **kwargs):
        pass

    def _plugin(self):
        return self.aq_parent


class AtomicInvitations(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        connector = OpenODBCConnection('lab_db', 'Disposable test',
            connection_string=os.environ['SQLUW_TEST_DSN'], pool_enabled=True, pool_size=4, check=True)
        cls.db = connector()
        cls.specs = invitation_templates('postgresql', identity_tables=DEFAULT_TABLES)
        cls.folder = Folder('lab')
        cls.folder._setObject('lab_db', connector)
        cls.folder._setObject('acl_users', NoFallbackUsers())
        cls.folder._setObject('sql_user_provisioning', DatabaseTestController(('Member',), totp_required=True))
        cls.controller = cls.folder.sql_user_provisioning
        specs = postgresql_templates()
        for spec in list(cls.specs.values()) + list(specs.values()):
            method = SQL(spec['id'], spec['title'], 'lab_db', spec['arguments'], spec['template'])
            method.max_cache_ = 0
            method.cache_time_ = 0
            cls.folder._setObject(spec['id'], method)
        assert not cls.db.query("select tablename from pg_tables where schemaname='public'")[1]
        for key in ('setup_users', 'setup_profiles', 'setup_roles', 'setup_user_roles'):
            cls.db.query(specs[key]['template'])
        for key in ('setup', 'setup_roles'):
            cls.db.query(cls.specs[key]['template'])

    def setUp(self):
        transaction.abort()
        self.tokens = {}
        self.db.query('truncate pas_invitation_roles, pas_invitations, pas_user_roles, '
                      'pas_user_profiles, pas_roles, pas_users')

    def tearDown(self):
        transaction.abort()
        self.assertEqual(self.db.active_transaction_count(), 0)

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def invite(self, key='one', roles=('Member',)):
        try:
            result = type(self).controller.create_invitation("o'hara@example.invalid", list(roles),
                                                       {'REMOTE_ADDR': self.id()})
            self.tokens[key] = result['token']
            transaction.commit()
            return result
        except BaseException:
            transaction.abort()
            raise

    def complete(self, key='one', user='new', login=None, finish=True):
        try:
            result = type(self).controller.complete_invitation(self.tokens[key], user, login or user,
                'long-test-password', {}, {'REMOTE_ADDR': self.id()})
            if finish:
                transaction.commit()
            return result
        except BaseException:
            transaction.abort()
            raise

    def test_request_abort_after_commit_requested_rolls_back(self):
        self.invite()
        self.complete(finish=False)
        transaction.abort()
        self.assertEqual(self.count('pas_users'), 0)
        self.assertEqual(self.db.query('select accepted_at, claim_nonce from pas_invitations')[1][0], (None, None))
        self.assertTrue(self.complete())

    def count(self, table):
        return self.db.query('select count(*) from ' + table)[1][0][0]

    def test_complete_and_replay(self):
        self.invite()
        self.assertEqual(self.complete()['user_id'], 'new')
        with self.assertRaises(ValueError):
            self.complete(user='replay')
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
            try:
                return self.complete(user='user' + str(n))
            except ValueError:
                return None
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
                condition = ' when (new.accepted_at is not null)' if table == 'pas_invitations' else ''
                self.db.query('create trigger fail_test before ' + event + ' on ' + table +
                              ' for each row' + condition + ' execute function fail_invitation_test()')
                try:
                    with self.assertRaises(Exception):
                        self.complete()
                    self.assertEqual(self.db.query('select 1')[1][0][0], 1)
                    for identity_table in DEFAULT_TABLES.values():
                        self.assertEqual(self.count(identity_table), 0)
                    self.assertEqual(self.db.query('select accepted_at, result_user_id from pas_invitations')[1][0], (None, None))
                finally:
                    self.db.query('drop trigger fail_test on ' + table)
                self.assertEqual(self.complete()['user_id'], 'new')

    def test_duplicate_identity_preserves_existing_user_and_invitation(self):
        self.invite()
        self.complete()
        self.invite('two')
        for user, login in (('new', 'different'), ('different', 'new')):
            with self.assertRaises(Exception):
                self.complete('two', user, login)
            self.assertEqual(self.count('pas_users'), 1)
        self.assertEqual(self.complete('two', 'unique')['user_id'], 'unique')

    def test_invalid_roles_and_revoked_or_expired_invites(self):
        self.invite()
        self.db.query("update pas_invitation_roles set role_id='Manager'")
        with self.assertRaises(ValueError):
            self.complete()
        self.setUp()
        self.invite()
        self.db.query('update pas_invitations set expires_at=1')
        with self.assertRaises(ValueError):
            self.complete()
        self.db.query('update pas_invitations set expires_at=9999999999, revoked_at=1')
        with self.assertRaises(ValueError):
            self.complete()
        self.assertEqual(self.count('pas_users'), 0)

    def test_invitation_role_failure_rolls_back_parent(self):
        self.db.query("create or replace function fail_create_test() returns trigger "
                      "language plpgsql as $$ begin raise exception 'injected failure'; end $$")
        self.db.query('create trigger fail_create before insert on pas_invitation_roles '
                      'for each row execute function fail_create_test()')
        try:
            with self.assertRaises(ValueError):
                self.invite()
            self.assertEqual(self.count('pas_invitations'), 0)
            self.assertEqual(self.count('pas_invitation_roles'), 0)
        finally:
            self.db.query('drop trigger fail_create on pas_invitation_roles')
        self.invite()


if __name__ == '__main__':
    unittest.main(verbosity=2)
