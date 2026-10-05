# Copyright (c) 2026, Agilasoft Cloud Technologies and contributors
# License: MIT. See license.txt

import unittest

from frappepro.permission_studio.normalize import (
	BLOCKED_DOCTYPES,
	PermissionSetupError,
	build_coverage_where,
	build_group_where,
	clean_group_name,
	desired_grants,
	group_order_by,
	like,
	prepare_members,
	prepare_rules,
)


class TestNormalize(unittest.TestCase):
	def test_like_escapes_wildcards(self):
		self.assertEqual(like("100%_done"), "%100\\%\\_done%")

	def test_group_name_is_required(self):
		with self.assertRaises(PermissionSetupError):
			clean_group_name("   ")

	def test_members_skip_blanks_and_duplicates(self):
		self.assertEqual(
			prepare_members([{"user": "a@example.com"}, {"user": " a@example.com "}, "", {"user": "b@example.com"}]),
			["a@example.com", "b@example.com"],
		)

	def test_administrator_cannot_be_a_member(self):
		with self.assertRaises(PermissionSetupError):
			prepare_members(["Administrator"])

	def test_rules_clear_applicable_for_when_applied_everywhere(self):
		rules = prepare_rules(
			[
				{
					"reference_doctype": "Company",
					"for_value": "Acme",
					"apply_to_all_doctypes": 1,
					"applicable_for": "Sales Invoice",
					"hide_descendants": 1,
					"is_default": 1,
				}
			]
		)
		self.assertEqual(rules[0]["applicable_for"], "")
		self.assertEqual(rules[0]["hide_descendants"], 0)
		self.assertEqual(rules[0]["is_default"], 1)

	def test_tree_doctype_keeps_hide_descendants(self):
		rules = prepare_rules(
			[{"reference_doctype": "Company", "for_value": "Acme", "hide_descendants": 1}],
			tree_doctypes={"Company"},
		)
		self.assertEqual(rules[0]["hide_descendants"], 1)

	def test_duplicate_rule_is_rejected(self):
		with self.assertRaises(PermissionSetupError):
			prepare_rules(
				[
					{"reference_doctype": "Role", "for_value": "Guest"},
					{"reference_doctype": "Role", "for_value": "Guest"},
				]
			)

	def test_narrowed_rule_needs_applicable_for(self):
		with self.assertRaises(PermissionSetupError):
			prepare_rules(
				[{"reference_doctype": "Role", "for_value": "Guest", "apply_to_all_doctypes": 0}]
			)

	def test_only_one_default_per_doctype(self):
		with self.assertRaises(PermissionSetupError):
			prepare_rules(
				[
					{"reference_doctype": "Role", "for_value": "Guest", "is_default": 1},
					{"reference_doctype": "Role", "for_value": "All", "is_default": 1},
				]
			)
		with self.assertRaises(PermissionSetupError):
			prepare_rules(
				[
					{
						"reference_doctype": "Role",
						"for_value": "Guest",
						"is_default": 1,
						"apply_to_all_doctypes": 0,
						"applicable_for": "User",
					},
					{"reference_doctype": "Role", "for_value": "All", "is_default": 1},
				]
			)

	def test_blocked_doctype(self):
		self.assertIn("User Permission", BLOCKED_DOCTYPES)
		with self.assertRaises(PermissionSetupError):
			prepare_rules([{"reference_doctype": "User Permission", "for_value": "UP-0001"}])

	def test_disabled_group_grants_nothing(self):
		rules = prepare_rules([{"reference_doctype": "Role", "for_value": "Guest"}])
		self.assertEqual(desired_grants(["a@example.com"], rules, enabled=0), {})
		self.assertEqual(len(desired_grants(["a@example.com", "b@example.com"], rules, enabled=1)), 2)

	def test_group_filters_are_parameterized(self):
		where, params = build_group_where(
			{
				"search": "50%",
				"user": "a@example.com",
				"reference_doctype": "Company",
				"status": "active",
				"preset": "mine",
				"value": "Acme",
			},
			session_user="owner@example.com",
		)
		self.assertIn("pg.group_name LIKE %(search)s", where)
		self.assertIn("m_user.user = %(filter_user)s", where)
		self.assertIn("r_dt.reference_doctype = %(filter_doctype)s", where)
		self.assertIn("pg.enabled = 1", where)
		self.assertIn("pg.owner = %(owner)s", where)
		self.assertEqual(params["search"], "%50\\%%")
		self.assertEqual(params["filter_user"], "a@example.com")
		self.assertEqual(params["owner"], "owner@example.com")
		self.assertNotIn("50%", where)

	def test_unknown_sort_falls_back(self):
		self.assertEqual(group_order_by("modified; drop table"), group_order_by(None))
		self.assertIn("group_name", group_order_by("name"))

	def test_coverage_filters(self):
		where, params = build_coverage_where(
			{
				"enabled_only": 1,
				"defaults_only": 1,
				"narrowed_only": 1,
				"user": "a@example.com",
				"query": "north_1",
			}
		)
		self.assertIn("pg.enabled = 1", where)
		self.assertIn("r.is_default = 1", where)
		self.assertIn("r.apply_to_all_doctypes, 0) = 0", where)
		self.assertEqual(params["user"], "a@example.com")
		self.assertEqual(params["query"], "%north\\_1%")


if __name__ == "__main__":
	unittest.main()
