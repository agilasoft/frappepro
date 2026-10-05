# Copyright (c) 2026, Agilasoft Cloud Technologies and contributors
# License: MIT. See license.txt

"""Pure helpers for permission groups.

Nothing in this module imports Frappe, so the rules can be unit tested
without a site.
"""

from __future__ import annotations

BLOCKED_USERS = frozenset({"Guest", "Administrator"})

# Restricting these would let a group hide the tools that edit the group.
BLOCKED_DOCTYPES = frozenset(
	{
		"Permission Group",
		"Permission Group Member",
		"Permission Group Rule",
		"Permission Group Grant",
		"User Permission",
		"DocPerm",
		"Custom DocPerm",
		"Has Role",
	}
)

GROUP_SORTS = {
	"modified": "pg.modified DESC",
	"name": "pg.group_name ASC",
	"members": (
		"(SELECT COUNT(*) FROM `tabPermission Group Member` m WHERE m.parent = pg.name) DESC, "
		"pg.group_name ASC"
	),
	"rules": (
		"(SELECT COUNT(*) FROM `tabPermission Group Rule` r WHERE r.parent = pg.name) DESC, "
		"pg.group_name ASC"
	),
}


class PermissionSetupError(ValueError):
	"""A group definition that cannot be applied."""


def as_check(value) -> int:
	return 1 if value in (1, True, "1", "true", "True") else 0


def clean_text(value) -> str:
	if value is None:
		return ""
	return str(value).strip()


def like(value: str) -> str:
	"""Escape a fragment for a SQL LIKE ... ESCAPE '\\' predicate."""
	escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
	return f"%{escaped}%"


def clean_group_name(name: str) -> str:
	cleaned = clean_text(name)
	if not cleaned:
		raise PermissionSetupError("Enter a group name.")
	if len(cleaned) > 140:
		raise PermissionSetupError("Group name must be 140 characters or fewer.")
	return cleaned


def prepare_members(members) -> list[str]:
	"""Return a de-duplicated user list, preserving order."""
	seen = set()
	prepared = []
	for row in members or []:
		if isinstance(row, str):
			user = clean_text(row)
		else:
			user = clean_text((row or {}).get("user"))
		if not user or user in seen:
			continue
		if user in BLOCKED_USERS:
			raise PermissionSetupError(
				f"{user} is not affected by user permissions, so they cannot be added to a group."
			)
		seen.add(user)
		prepared.append(user)
	return prepared


def prepare_rules(rules, tree_doctypes: set[str] | None = None) -> list[dict]:
	"""Normalize rule rows and reject combinations Frappe cannot store."""
	tree_doctypes = tree_doctypes or set()
	prepared = []
	seen = set()
	default_doctypes = set()

	for index, raw in enumerate(rules or [], start=1):
		raw = raw or {}
		reference_doctype = clean_text(raw.get("reference_doctype"))
		for_value = clean_text(raw.get("for_value"))
		apply_all = as_check(raw.get("apply_to_all_doctypes", 1))
		applicable_for = "" if apply_all else clean_text(raw.get("applicable_for"))
		hide_descendants = as_check(raw.get("hide_descendants"))
		is_default = as_check(raw.get("is_default"))

		if not reference_doctype or not for_value:
			raise PermissionSetupError(f"Row {index} needs both a DocType and a value.")
		if reference_doctype in BLOCKED_DOCTYPES:
			raise PermissionSetupError(f"{reference_doctype} cannot be limited from Permission Studio.")
		if not apply_all and not applicable_for:
			raise PermissionSetupError(
				f"Row {index} ({reference_doctype} = {for_value}) needs Applicable For, "
				"or turn Apply To All Document Types back on."
			)
		if applicable_for in BLOCKED_DOCTYPES:
			raise PermissionSetupError(f"{applicable_for} cannot be used as Applicable For.")
		if reference_doctype not in tree_doctypes:
			hide_descendants = 0

		identity = (reference_doctype, for_value, applicable_for, apply_all)
		if identity in seen:
			where = "everywhere" if apply_all else f"on {applicable_for}"
			raise PermissionSetupError(f"{reference_doctype} = {for_value} is already allowed {where}.")
		seen.add(identity)

		if is_default:
			if reference_doctype in default_doctypes:
				raise PermissionSetupError(
					f"Only one default value is allowed for {reference_doctype} in a group."
				)
			default_doctypes.add(reference_doctype)

		prepared.append(
			{
				"reference_doctype": reference_doctype,
				"for_value": for_value,
				"apply_to_all_doctypes": apply_all,
				"applicable_for": applicable_for,
				"hide_descendants": hide_descendants,
				"is_default": is_default,
			}
		)
	return prepared


def rule_key(user: str, rule: dict) -> tuple:
	return (
		user,
		rule["reference_doctype"],
		rule["for_value"],
		rule["applicable_for"],
		int(rule["apply_to_all_doctypes"]),
	)


def desired_grants(members: list[str], rules: list[dict], enabled: int) -> dict[tuple, dict]:
	if not as_check(enabled):
		return {}
	desired = {}
	for user in members:
		for rule in rules:
			desired[rule_key(user, rule)] = rule
	return desired


def build_group_where(filters: dict | None, session_user: str) -> tuple[str, dict]:
	"""WHERE clause for `tabPermission Group` aliased as `pg`."""
	filters = filters or {}
	clauses = ["1=1"]
	params: dict = {}

	search = clean_text(filters.get("search"))
	if search:
		params["search"] = like(search)
		clauses.append(
			"""(
				pg.group_name LIKE %(search)s ESCAPE '\\\\'
				OR IFNULL(pg.description, '') LIKE %(search)s ESCAPE '\\\\'
				OR EXISTS (
					SELECT 1 FROM `tabPermission Group Rule` r_search
					WHERE r_search.parent = pg.name
					AND r_search.for_value LIKE %(search)s ESCAPE '\\\\'
				)
				OR EXISTS (
					SELECT 1 FROM `tabPermission Group Member` m_search
					LEFT JOIN `tabUser` u_search ON u_search.name = m_search.user
					WHERE m_search.parent = pg.name
					AND (
						m_search.user LIKE %(search)s ESCAPE '\\\\'
						OR IFNULL(u_search.full_name, '') LIKE %(search)s ESCAPE '\\\\'
					)
				)
			)"""
		)

	status = clean_text(filters.get("status")) or "all"
	if status == "active":
		clauses.append("pg.enabled = 1")
	elif status == "disabled":
		clauses.append("pg.enabled = 0")

	user = clean_text(filters.get("user"))
	if user:
		params["filter_user"] = user
		clauses.append(
			"""EXISTS (
				SELECT 1 FROM `tabPermission Group Member` m_user
				WHERE m_user.parent = pg.name AND m_user.user = %(filter_user)s
			)"""
		)

	reference_doctype = clean_text(filters.get("reference_doctype"))
	if reference_doctype:
		params["filter_doctype"] = reference_doctype
		clauses.append(
			"""EXISTS (
				SELECT 1 FROM `tabPermission Group Rule` r_dt
				WHERE r_dt.parent = pg.name AND r_dt.reference_doctype = %(filter_doctype)s
			)"""
		)

	value = clean_text(filters.get("value"))
	if value:
		params["filter_value"] = like(value)
		clauses.append(
			"""EXISTS (
				SELECT 1 FROM `tabPermission Group Rule` r_val
				WHERE r_val.parent = pg.name
				AND r_val.for_value LIKE %(filter_value)s ESCAPE '\\\\'
			)"""
		)

	preset = clean_text(filters.get("preset")) or "all"
	if preset == "mine":
		params["owner"] = session_user
		clauses.append("pg.owner = %(owner)s")
	elif preset == "empty":
		clauses.append(
			"""(
				NOT EXISTS (
					SELECT 1 FROM `tabPermission Group Member` m_empty WHERE m_empty.parent = pg.name
				)
				OR NOT EXISTS (
					SELECT 1 FROM `tabPermission Group Rule` r_empty WHERE r_empty.parent = pg.name
				)
			)"""
		)
	elif preset == "inactive":
		clauses.append("pg.enabled = 0")

	return " AND ".join(clauses), params


def group_order_by(sort: str | None) -> str:
	return GROUP_SORTS.get(clean_text(sort) or "modified", GROUP_SORTS["modified"])


def build_coverage_where(filters: dict | None) -> tuple[str, dict]:
	"""WHERE clause for coverage rows aliased as pg, m, r, and u."""
	filters = filters or {}
	clauses = ["1=1"]
	params: dict = {}

	if as_check(filters.get("enabled_only", 1)):
		clauses.append("pg.enabled = 1")
	if as_check(filters.get("defaults_only")):
		clauses.append("r.is_default = 1")
	if as_check(filters.get("narrowed_only")):
		clauses.append("IFNULL(r.apply_to_all_doctypes, 0) = 0")

	user = clean_text(filters.get("user"))
	if user:
		params["user"] = user
		clauses.append("m.user = %(user)s")

	group = clean_text(filters.get("permission_group"))
	if group:
		params["permission_group"] = group
		clauses.append("pg.name = %(permission_group)s")

	reference_doctype = clean_text(filters.get("reference_doctype"))
	if reference_doctype:
		params["reference_doctype"] = reference_doctype
		clauses.append("r.reference_doctype = %(reference_doctype)s")

	query = clean_text(filters.get("query"))
	if query:
		params["query"] = like(query)
		clauses.append(
			"""(
				m.user LIKE %(query)s ESCAPE '\\\\'
				OR IFNULL(u.full_name, '') LIKE %(query)s ESCAPE '\\\\'
				OR pg.group_name LIKE %(query)s ESCAPE '\\\\'
				OR r.reference_doctype LIKE %(query)s ESCAPE '\\\\'
				OR r.for_value LIKE %(query)s ESCAPE '\\\\'
				OR IFNULL(r.applicable_for, '') LIKE %(query)s ESCAPE '\\\\'
			)"""
		)

	return " AND ".join(clauses), params


def clamp_limit(value, default: int = 60, maximum: int = 200) -> int:
	try:
		number = int(value)
	except (TypeError, ValueError):
		number = default
	return max(1, min(number, maximum))


def clamp_offset(value) -> int:
	try:
		number = int(value)
	except (TypeError, ValueError):
		number = 0
	return max(0, number)
