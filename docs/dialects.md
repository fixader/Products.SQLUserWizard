# SQL Dialects

The product treats Z SQL Methods as its database contract. The concrete
database adapter may be OpenODBCDA, a SQLAlchemy wrapper, psycopg, an Oracle
adapter, or another Zope database adapter, as long as Z SQL Methods can execute
the generated SQL.

## Managed dialects

Managed mode currently has template support for the mainstream databases used
in the lab scope:

- PostgreSQL
- SQLite
- MySQL / MariaDB
- Microsoft SQL Server
- Oracle 11g
- Oracle 12c and newer

The supported SQL surface is intentionally small:

- create the four product-owned tables
- fetch one user by login
- fetch one user/profile by user id
- fetch roles for a user
- list users and roles
- insert or update users, roles, and profile rows
- assign and clear roles
- delete profile and user rows

The product does not try to abstract arbitrary application data. Fields such as
avatar images, rich profile models, documents, BLOBs, CLOBs, and domain tables
are application concerns.

## Important dialect differences

Single-row fetch:

- PostgreSQL, SQLite, MySQL, and MariaDB use `limit 1`.
- Microsoft SQL Server uses `top 1`.
- Oracle 11g uses `rownum = 1`.
- Oracle 12c and newer use `fetch first 1 rows only`.

Upsert:

- PostgreSQL and SQLite use `on conflict`.
- MySQL and MariaDB use `on duplicate key update`.
- Microsoft SQL Server uses `merge`.
- Oracle uses `merge into ... using (select ... from dual)`.

Boolean/enabled fields:

- PostgreSQL uses `boolean`.
- MySQL and MariaDB use `tinyint(1)`.
- SQL Server uses `bit`.
- SQLite uses `integer`.
- Oracle uses `number(1)`.

Schema repair:

PostgreSQL currently has explicit `alter table ... add column if not exists`
repair for security columns. Other dialects create the full table shape for new
managed installations and run a harmless schema-repair no-op. Broader
cross-database schema migration should be explicit and tested before it is made
automatic.

## Installation boundary

Every dialect creates the same product-owned model. Table names must be distinct
simple identifiers (letters, digits, underscores; start with a letter; maximum
30 characters). Schema-qualified names are not supported: configure the adapter's
default schema instead. New installations check the database catalog and reject
name collisions before changing PAS or SQL objects. Repair requires the existing
managed manifest and the same connection id, dialect and table mapping.

There is no existing-user-database mode or data migration generator. Import old
data separately into the new model if needed.
