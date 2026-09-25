# Frozen upgrade input

`sqluserwizard-0.1.0a2.zip` contains the unmodified `src/` tree exported by
`git archive 8944411 src` from this repository. It is test input, never an
installed dependency. Upgrade tests extract it into a temporary directory and
run its actual installer in a separate Python process, then import the exported
ZODB folder into the new version. All SQL data stays in disposable SQLite.
