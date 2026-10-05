# Copyright (c) 2026, Agilasoft Cloud Technologies and contributors
# License: MIT. See license.txt

from __future__ import annotations

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

CUSTOM_FIELDS: dict[str, list[dict]] = {
	"User Permission": [
		{
			"fieldname": "frappepro_group",
			"label": "FrappePro Group",
			"fieldtype": "Link",
			"options": "Permission Group",
			"insert_after": "user",
			"read_only": 1,
			"no_copy": 1,
			"in_list_view": 1,
			"in_standard_filter": 1,
			"description": "Permission Group that last synced this restriction.",
		},
		{
			"fieldname": "frappepro_managed",
			"label": "Managed by FrappePro",
			"fieldtype": "Check",
			"insert_after": "frappepro_group",
			"read_only": 1,
			"no_copy": 1,
			"default": "0",
			"description": "FrappePro created this User Permission and removes it when the group no longer grants it.",
		},
	]
}


def after_install() -> None:
	ensure_custom_fields()


def after_migrate() -> None:
	ensure_custom_fields()


def before_tests() -> None:
	ensure_custom_fields()


def ensure_custom_fields() -> None:
	"""Create the User Permission fields Permission Studio uses to track what it owns."""
	create_custom_fields(CUSTOM_FIELDS, ignore_validate=True, update=True)
