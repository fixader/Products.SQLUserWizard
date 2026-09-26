"""Validated definitions and values for application-specific profile fields."""

import json
import re
from html import escape


FIELD_TYPES = ("text", "email", "tel", "url", "textarea", "checkbox", "select")
RESERVED_FIELDS = frozenset((
    "user_id", "first_name", "last_name", "display_name", "email", "mobile",
))


def normalize_definition(field_id, label, field_type="text", required=False,
                         active=True, sort_order=100, options="", default=""):
    field_id = str(field_id or "").strip().lower()
    if not re.fullmatch(r"[a-z][a-z0-9_]{0,39}", field_id):
        raise ValueError("Field id must start with a letter and contain only lowercase letters, numbers and underscores")
    if field_id in RESERVED_FIELDS:
        raise ValueError("That field id is reserved by the built-in profile")
    label = str(label or "").strip()
    if not label or len(label) > 120:
        raise ValueError("Label is required and may contain at most 120 characters")
    field_type = str(field_type or "text").strip().lower()
    if field_type not in FIELD_TYPES:
        raise ValueError("Unsupported profile field type")
    try:
        sort_order = int(sort_order)
    except (TypeError, ValueError):
        raise ValueError("Sort order must be an integer") from None
    choices = []
    if field_type == "select":
        for line in str(options or "").splitlines():
            line = line.strip()
            if not line:
                continue
            value, separator, title = line.partition("|")
            value, title = value.strip(), (title.strip() if separator else value.strip())
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}", value):
                raise ValueError("Select values must be short identifiers")
            if not title or len(title) > 120:
                raise ValueError("Select labels may contain at most 120 characters")
            if value in {item[0] for item in choices}:
                raise ValueError("Select values must be unique")
            choices.append((value, title))
        if not choices:
            raise ValueError("Select fields need at least one value|Label option")
    default = str(default or "")
    if len(default) > 2000:
        raise ValueError("Default value is too long")
    if field_type == "select" and default and default not in {item[0] for item in choices}:
        raise ValueError("Default must be one of the select values")
    if field_type == "checkbox":
        default = "1" if default in ("1", "true", "yes", "on") else ""
    return {
        "id": field_id, "label": label, "type": field_type,
        "required": bool(required), "active": bool(active),
        "sort_order": sort_order, "options": tuple(choices), "default": default,
    }


def ordered(definitions, active_only=False):
    values = [dict(item) for item in (definitions or ())]
    if active_only:
        values = [item for item in values if item.get("active", True)]
    return sorted(values, key=lambda item: (int(item.get("sort_order", 100)), item["id"]))


def load_values(raw):
    if not raw:
        return {}
    try:
        data = json.loads(str(raw))
    except (TypeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def collect_values(definitions, request, existing=None):
    result = dict(existing or {})
    allowed = {item["id"] for item in ordered(definitions, active_only=True)}
    for definition in ordered(definitions, active_only=True):
        field_id = definition["id"]
        value = "1" if definition["type"] == "checkbox" and request.get(field_id) else str(request.get(field_id, "")).strip()
        if len(value) > 2000:
            raise ValueError(f"{definition['label']} is too long")
        if definition.get("required") and not value:
            raise ValueError(f"{definition['label']} is required")
        if definition["type"] == "select" and value and value not in {item[0] for item in definition.get("options", ())}:
            raise ValueError(f"{definition['label']} has an invalid value")
        result[field_id] = value
    # Preserve disabled definitions, discard unknown keys that were never configured.
    configured = {item["id"] for item in ordered(definitions)}
    return {key: value for key, value in result.items() if key in configured or key in allowed}


def dump_values(values):
    return json.dumps(values or {}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def render_fields(definitions, values=None):
    values = values or {}
    parts = []
    for definition in ordered(definitions, active_only=True):
        field_id = definition["id"]
        label = escape(definition["label"])
        current = str(values.get(field_id, definition.get("default", "")) or "")
        required = " required" if definition.get("required") else ""
        kind = definition["type"]
        if kind == "textarea":
            control = f'<textarea name="{field_id}"{required}>{escape(current)}</textarea>'
        elif kind == "checkbox":
            checked = " checked" if current in ("1", "true", "yes", "on") else ""
            control = f'<input name="{field_id}" type="checkbox" value="1"{checked}{required}>'
        elif kind == "select":
            options = ['<option value="">Choose…</option>']
            for value, title in definition.get("options", ()):
                selected = " selected" if current == value else ""
                options.append(f'<option value="{escape(value)}"{selected}>{escape(title)}</option>')
            control = f'<select name="{field_id}"{required}>' + "".join(options) + "</select>"
        else:
            control = f'<input name="{field_id}" type="{kind}" value="{escape(current)}"{required}>'
        parts.append(f'<label class="form-field"><span>{label}</span>{control}</label>')
    if not parts:
        return ""
    return '<fieldset class="profile-extra-fields"><legend>Additional profile information</legend>' + "".join(parts) + "</fieldset>"
