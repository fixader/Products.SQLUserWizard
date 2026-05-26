from Products.SQLUserWizard.installer import SQLUserWizardInstaller


def test_installer_rebinds_existing_pas_as_local_user_folder():
    class FakePas:
        meta_type = "Pluggable Auth Service"

        def manage_afterAdd(self, item, container):
            container.__allow_groups__ = self

    class FakeFolder:
        def __init__(self):
            self.acl_users = FakePas()

        def objectIds(self):
            return ["acl_users"]

        def absolute_url_path(self):
            return "/App"

    folder = FakeFolder()
    installer = SQLUserWizardInstaller(folder, "db")

    pas = installer._ensure_pas()

    assert pas is folder.acl_users
    assert folder.__allow_groups__ is pas
    assert "Bound acl_users as local user folder" in installer.result.actions
