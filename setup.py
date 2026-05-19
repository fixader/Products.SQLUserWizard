from setuptools import find_namespace_packages
from setuptools import setup


setup(
    name="Products.SQLUserWizard",
    version="0.1.0a1",
    description="Zope PAS SQL user wizard",
    packages=find_namespace_packages("src"),
    package_dir={"": "src"},
    include_package_data=True,
    license="MIT",
    python_requires=">=3.8",
    install_requires=[
        "Zope>=5.0",
        "Products.PluggableAuthService>=2.0",
        "Products.ZSQLMethods",
        "segno",
    ],
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Framework :: Zope",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
    ],
    zip_safe=False,
)
