def manage_addSQLUserWizardForm(self, REQUEST=None):
    return """<html>
<head>
  <title>Add SQL User Wizard</title>
</head>
<body>
<h2>Add SQL User Wizard</h2>
<form action="manage_addSQLUserWizard" method="post">
  <div>
    <label>Id
      <input name="id" value="sql_user_wizard">
    </label>
  </div>
  <div>
    <label>Title
      <input name="title" value="SQL User Wizard">
    </label>
  </div>
  <input type="submit" value="Add">
</form>
</body>
</html>"""


def manage_addSQLUserAdminForm(self, REQUEST=None):
    return """<html>
<head>
  <title>Add SQL User Admin</title>
</head>
<body>
<h2>Add SQL User Admin</h2>
<form action="manage_addSQLUserAdmin" method="post">
  <div>
    <label>Id
      <input name="id" value="sql_user_admin">
    </label>
  </div>
  <div>
    <label>Title
      <input name="title" value="SQL User Admin">
    </label>
  </div>
  <input type="submit" value="Add">
</form>
</body>
</html>"""
