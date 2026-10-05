# Copyright (c) 2026, Agilasoft Cloud Technologies and contributors
# License: MIT. See license.txt

"""Keep Frappe User Permissions in step with a Permission Group.

User Permissions are restrictive: a row for Company = Acme means that user
sees Acme only, for that DocType. Disabling or deleting a group deletes the
rows this app created, which lifts those limits. Rows that already existed
before the group (adopted) are left in place.
"""

from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.utils import cint, cstr

from frappehero.permission_studio.normalize import (
	PermissionSetupError,
	as_check,
	clean_group_name,
	clean_text,
	desired_grants,
	prepare_members,
	prepare_rules,
)


def validate_group(group) -> None:
	"""Normalize members and rules onto the document before it is written."""
	try:
		members = prepare_members(_child_dicts(group, "members"))
		raw_rules = _child_dicts(group, "rules")
		rules = prepare_rules(raw_rules, _tree_doctypes(raw_rules))
		group.group_name = clean_group_name(group.group_name)
	except PermissionSetupError as error:
		frappe.throw(str(error))

	_assert_documents_exist(members, rules)
	group.enabled = cint(as_check(group.enabled))
	group.description = clean_text(group.description)
	group.set("members", [{"user": user} for user in members])
	group.set("rules", rules)


def sync_group(group) -> dict[str, int]:
	"""Create, update, and retire User Permissions for one group.

	Called after the group document has been saved, and safe to call again.
	"""
	_require_tracking_fields()
	try:
		members = prepare_members(_child_dicts(group, "members"))
		raw_rules = _child_dicts(group, "rules")
		rules = prepare_rules(raw_rules, _tree_doctypes(raw_rules))
	except PermissionSetupError as error:
		frappe.throw(str(error))
	_assert_documents_exist(members, rules)

	desired = desired_grants(members, rules, cint(group.enabled))
	existing = _existing_grants(group.name)
	removed = 0

	for key, row in existing.items():
		if key not in desired:
			_delete_grant(row.name)
			removed += 1

	for key, rule in desired.items():
		user, reference_doctype, for_value, applicable_for, apply_all = key
		up_name, adopted = _ensure_user_permission(
			group.name,
			user,
			rule,
		)
		current = existing.get(key)
		values = {
			"user_permission": up_name,
			"adopted": adopted,
			"is_default": rule["is_default"],
			"hide_descendants": rule["hide_descendants"],
			"apply_to_all_doctypes": apply_all,
			"applicable_for": applicable_for,
		}
		if current:
			frappe.db.set_value("Permission Group Grant", current.name, values, update_modified=False)
		else:
			frappe.get_doc(
				{
					"doctype": "Permission Group Grant",
					"permission_group": group.name,
					"user": user,
					"reference_doctype": reference_doctype,
					"for_value": for_value,
					**values,
				}
			).insert(ignore_permissions=True)

	stats = {"applied": len(desired), "removed": removed}
	group.flags.frappehero_sync_stats = stats
	return stats


def clear_group(group_name: str) -> int:
	"""Drop every grant for a group and the User Permissions only this app owns."""
	if not frappe.db.table_exists("Permission Group Grant"):
		return 0
	names = frappe.get_all(
		"Permission Group Grant",
		filters={"permission_group": group_name},
		pluck="name",
	)
	for name in names:
		_delete_grant(name)
	return len(names)


def release_user_permission(user_permission: str | None, group: str | None, adopted: int) -> None:
	"""After a grant row is gone, delete or keep the User Permission it pointed at."""
	if not user_permission or not frappe.db.exists("User Permission", user_permission):
		return

	remaining = frappe.db.get_value(
		"Permission Group Grant",
		{"user_permission": user_permission},
		"permission_group",
	)
	managed = cint(frappe.db.get_value("User Permission", user_permission, "frappehero_managed"))

	if remaining:
		if managed:
			frappe.db.set_value(
				"User Permission",
				user_permission,
				"frappehero_group",
				remaining,
				update_modified=False,
			)
		return

	if managed and not cint(adopted):
		frappe.delete_doc("User Permission", user_permission, ignore_permissions=True)
		return

	current = frappe.db.get_value("User Permission", user_permission, "frappehero_group")
	if current and current == group:
		frappe.db.set_value(
			"User Permission",
			user_permission,
			"frappehero_group",
			None,
			update_modified=False,
		)


def _require_tracking_fields() -> None:
	if frappe.db.has_column("User Permission", "frappehero_managed"):
		return
	frappe.throw(
		_(
			"Frappe Hero has not finished installing its User Permission fields. "
			"Run bench migrate on this site, then try again."
		)
	)


def _child_dicts(group, fieldname: str) -> list[dict]:
	rows = []
	for child in group.get(fieldname) or []:
		if hasattr(child, "as_dict"):
			rows.append(child.as_dict())
		else:
			rows.append(dict(child))
	return rows


def _tree_doctypes(rules: list[dict]) -> set[str]:
	names = {cstr(rule.get("reference_doctype")) for rule in rules if rule.get("reference_doctype")}
	if not names:
		return set()
	rows = frappe.get_all("DocType", filters={"name": ["in", list(names)], "is_tree": 1}, pluck="name")
	return set(rows)


def _assert_documents_exist(members: list[str], rules: list[dict]) -> None:
	for user in members:
		if not frappe.db.exists("User", user):
			frappe.throw(_("User {0} does not exist.").format(user))
		user_type = frappe.db.get_value("User", user, "user_type")
		if user_type and user_type != "System User":
			frappe.throw(_("{0} is a {1}. Permission groups only include System Users.").format(user, user_type))

	seen_doctypes: set[str] = set()
	for rule in rules:
		doctype = rule["reference_doctype"]
		if doctype not in seen_doctypes:
			_assert_linkable_doctype(doctype)
			seen_doctypes.add(doctype)
		applicable = rule["applicable_for"]
		if applicable and applicable not in seen_doctypes:
			_assert_linkable_doctype(applicable)
			seen_doctypes.add(applicable)
		if not frappe.db.exists(doctype, rule["for_value"]):
			frappe.throw(
				_("{0} {1} does not exist.").format(doctype, rule["for_value"]),
				frappe.DoesNotExistError,
			)


def _assert_linkable_doctype(doctype: str) -> None:
	meta = frappe.get_meta(doctype)
	if meta.istable or meta.issingle:
		frappe.throw(_("{0} cannot be used in a permission group.").format(doctype))


def _existing_grants(group_name: str) -> dict[tuple, Any]:
	if not frappe.db.exists("DocType", "Permission Group Grant"):
		return {}
	rows = frappe.get_all(
		"Permission Group Grant",
		filters={"permission_group": group_name},
		fields=[
			"name",
			"user",
			"reference_doctype",
			"for_value",
			"applicable_for",
			"apply_to_all_doctypes",
			"user_permission",
			"adopted",
			"is_default",
			"hide_descendants",
		],
	)
	mapped = {}
	for row in rows:
		key = (
			row.user,
			row.reference_doctype,
			row.for_value,
			cstr(row.applicable_for),
			cint(row.apply_to_all_doctypes),
		)
		mapped[key] = row
	return mapped


def _delete_grant(name: str) -> None:
	if frappe.db.exists("Permission Group Grant", name):
		frappe.delete_doc("Permission Group Grant", name, ignore_permissions=True, force=True)


def _ensure_user_permission(group_name: str, user: str, rule: dict) -> tuple[str, int]:
	existing = _find_user_permission(user, rule)
	if existing:
		adopted = 0 if cint(existing.frappehero_managed) else 1
		if adopted and not _flags_match(existing, rule):
			frappe.throw(
				_(
					"A User Permission for {0} already allows {1} = {2}, with different options. "
					"Remove that User Permission or match Is Default and Hide Descendants before adding it here."
				).format(user, rule["reference_doctype"], rule["for_value"])
			)
		_reject_sibling_conflicts(existing.name, group_name, user, rule)
		if not adopted:
			_update_managed_permission(existing.name, group_name, rule)
		return existing.name, adopted

	document = frappe.get_doc(
		{
			"doctype": "User Permission",
			"user": user,
			"allow": rule["reference_doctype"],
			"for_value": rule["for_value"],
			"apply_to_all_doctypes": rule["apply_to_all_doctypes"],
			"applicable_for": rule["applicable_for"] or None,
			"hide_descendants": rule["hide_descendants"],
			"is_default": rule["is_default"],
			"frappehero_group": group_name,
			"frappehero_managed": 1,
		}
	)
	try:
		document.insert(ignore_permissions=True)
	except frappe.ValidationError:
		frappe.throw(
			_(
				"Could not allow {0} = {1} for {2}. Another User Permission may already be the default for {0}."
			).format(rule["reference_doctype"], rule["for_value"], user)
		)
	return document.name, 0


def _find_user_permission(user: str, rule: dict):
	rows = frappe.get_all(
		"User Permission",
		filters={
			"user": user,
			"allow": rule["reference_doctype"],
			"for_value": rule["for_value"],
			"applicable_for": cstr(rule["applicable_for"]),
			"apply_to_all_doctypes": rule["apply_to_all_doctypes"],
		},
		fields=["name", "frappehero_managed", "is_default", "hide_descendants", "frappehero_group"],
		limit=1,
	)
	return rows[0] if rows else None


def _flags_match(existing, rule: dict) -> bool:
	return cint(existing.is_default) == rule["is_default"] and cint(existing.hide_descendants) == rule[
		"hide_descendants"
	]


def _reject_sibling_conflicts(user_permission: str, group_name: str, user: str, rule: dict) -> None:
	siblings = frappe.get_all(
		"Permission Group Grant",
		filters={"user_permission": user_permission, "permission_group": ["!=", group_name]},
		fields=["permission_group", "is_default", "hide_descendants"],
	)
	for sibling in siblings:
		if cint(sibling.is_default) != rule["is_default"] or cint(sibling.hide_descendants) != rule[
			"hide_descendants"
		]:
			frappe.throw(
				_(
					"{0} already receives {1} = {2} from {3} with different options. "
					"Use the same Is Default and Hide Descendants in both groups."
				).format(user, rule["reference_doctype"], rule["for_value"], sibling.permission_group)
			)


def _update_managed_permission(name: str, group_name: str, rule: dict) -> None:
	document = frappe.get_doc("User Permission", name)
	document.is_default = rule["is_default"]
	document.hide_descendants = rule["hide_descendants"]
	document.frappehero_group = group_name
	document.frappehero_managed = 1
	try:
		document.save(ignore_permissions=True)
	except frappe.ValidationError:
		frappe.throw(
			_(
				"Could not update {0} = {1} for {2}. Another value may already be the default for {0}."
			).format(rule["reference_doctype"], rule["for_value"], document.user)
		)
