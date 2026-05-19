from setuptools import find_namespace_packages
from setuptools import setup


setup(
    name="Products.SQLUserWizard",
    version="0.1.0",
    description="Zope PAS SQL user wizard",
    packages=find_namespace_packages("src"),
    package_dir={"": "src"},
    include_package_data=True,
    install_requires=[
        "Zope>=5.0",
        "Products.PluggableAuthService>=2.0",
        "Products.ZSQLMethods",
        "segno",
    ],
    zip_safe=False,
)
