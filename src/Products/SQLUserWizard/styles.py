"""Static stylesheet installed in each managed application folder."""

STYLESHEET_ID = "sql_wizard.css"

STYLESHEET = """/* Products.SQLUserWizard static application stylesheet. */
:root { --sqluw-page:#f6f8fb; --sqluw-surface:#fff; --sqluw-border:#c8ced8; --sqluw-muted:#667085; --sqluw-primary:#1d5f9f; }
* { box-sizing:border-box; }
body.sqluw-page { margin:0; padding:2rem clamp(1rem,3vw,2.5rem); color:#172033; background:var(--sqluw-page); font-family:system-ui,sans-serif; line-height:1.45; }
.sqluw-editor-shell { max-width:1100px; margin:0 auto; }
.panel, .sqluw-form-card { min-width:0; margin:0 0 1.25rem; padding:1.1rem; border:1px solid var(--sqluw-border); border-radius:.5rem; background:var(--sqluw-surface); box-shadow:0 1px 2px rgba(23,32,51,.06); }
.profile-editor-link { margin:.15rem 0 .55rem; text-align:right; }
.muted { color:var(--sqluw-muted); }
.form-field { display:grid; grid-template-columns:10.5rem minmax(0,1fr); gap:.75rem; align-items:center; margin:.65rem 0; font-weight:600; }
.form-field input, .form-field select, .form-field textarea { width:100%; min-width:0; padding:.5rem .6rem; border:1px solid #aeb8c6; border-radius:.3rem; background:#fff; color:#172033; font:inherit; }
.form-field textarea { resize:vertical; }
.form-field input:focus, .form-field select:focus, .form-field textarea:focus { border-color:#3979b7; outline:2px solid #cfe3f6; outline-offset:1px; }
.check-row { display:flex; gap:.55rem; align-items:flex-start; margin:.65rem 0; font-weight:500; }
.check-row input { width:auto; margin-top:.18rem; }
.form-actions { display:flex; flex-wrap:wrap; gap:.7rem; align-items:center; padding-top:1rem; }
button, .button { display:inline-block; padding:.55rem .9rem; border:1px solid #8f9baa; border-radius:.35rem; background:#fff; color:#172033; cursor:pointer; font:inherit; font-weight:600; text-decoration:none; }
button:hover, .button:hover { background:#f1f4f8; }
.form-actions button:first-child { color:#fff; border-color:var(--sqluw-primary); background:var(--sqluw-primary); }
.danger { color:#8a1f11; border-color:#d6a29a; }
fieldset { min-width:0; margin:0 0 1rem; padding:1rem; border:1px solid var(--sqluw-border); border-radius:.45rem; background:#fff; }
legend { padding:0 .35rem; font-weight:700; }
.table-scroll { max-width:100%; overflow:auto; border:1px solid #e1e5eb; border-radius:.35rem; }
table { width:100%; border-collapse:collapse; }
th, td { padding:.55rem .6rem; border-bottom:1px solid #d6dbe3; text-align:left; vertical-align:top; }
th { background:#f1f4f8; font-size:.84rem; }
.ok { padding:.7rem; border-left:4px solid #17803a; background:#eef8f0; }
.error { padding:.7rem; border-left:4px solid #b42318; background:#fff1f0; }
@media (max-width:620px) { body.sqluw-page { padding:1rem; } .form-field { grid-template-columns:1fr; gap:.25rem; } }
"""
