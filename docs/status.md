# Current Status

This document records what has been verified in the lab. It should be updated
whenever a new database, Zope version, or authentication mode is proven end to
end.

## Verified on Zope 6.1

Managed mode has been smoke-tested end to end on Zope 6.1 with separate
product-owned tables for each database:

| Database | Managed install | SQL login | Role lookup | Notes |
| --- | --- | --- | --- | --- |
| PostgreSQL | yes | yes | yes | Z SQL Method via ODBC adapter |
| PostgreSQL + TOTP | yes | yes | yes | `PAS2FALab`; optional self-service setup, enrollment-required redirect with return-to-app `came_from`, missing/wrong authenticator code rejection, valid-code login, and QR-code rendering are verified; lab issuer is `SQL_User_Wizard` |
| SQLite | yes | yes | yes | Z SQL Method via ODBC adapter |
| MariaDB/MySQL | yes | yes | yes | Z SQL Method via ODBC adapter |
| Microsoft SQL Server | yes | yes | yes | Z SQL Method via ODBC adapter |
| Oracle 11g-style SQL | yes | yes | yes | Uses `rownum = 1`, `varchar2`, and `sysdate` |

Auth-only mode has been smoke-tested against existing Zope-style PostgreSQL and
Oracle user/role tables. In auth-only mode the generated SQL is read-only.

## Verified on Zope 5.8.3

The product has been installed as a buildout `develop` egg on Zope 5.8.3 /
Python 3.8. Because that buildout path expects `setup.py`, the repository keeps
a small compatibility `setup.py` alongside `pyproject.toml`.

Managed PostgreSQL mode has been smoke-tested in a `/PASLab` folder with
separate product-owned `z5pas_*` tables:

| Database | Managed install | SQL login | Role lookup | Notes |
| --- | --- | --- | --- | --- |
| PostgreSQL | yes | yes | yes | Z SQL Method via OpenODBCDA on Zope 5.8.3 |
| PostgreSQL + TOTP | yes | yes | yes | `/PASLab`; enrollment-required redirect with return-to-app `came_from`, QR-code setup page, valid-code activation, and missing-code rejection are verified on Zope 5.8.3 |

An existing small schedule application has also been used to prove the
important migration boundary: an application may already have a user table, a
role table, and an employee/person table. The user table can be narrowed toward
identity/security, the role table can be used for PAS roles, and the
employee/person table should remain application data unless selected columns
are deliberately synced into the generated profile layer.

## Not Yet Verified

- Oracle 12c+ `fetch first 1 rows only` against a live Oracle 12c+ database.
- SQL Server through the FreeTDS adapter variant.
- A generalized, product-supported take-control/mapping workflow from
  auth-only to managed mode.

## Current Product Boundary

The product supports mainstream Zope database-adapter scenarios through Z SQL
Methods. It does not try to map arbitrary external identity schemas directly.
For unrelated legacy systems, create a managed target model first, then import
users and roles into that model with application-specific scripts.

For existing Zope applications, the wizard now includes a preflight checklist
that calls out the security/profile/application-data split before install or
repair is run against existing table names.
