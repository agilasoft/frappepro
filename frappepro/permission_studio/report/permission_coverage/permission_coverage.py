# Copyright (c) 2026, Agilasoft Cloud Technologies and contributors
# License: MIT. See license.txt

import frappe
from frappe import _

from frappepro.permission_studio.queries import coverage_rows


def execute(filters=None):
	frappe.only_for("System Manager")
	filters = filters or {}
	columns = [
		{"label": _("User"), "fieldname": "user", "fieldtype": "Link", "options": "User", "width": 180},
		{"label": _("Full Name"), "fieldname": "full_name", "fieldtype": "Data", "width": 160},
		{
			"label": _("Permission Group"),
			"fieldname": "permission_group",
			"fieldtype": "Link",
			"options": "Permission Group",
			"width": 180,
		},
		{"label": _("DocType"), "fieldname": "reference_doctype", "fieldtype": "Link", "options": "DocType", "width": 140},
		{"label": _("Value"), "fieldname": "for_value", "fieldtype": "Data", "width": 160},
		{"label": _("Applies To"), "fieldname": "applies_to", "fieldtype": "Data", "width": 160},
		{"label": _("Default"), "fieldname": "is_default", "fieldtype": "Check", "width": 80},
		{"label": _("Hide Descendants"), "fieldname": "hide_descendants", "fieldtype": "Check", "width": 120},
		{"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 100},
	]
	data = coverage_rows(filters, limit=5000, offset=0)
	return columns, data
