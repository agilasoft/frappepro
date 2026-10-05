# Copyright (c) 2026, Agilasoft Cloud Technologies and contributors
# License: MIT. See license.txt

import unittest

try:
	import frappe
	from frappe.utils import cint

	try:
		from frappe.tests import IntegrationTestCase as FrappeTestCase
	except ImportError:
		from frappe.tests.utils import FrappeTestCase
except ImportError:
	frappe = None
	FrappeTestCase = unittest.TestCase


@unittest.skipUnless(frappe, "Frappe site is required")
class TestPermissionGroup(FrappeTestCase):
	def setUp(self):
		from frappepro.install import ensure_custom_fields

		ensure_custom_fields()
		self.user = self._ensure_user("fp-one@example.com", "FP One")
		self.other = self._ensure_user("fp-two@example.com", "FP Two")
		self._cleanup()

	def tearDown(self):
		self._cleanup()

	def test_group_creates_and_removes_user_permissions(self):
		group = self._group("FP Test Basic", ["Guest"])
		permission = self._permission("Guest")
		self.assertTrue(permission)
		self.assertEqual(cint(permission.frappepro_managed), 1)
		self.assertEqual(permission.frappepro_group, group.name)

		group.set("rules", [{"reference_doctype": "Role", "for_value": "All", "apply_to_all_doctypes": 1}])
		group.save()
		self.assertFalse(self._permission("Guest"))
		self.assertTrue(self._permission("All"))

		frappe.delete_doc("Permission Group", group.name)
		self.assertFalse(self._permission("All"))

	def test_shared_permission_survives_until_the_last_group(self):
		first = self._group("FP Test Share A", ["Guest"])
		second = self._group("FP Test Share B", ["Guest"])
		permission = self._permission("Guest")
		frappe.delete_doc("Permission Group", first.name)
		self.assertTrue(frappe.db.exists("User Permission", permission.name))
		frappe.delete_doc("Permission Group", second.name)
		self.assertFalse(frappe.db.exists("User Permission", permission.name))

	def test_disabling_lifts_restrictions(self):
		group = self._group("FP Test Disable", ["Guest"])
		group.enabled = 0
		group.save()
		self.assertFalse(self._permission("Guest"))
		group.enabled = 1
		group.save()
		self.assertTrue(self._permission("Guest"))

	def test_manual_permission_is_adopted_and_kept(self):
		manual = frappe.get_doc(
			{
				"doctype": "User Permission",
				"user": self.user,
				"allow": "Role",
				"for_value": "Guest",
				"apply_to_all_doctypes": 1,
			}
		).insert(ignore_permissions=True)
		group = self._group("FP Test Adopt", ["Guest"])
		grant = frappe.db.get_value(
			"Permission Group Grant",
			{"permission_group": group.name, "user": self.user, "for_value": "Guest"},
			["adopted", "user_permission"],
			as_dict=True,
		)
		self.assertEqual(cint(grant.adopted), 1)
		self.assertEqual(grant.user_permission, manual.name)
		frappe.delete_doc("Permission Group", group.name)
		self.assertTrue(frappe.db.exists("User Permission", manual.name))
		self.assertEqual(cint(frappe.db.get_value("User Permission", manual.name, "frappepro_managed")), 0)

	def test_conflicting_manual_default_is_rejected(self):
		frappe.get_doc(
			{
				"doctype": "User Permission",
				"user": self.user,
				"allow": "Role",
				"for_value": "Guest",
				"apply_to_all_doctypes": 1,
				"is_default": 1,
			}
		).insert(ignore_permissions=True)
		with self.assertRaises(frappe.ValidationError):
			self._group("FP Test Conflict", ["Guest"], is_default=0)

	def test_administrator_and_bad_rules_are_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc(
				{
					"doctype": "Permission Group",
					"group_name": "FP Test Admin",
					"members": [{"user": "Administrator"}],
					"rules": [{"reference_doctype": "Role", "for_value": "Guest", "apply_to_all_doctypes": 1}],
				}
			).insert()
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc(
				{
					"doctype": "Permission Group",
					"group_name": "FP Test Narrow",
					"members": [{"user": self.user}],
					"rules": [
						{
							"reference_doctype": "Role",
							"for_value": "Guest",
							"apply_to_all_doctypes": 0,
						}
					],
				}
			).insert()

	def test_studio_search_finds_the_group(self):
		from frappepro.permission_studio.api import get_studio

		group = self._group("FP Test Searchable", ["All"])
		result = get_studio({"search": group.group_name, "user": self.user, "reference_doctype": "Role"})
		self.assertEqual(result["total"], 1)
		self.assertEqual(result["groups"][0]["name"], group.name)
		self.assertGreaterEqual(result["summary"]["rules"], 1)

	def _group(self, name, values, is_default=0):
		return frappe.get_doc(
			{
				"doctype": "Permission Group",
				"group_name": name,
				"enabled": 1,
				"members": [{"user": self.user}],
				"rules": [
					{
						"reference_doctype": "Role",
						"for_value": value,
						"apply_to_all_doctypes": 1,
						"is_default": is_default,
					}
					for value in values
				],
			}
		).insert()

	def _permission(self, value):
		rows = frappe.get_all(
			"User Permission",
			filters={"user": self.user, "allow": "Role", "for_value": value},
			fields=["name", "frappepro_managed", "frappepro_group"],
			limit=1,
		)
		return rows[0] if rows else None

	def _ensure_user(self, email, first_name):
		if not frappe.db.exists("User", email):
			frappe.get_doc(
				{
					"doctype": "User",
					"email": email,
					"first_name": first_name,
					"send_welcome_email": 0,
					"user_type": "System User",
				}
			).insert(ignore_permissions=True)
		return email

	def _cleanup(self):
		for name in frappe.get_all(
			"Permission Group", filters={"group_name": ["like", "FP Test%"]}, pluck="name"
		):
			frappe.delete_doc("Permission Group", name, force=True, ignore_permissions=True)
		for user in (getattr(self, "user", None), getattr(self, "other", None)):
			if not user:
				continue
			for name in frappe.get_all("User Permission", filters={"user": user}, pluck="name"):
				frappe.delete_doc("User Permission", name, force=True, ignore_permissions=True)
