frappe.query_reports["Permission Coverage"] = {
	filters: [
		{
			fieldname: "user",
			label: __("User"),
			fieldtype: "Link",
			options: "User",
		},
		{
			fieldname: "permission_group",
			label: __("Permission Group"),
			fieldtype: "Link",
			options: "Permission Group",
		},
		{
			fieldname: "reference_doctype",
			label: __("DocType"),
			fieldtype: "Link",
			options: "DocType",
		},
		{
			fieldname: "query",
			label: __("Search"),
			fieldtype: "Data",
		},
		{
			fieldname: "enabled_only",
			label: __("Enabled Groups Only"),
			fieldtype: "Check",
			default: 1,
		},
		{
			fieldname: "defaults_only",
			label: __("Defaults Only"),
			fieldtype: "Check",
		},
		{
			fieldname: "narrowed_only",
			label: __("Narrowed To One DocType"),
			fieldtype: "Check",
		},
	],
};
