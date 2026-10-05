# Copyright (c) 2026, Agilasoft Cloud Technologies and contributors
# License: MIT. See license.txt

from __future__ import annotations

import frappe


def before_uninstall() -> None:
	"""Lift restrictions this app created, then drop its custom fields.

	User Permissions owned by Frappe Hero are restrictive. Leaving them behind
	after uninstall would keep limiting users with no screen left to edit them.
	"""
	_delete_grants()
	_delete_managed_user_permissions()
	_delete_custom_fields()


def _delete_grants() -> None:
	if not frappe.db.table_exists("Permission Group Grant"):
		return
	frappe.db.sql("DELETE FROM `tabPermission Group Grant`")


def _delete_managed_user_permissions() -> None:
	if not frappe.db.table_exists("User Permission"):
		return
	if not frappe.db.has_column("User Permission", "frappehero_managed"):
		return
	names = frappe.get_all("User Permission", filters={"frappehero_managed": 1}, pluck="name")
	for name in names:
		frappe.delete_doc("User Permission", name, ignore_permissions=True, force=True)


def _delete_custom_fields() -> None:
	for fieldname in ("frappehero_group", "frappehero_managed"):
		name = frappe.db.get_value("Custom Field", {"dt": "User Permission", "fieldname": fieldname})
		if name:
			frappe.delete_doc("Custom Field", name, ignore_permissions=True, force=True)
