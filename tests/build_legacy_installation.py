"""Run ONLY in a subprocess whose PYTHONPATH points at the frozen old release."""
import sys
from pathlib import Path

import transaction
from AccessControl.SecurityManagement import newSecurityManager
from AccessControl.users import UnrestrictedUser
from Testing import ZopeTestCase
from legacy_sqlite import SQLiteConnection
from Products.SQLUserWizard.installer import SQLUserWizardInstaller
from Products.SQLUserWizard.wizard import SQLUserWizard


output = Path(sys.argv[1])
for product in ("PluggableAuthService", "ZSQLMethods", "PythonScripts"):
    ZopeTestCase.installProduct(product)
app = ZopeTestCase.app()
newSecurityManager(None, UnrestrictedUser("test-manager", "", ["Manager"], []))
app.manage_addFolder("Legacy")
folder = app.Legacy
folder._setObject("test_db", SQLiteConnection())
# This is the old wizard's completed migration table mapping.
tables = dict(users="pas_users_migrated", roles="pas_roles_catalog",
              user_roles="pas_user_roles_migrated", profiles="pas_user_profiles")
SQLUserWizardInstaller(folder, "test_db", dialect="sqlite", tables=tables,
                       fallback_password="emergency-pass").install()
folder._setObject("sql_user_wizard", SQLUserWizard())
wizard = folder.sql_user_wizard
wizard.connection_id = "test_db"
wizard.dialect = "sqlite"
wizard.users_table = tables["users"]
wizard.user_roles_table = tables["user_roles"]
# roles_table deliberately remains an inherited old class default.
db = folder.test_db._v_db
db.execute("insert into pas_users_migrated (user_id, username, password, password_hash_id, enabled, totp_required, totp_enabled, totp_secret) values ('alice-id','alice','correct-password','plain',1,1,1,'JBSWY3DPEHPK3PXP')")
db.execute("insert into pas_roles_catalog (role_id, title) values ('Member','Member')")
db.execute("insert into pas_user_roles_migrated values ('alice-id','Member')")
db.execute("insert into pas_user_profiles (user_id, display_name) values ('alice-id','Alice preserved')")
output.joinpath("database.sql").write_text("\n".join(db.iterdump()), encoding="utf-8")
transaction.savepoint(optimistic=True)
folder._p_jar.exportFile(folder._p_oid, str(output / "legacy.zexp"))
transaction.abort()
ZopeTestCase.close(app)
