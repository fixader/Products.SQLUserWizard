"""Trusted PAS adapters; SQL methods themselves are not browser endpoints."""


def enumerate_users(plugin, id=None, login=None, exact_match=False, sort_by=None, max_results=None):
    def values(value):
        return list(value) if isinstance(value, (tuple, list)) else [value] if value else []

    ids, logins = values(id), values(login)
    try:
        if exact_match and (ids or logins):
            rows = [row for value in ids for row in plugin.zsql_pas_get_user(user_id=value)]
            rows += [row for value in logins for row in plugin.zsql_pas_fetch_user(login=value)]
        else:
            rows = plugin.zsql_pas_list_users()
    except Exception:
        return ()
    result = {}
    for row in rows:
        info = dict(id=str(row.user_id), login=str(row.login_name),
                    title=str(getattr(row, "display_name", "") or row.login_name))
        if exact_match and (ids or logins) and info["id"] not in ids and info["login"] not in logins:
            continue
        if not exact_match and ids + logins:
            if not any(str(term).lower() in " ".join(info.values()).lower() for term in ids + logins):
                continue
        result[info["id"]] = info
    rows = list(result.values())
    if sort_by:
        rows.sort(key=lambda row: row.get(sort_by, ""))
    if max_results:
        rows = rows[:int(max_results)]
    return tuple(rows)


def roles_for_principal(plugin, principal):
    try:
        return tuple(row.role for row in plugin.zsql_pas_fetch_roles(user_id=principal.getId()))
    except Exception:
        return ()
