"""SQL user wizard Zope product."""

from AccessControl import allow_module


allow_module("AuthEncoding")
allow_module("Products.SQLUserWizard.totp")


def initialize(context):
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
    context.registerClass(
        meta_type="SQL User Admin",
        constructors=(
            manage_addSQLUserAdmin,
            manage_addSQLUserAdminForm,
        ),
    )
