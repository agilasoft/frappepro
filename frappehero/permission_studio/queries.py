# Copyright (c) 2026, Agilasoft Cloud Technologies and contributors
# License: MIT. See license.txt

from __future__ import annotations

import frappe
from frappe.utils import cint, cstr

from frappehero.permission_studio.normalize import (
	build_coverage_where,
	build_group_where,
	clamp_limit,
	clamp_offset,
	group_order_by,
)


def list_groups(filters: dict | None, session_user: str) -> dict:
	filters = filters or {}
	where, params = build_group_where(filters, session_user)
	limit = clamp_limit(filters.get("limit"), default=24, maximum=200)
	offset = clamp_offset(filters.get("offset"))
	order_by = group_order_by(filters.get("sort"))

	total = frappe.db.sql(
		f"SELECT COUNT(*) FROM `tabPermission Group` pg WHERE {where}",
		params,
	)[0][0]
	summary = _summary(where, params)

	params = dict(params)
	params.update({"limit": limit, "offset": offset})
	name_rows = frappe.db.sql(
		f"""
		SELECT pg.name
		FROM `tabPermission Group` pg
		WHERE {where}
		ORDER BY {order_by}
		LIMIT %(limit)s OFFSET %(offset)s
		""",
		params,
		as_dict=True,
	)
	names = [row.name for row in name_rows]

	if not names:
		return {"groups": [], "total": total, "summary": summary, "limit": limit, "offset": offset}

	group_rows = frappe.get_all(
		"Permission Group",
		filters={"name": ["in", names]},
		fields=["name", "group_name", "description", "enabled", "modified", "owner"],
	)
	by_name = {row.name: row for row in group_rows}
	members = frappe.db.sql(
		"""
		SELECT m.parent, m.user, u.full_name, u.user_image, u.enabled
		FROM `tabPermission Group Member` m
		LEFT JOIN `tabUser` u ON u.name = m.user
		WHERE m.parent IN %(names)s
		ORDER BY IFNULL(u.full_name, m.user)
		""",
		{"names": names},
		as_dict=True,
	)
	rules = frappe.db.sql(
		"""
		SELECT parent, reference_doctype, for_value
		FROM `tabPermission Group Rule`
		WHERE parent IN %(names)s
		ORDER BY reference_doctype, for_value
		""",
		{"names": names},
		as_dict=True,
	)

	members_by_group: dict[str, list] = {name: [] for name in names}
	for row in members:
		members_by_group.setdefault(row.parent, []).append(row)
	rules_by_group: dict[str, list] = {name: [] for name in names}
	for row in rules:
		rules_by_group.setdefault(row.parent, []).append(row)

	groups = []
	for name in names:
		row = by_name.get(name)
		if not row:
			continue
		group_members = members_by_group.get(name, [])
		group_rules = rules_by_group.get(name, [])
		groups.append(
			{
				"name": row.name,
				"group_name": row.group_name,
				"description": row.description or "",
				"enabled": cint(row.enabled),
				"modified": row.modified,
				"owner": row.owner,
				"member_count": len(group_members),
				"rule_count": len(group_rules),
				"members": [
					{
						"user": member.user,
						"full_name": member.full_name or member.user,
						"user_image": member.user_image,
						"enabled": cint(member.enabled) if member.enabled is not None else 1,
					}
					for member in group_members[:8]
				],
				"doctypes": _doctype_counts(group_rules),
			}
		)

	return {"groups": groups, "total": total, "summary": summary, "limit": limit, "offset": offset}


def _summary(where: str, params: dict) -> dict:
	group_count = frappe.db.sql(
		f"SELECT COUNT(*) FROM `tabPermission Group` pg WHERE {where}",
		params,
	)[0][0]
	user_count = frappe.db.sql(
		f"""
		SELECT COUNT(DISTINCT m.user)
		FROM `tabPermission Group Member` m
		INNER JOIN `tabPermission Group` pg ON pg.name = m.parent
		WHERE {where}
		""",
		params,
	)[0][0]
	rule_count = frappe.db.sql(
		f"""
		SELECT COUNT(*)
		FROM `tabPermission Group Rule` r
		INNER JOIN `tabPermission Group` pg ON pg.name = r.parent
		WHERE {where}
		""",
		params,
	)[0][0]
	return {"groups": group_count, "users": user_count, "rules": rule_count}


def _doctype_counts(rules: list) -> list[dict]:
	counts: dict[str, int] = {}
	for rule in rules:
		counts[rule.reference_doctype] = counts.get(rule.reference_doctype, 0) + 1
	return [{"doctype": doctype, "count": count} for doctype, count in counts.items()]


def coverage_rows(filters: dict | None, limit: int = 50, offset: int = 0) -> list[dict]:
	where, params = build_coverage_where(filters)
	params = dict(params)
	params.update({"limit": limit, "offset": offset})
	rows = frappe.db.sql(
		f"""
		SELECT
			m.user,
			IFNULL(u.full_name, m.user) AS full_name,
			u.user_image,
			pg.name AS permission_group,
			pg.group_name,
			pg.enabled,
			r.reference_doctype,
			r.for_value,
			IFNULL(r.applicable_for, '') AS applicable_for,
			IFNULL(r.apply_to_all_doctypes, 1) AS apply_to_all_doctypes,
			IFNULL(r.hide_descendants, 0) AS hide_descendants,
			IFNULL(r.is_default, 0) AS is_default
		FROM `tabPermission Group Rule` r
		INNER JOIN `tabPermission Group` pg ON pg.name = r.parent
		INNER JOIN `tabPermission Group Member` m ON m.parent = pg.name
		LEFT JOIN `tabUser` u ON u.name = m.user
		WHERE {where}
		ORDER BY full_name, pg.group_name, r.reference_doctype, r.for_value
		LIMIT %(limit)s OFFSET %(offset)s
		""",
		params,
		as_dict=True,
	)
	for row in rows:
		row["enabled"] = cint(row.enabled)
		row["apply_to_all_doctypes"] = cint(row.apply_to_all_doctypes)
		row["hide_descendants"] = cint(row.hide_descendants)
		row["is_default"] = cint(row.is_default)
		row["status"] = "Active" if row.enabled else "Disabled"
		row["applies_to"] = "All document types" if row.apply_to_all_doctypes else row.applicable_for
	return rows


def coverage_total(filters: dict | None) -> int:
	where, params = build_coverage_where(filters)
	return frappe.db.sql(
		f"""
		SELECT COUNT(*)
		FROM `tabPermission Group Rule` r
		INNER JOIN `tabPermission Group` pg ON pg.name = r.parent
		INNER JOIN `tabPermission Group Member` m ON m.parent = pg.name
		LEFT JOIN `tabUser` u ON u.name = m.user
		WHERE {where}
		""",
		params,
	)[0][0]


def filter_options() -> dict:
	groups = frappe.get_all(
		"Permission Group",
		fields=["name", "group_name", "enabled"],
		order_by="group_name asc",
		limit=300,
	)
	users = frappe.db.sql(
		"""
		SELECT DISTINCT m.user, IFNULL(u.full_name, m.user) AS full_name
		FROM `tabPermission Group Member` m
		LEFT JOIN `tabUser` u ON u.name = m.user
		ORDER BY full_name
		LIMIT 300
		""",
		as_dict=True,
	)
	doctypes = frappe.db.sql(
		"""
		SELECT DISTINCT reference_doctype
		FROM `tabPermission Group Rule`
		ORDER BY reference_doctype
		LIMIT 300
		""",
		pluck=True,
	)
	return {"groups": groups, "users": users, "doctypes": doctypes}


def value_labels(rules: list[dict]) -> dict[tuple[str, str], str]:
	by_doctype: dict[str, set[str]] = {}
	for rule in rules:
		by_doctype.setdefault(rule["reference_doctype"], set()).add(rule["for_value"])

	labels: dict[tuple[str, str], str] = {}
	for doctype, names in by_doctype.items():
		meta = frappe.get_meta(doctype)
		title_field = meta.get_title_field() or "name"
		if title_field == "name":
			for name in names:
				labels[(doctype, name)] = name
			continue
		rows = frappe.get_all(
			doctype,
			filters={"name": ["in", list(names)]},
			fields=["name", title_field],
		)
		found = {row.name: row.get(title_field) or row.name for row in rows}
		for name in names:
			labels[(doctype, name)] = found.get(name) or name
	return labels


def preview_access(group_name: str | None, members: list[str], rules: list[dict], enabled: int) -> list[dict]:
	"""Effective limits if this draft is saved, combined with other enabled groups."""
	if not members:
		return []

	user_rows = frappe.get_all(
		"User",
		filters={"name": ["in", members]},
		fields=["name", "full_name", "user_image"],
	)
	users = {row.name: row for row in user_rows}

	sources: dict[str, dict[tuple, set[str]]] = {user: {} for user in members}
	if cint(enabled):
		for user in members:
			for rule in rules:
				_add_source(sources, user, rule["reference_doctype"], rule["for_value"], "This group")

	other = frappe.db.sql(
		"""
		SELECT m.user, pg.group_name, r.reference_doctype, r.for_value
		FROM `tabPermission Group Rule` r
		INNER JOIN `tabPermission Group` pg ON pg.name = r.parent
		INNER JOIN `tabPermission Group Member` m ON m.parent = pg.name
		WHERE pg.enabled = 1
		AND m.user IN %(users)s
		AND (%(group_name)s = '' OR pg.name != %(group_name)s)
		""",
		{"users": members, "group_name": group_name or ""},
		as_dict=True,
	)
	for row in other:
		_add_source(sources, row.user, row.reference_doctype, row.for_value, row.group_name)

	preview = []
	for user in members:
		info = users.get(user)
		buckets: dict[str, list] = {}
		for (doctype, value), names in sorted(sources.get(user, {}).items()):
			buckets.setdefault(doctype, []).append(
				{"value": value, "sources": sorted(names, key=lambda item: (item != "This group", item))}
			)
		preview.append(
			{
				"user": user,
				"full_name": (info.full_name if info else None) or user,
				"user_image": info.user_image if info else None,
				"doctypes": [
					{"doctype": doctype, "values": values} for doctype, values in buckets.items()
				],
			}
		)
	return preview


def _add_source(sources, user, doctype, value, source) -> None:
	if user not in sources:
		sources[user] = {}
	key = (cstr(doctype), cstr(value))
	sources[user].setdefault(key, set()).add(source)
