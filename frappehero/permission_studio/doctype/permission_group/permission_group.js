const BLOCKED_DOCTYPES = [
	"Permission Group",
	"Permission Group Member",
	"Permission Group Rule",
	"Permission Group Grant",
	"User Permission",
	"DocPerm",
	"Custom DocPerm",
	"Has Role",
];

frappe.ui.form.on("Permission Group", {
	refresh(frm) {
		frm.set_intro(
			__(
				"Members only see the values listed below for each DocType. Role permissions still control what they can do. Open Permission Studio for the graphical editor."
			)
		);
		if (!frm.is_new()) {
			frm.add_custom_button(__("Open in Permission Studio"), () => {
				frappe.set_route("permission-studio", frm.doc.name);
			});
		}
		frm.set_query("user", "members", () => ({
			filters: {
				user_type: "System User",
				name: ["not in", ["Guest", "Administrator"]],
			},
		}));
		frm.set_query("reference_doctype", "rules", () => ({
			filters: {
				istable: 0,
				issingle: 0,
				name: ["not in", BLOCKED_DOCTYPES],
			},
		}));
		frm.set_query("applicable_for", "rules", () => ({
			filters: {
				istable: 0,
				issingle: 0,
				name: ["not in", BLOCKED_DOCTYPES],
			},
		}));
	},
});

frappe.ui.form.on("Permission Group Rule", {
	apply_to_all_doctypes(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (row.apply_to_all_doctypes) {
			frappe.model.set_value(cdt, cdn, "applicable_for", "");
		}
	},
});

frappe.listview_settings["Permission Group"] = {
	add_fields: ["enabled"],
	get_indicator(doc) {
		if (cint(doc.enabled)) {
			return [__("Active"), "green", "enabled,=,1"];
		}
		return [__("Disabled"), "grey", "enabled,=,0"];
	},
	onload(listview) {
		listview.page.add_inner_button(__("Permission Studio"), () => {
			frappe.set_route("permission-studio");
		});
	},
};
