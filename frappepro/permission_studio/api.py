# Copyright (c) 2026, Agilasoft Cloud Technologies and contributors
# License: MIT. See license.txt

from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.utils import cint, cstr, get_datetime

from frappepro.permission_studio.normalize import (
	BLOCKED_DOCTYPES,
	PermissionSetupError,
	as_check,
	clamp_limit,
	clean_group_name,
	clean_text,
	like,
	prepare_members,
	prepare_rules,
)
from frappepro.permission_studio.queries import (
	coverage_rows,
	coverage_total,
	filter_options,
	list_groups,
	preview_access,
	value_labels,
)
from frappepro.permission_studio.sync import sync_group


def has_app_permission() -> bool:
	return frappe.session.user == "Administrator" or "System Manager" in set(frappe.get_roles())


@frappe.whitelist()
def get_studio(filters: str | dict | None = None) -> dict:
	_only_system_manager()
	return list_groups(_parse(filters), frappe.session.user)


@frappe.whitelist()
def get_filter_options() -> dict:
	_only_system_manager()
	return filter_options()


@frappe.whitelist()
def get_group(name: str) -> dict:
	_only_system_manager()
	document = frappe.get_doc("Permission Group", name)
	document.check_permission("read")
	return _serialize_group(document)


@frappe.whitelist()
def save_group(payload: str | dict) -> dict:
	_only_system_manager()
	data = _parse(payload)
	try:
		group_name = clean_group_name(data.get("group_name") or data.get("name"))
		members = prepare_members(data.get("members"))
		rules = prepare_rules(data.get("rules"))
	except PermissionSetupError as error:
		frappe.throw(str(error))

	name = clean_text(data.get("name"))
	if name and frappe.db.exists("Permission Group", name):
		document = frappe.get_doc("Permission Group", name)
		document.check_permission("write")
		_check_fresh(document, data.get("modified"))
		if group_name != document.name:
			frappe.rename_doc("Permission Group", document.name, group_name, force=False)
			document = frappe.get_doc("Permission Group", group_name)
	else:
		if frappe.db.exists("Permission Group", group_name):
			frappe.throw(_("A group named {0} already exists.").format(group_name))
		frappe.has_permission("Permission Group", "create", throw=True)
		document = frappe.new_doc("Permission Group")
		document.group_name = group_name

	document.group_name = group_name
	document.description = clean_text(data.get("description"))
	document.enabled = as_check(data.get("enabled", 1))
	document.set("members", [{"user": user} for user in members])
	document.set("rules", rules)
	document.save()
	return {
		"group": _serialize_group(document),
		"sync": document.flags.get("frappepro_sync_stats") or {},
	}


@frappe.whitelist()
def set_enabled(name: str, enabled: int | str = 1) -> dict:
	_only_system_manager()
	document = frappe.get_doc("Permission Group", name)
	document.check_permission("write")
	document.enabled = as_check(enabled)
	document.save()
	return {
		"group": _serialize_group(document),
		"sync": document.flags.get("frappepro_sync_stats") or {},
	}


@frappe.whitelist()
def delete_group(name: str) -> dict:
	_only_system_manager()
	document = frappe.get_doc("Permission Group", name)
	document.check_permission("delete")
	frappe.delete_doc("Permission Group", name)
	return {"deleted": name}


@frappe.whitelist()
def duplicate_group(name: str) -> dict:
	_only_system_manager()
	source = frappe.get_doc("Permission Group", name)
	source.check_permission("read")
	frappe.has_permission("Permission Group", "create", throw=True)
	copy_name = _next_copy_name(source.group_name or source.name)
	document = frappe.get_doc(
		{
			"doctype": "Permission Group",
			"group_name": copy_name,
			"description": source.description,
			"enabled": source.enabled,
			"members": [{"user": row.user} for row in source.members],
			"rules": [_rule_dict(row) for row in source.rules],
		}
	)
	document.insert()
	return {"group": _serialize_group(document), "sync": document.flags.get("frappepro_sync_stats") or {}}


@frappe.whitelist()
def resync_group(name: str) -> dict:
	_only_system_manager()
	document = frappe.get_doc("Permission Group", name)
	document.check_permission("write")
	stats = sync_group(document)
	return {"group": _serialize_group(document), "sync": stats}


@frappe.whitelist()
def preview(payload: str | dict) -> list[dict]:
	_only_system_manager()
	data = _parse(payload)
	try:
		members = prepare_members(data.get("members"))
		rules = prepare_rules(data.get("rules"))
	except PermissionSetupError as error:
		frappe.throw(str(error))
	return preview_access(
		clean_text(data.get("name")) or None,
		members,
		rules,
		as_check(data.get("enabled", 1)),
	)


@frappe.whitelist()
def get_coverage(filters: str | dict | None = None) -> dict:
	_only_system_manager()
	parsed = _parse(filters)
	limit = clamp_limit(parsed.get("limit"), default=50, maximum=200)
	offset = int(parsed.get("offset") or 0)
	if offset < 0:
		offset = 0
	return {
		"rows": coverage_rows(parsed, limit=limit, offset=offset),
		"total": coverage_total(parsed),
		"limit": limit,
		"offset": offset,
	}


@frappe.whitelist()
def search_users(
	query: str = "",
	role: str = "",
	include_disabled: int | str = 0,
	limit: int | str = 20,
) -> list[dict]:
	_only_system_manager()
	page_length = clamp_limit(limit, default=20, maximum=200)
	conditions = ["u.name NOT IN ('Guest', 'Administrator')", "u.user_type = 'System User'"]
	params: dict[str, Any] = {"limit": page_length}
	if not cint(include_disabled):
		conditions.append("u.enabled = 1")
	query = clean_text(query)
	if query:
		params["query"] = like(query)
		conditions.append(
			"(u.name LIKE %(query)s ESCAPE '\\\\' OR IFNULL(u.full_name, '') LIKE %(query)s ESCAPE '\\\\')"
		)
	join = ""
	role = clean_text(role)
	if role:
		if not frappe.db.exists("Role", role):
			frappe.throw(_("Role {0} does not exist.").format(role))
		params["role"] = role
		join = (
			"INNER JOIN `tabHas Role` hr ON hr.parent = u.name "
			"AND hr.parenttype = 'User' AND hr.role = %(role)s"
		)
	return frappe.db.sql(
		f"""
		SELECT DISTINCT u.name, u.full_name, u.user_image, u.enabled
		FROM `tabUser` u
		{join}
		WHERE {" AND ".join(conditions)}
		ORDER BY IFNULL(u.full_name, u.name), u.name
		LIMIT %(limit)s
		""",
		params,
		as_dict=True,
	)


@frappe.whitelist()
def search_roles(query: str = "", limit: int | str = 20) -> list[dict]:
	_only_system_manager()
	page_length = clamp_limit(limit, default=20, maximum=50)
	filters: dict[str, Any] = {"disabled": 0}
	query = clean_text(query)
	if query:
		filters["name"] = ["like", like(query)]
	return frappe.get_all("Role", filters=filters, fields=["name"], order_by="name asc", limit=page_length)


@frappe.whitelist()
def search_doctypes(query: str = "", limit: int | str = 20) -> list[dict]:
	_only_system_manager()
	page_length = clamp_limit(limit, default=20, maximum=50)
	filters: dict[str, Any] = {
		"istable": 0,
		"issingle": 0,
		"name": ["not in", list(BLOCKED_DOCTYPES)],
	}
	or_filters = None
	query = clean_text(query)
	if query:
		or_filters = {"name": ["like", f"%{query}%"], "module": ["like", f"%{query}%"]}
	rows = frappe.get_all(
		"DocType",
		filters=filters,
		or_filters=or_filters,
		fields=["name", "module", "is_tree"],
		order_by="name asc",
		limit=page_length,
	)
	return [{"name": row.name, "module": row.module, "is_tree": cint(row.is_tree)} for row in rows]


@frappe.whitelist()
def search_values(doctype: str, query: str = "", limit: int | str = 20) -> list[dict]:
	_only_system_manager()
	doctype = clean_text(doctype)
	if not doctype or not frappe.db.exists("DocType", doctype):
		frappe.throw(_("Choose a DocType first."))
	if doctype in BLOCKED_DOCTYPES:
		frappe.throw(_("{0} cannot be limited from Permission Studio.").format(doctype))
	meta = frappe.get_meta(doctype)
	if meta.istable or meta.issingle:
		frappe.throw(_("{0} has no records to permit.").format(doctype))

	page_length = clamp_limit(limit, default=20, maximum=50)
	title_field = meta.get_title_field() or "name"
	fields = ["name"] if title_field == "name" else ["name", title_field]
	or_filters = []
	query = clean_text(query)
	if query:
		or_filters.append([doctype, "name", "like", f"%{query}%"])
		if title_field != "name":
			or_filters.append([doctype, title_field, "like", f"%{query}%"])
	rows = frappe.get_list(
		doctype,
		or_filters=or_filters,
		fields=fields,
		limit_page_length=page_length,
		order_by="modified desc",
		ignore_user_permissions=True,
	)
	results = []
	for row in rows:
		label = row.get(title_field) if title_field != "name" else row.name
		description = "" if not label or label == row.name else label
		results.append({"value": row.name, "description": description or ""})
	return results


@frappe.whitelist()
def get_doctype_info(doctype: str) -> dict:
	_only_system_manager()
	doctype = clean_text(doctype)
	if not doctype or not frappe.db.exists("DocType", doctype):
		frappe.throw(_("DocType {0} does not exist.").format(doctype))
	meta = frappe.get_meta(doctype)
	return {
		"name": doctype,
		"is_tree": 1 if meta.get("is_tree") else 0,
		"istable": 1 if meta.istable else 0,
		"issingle": 1 if meta.issingle else 0,
		"title_field": meta.get_title_field() or "name",
	}


def _only_system_manager() -> None:
	frappe.only_for("System Manager")


def _parse(payload: str | dict | None) -> dict:
	if not payload:
		return {}
	if isinstance(payload, str):
		parsed = frappe.parse_json(payload)
	else:
		parsed = payload
	if parsed is None:
		return {}
	if not isinstance(parsed, dict):
		frappe.throw(_("Expected a JSON object."))
	return parsed


def _check_fresh(document, modified) -> None:
	if not modified:
		return
	current = document.modified
	try:
		stale = get_datetime(current) != get_datetime(modified)
	except Exception:
		stale = cstr(current) != cstr(modified)
	if stale:
		frappe.throw(
			_("{0} was saved by someone else. Reload the group and try again.").format(document.name),
			frappe.TimestampMismatchError,
		)


def _serialize_group(document) -> dict:
	rules = [_rule_dict(row) for row in document.rules]
	labels = value_labels(rules) if rules else {}
	trees = set()
	if rules:
		trees = set(
			frappe.get_all(
				"DocType",
				filters={"name": ["in", list({rule["reference_doctype"] for rule in rules})], "is_tree": 1},
				pluck="name",
			)
		)
	users = [row.user for row in document.members]
	user_rows = []
	if users:
		user_rows = frappe.get_all(
			"User",
			filters={"name": ["in", users]},
			fields=["name", "full_name", "user_image", "enabled"],
		)
	by_user = {row.name: row for row in user_rows}
	members = []
	for row in document.members:
		info = by_user.get(row.user)
		members.append(
			{
				"user": row.user,
				"full_name": (info.full_name if info else None) or row.user,
				"user_image": info.user_image if info else None,
				"enabled": cint(info.enabled) if info else 1,
			}
		)
	return {
		"name": document.name,
		"group_name": document.group_name,
		"description": document.description or "",
		"enabled": cint(document.enabled),
		"modified": document.modified,
		"owner": document.owner,
		"members": members,
		"rules": [
			{
				**rule,
				"value_label": labels.get((rule["reference_doctype"], rule["for_value"]), rule["for_value"]),
				"is_tree": 1 if rule["reference_doctype"] in trees else 0,
			}
			for rule in rules
		],
	}


def _rule_dict(row) -> dict:
	return {
		"reference_doctype": row.reference_doctype,
		"for_value": row.for_value,
		"apply_to_all_doctypes": cint(row.apply_to_all_doctypes),
		"applicable_for": row.applicable_for or "",
		"hide_descendants": cint(row.hide_descendants),
		"is_default": cint(row.is_default),
	}


def _next_copy_name(name: str) -> str:
	base = f"Copy of {name}".strip()
	candidate = base[:140]
	index = 2
	while frappe.db.exists("Permission Group", candidate):
		suffix = f" {index}"
		candidate = f"{base[: 140 - len(suffix)]}{suffix}"
		index += 1
	return candidate

