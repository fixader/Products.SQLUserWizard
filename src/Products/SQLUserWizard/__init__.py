"""SQL user wizard Zope product."""

from AccessControl import allow_module


allow_module("AuthEncoding")
allow_module("Products.SQLUserWizard.totp")
from AccessControl import ModuleSecurityInfo
ModuleSecurityInfo("Products.SQLUserWizard.sessions").declarePublic("authenticate_session")
ModuleSecurityInfo("Products.SQLUserWizard.pas").declarePublic("enumerate_users", "roles_for_principal")


def initialize(context):
    from zope.component import provideHandler
    from zope.processlifetime import IDatabaseOpenedWithRoot
    from .upgrade import upgrade_database
    from .admin import manage_addSQLUserAdmin
    from .browser import manage_addSQLUserWizardForm
    from .browser import manage_addSQLUserAdminForm
    from .wizard import manage_addSQLUserWizard

    context.registerClass(
        meta_type="SQL User Wizard",
        constructors=(
            manage_addSQLUserWizard,
            manage_addSQLUserWizardForm,
        ),
    )
    provideHandler(upgrade_database, (IDatabaseOpenedWithRoot,))
    context.registerClass(
        meta_type="SQL User Admin",
        constructors=(
            manage_addSQLUserAdmin,
            manage_addSQLUserAdminForm,
        ),
    )
