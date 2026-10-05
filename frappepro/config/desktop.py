from frappe import _


def get_data():
	return [
		{
			"module_name": "Permission Studio",
			"category": "Modules",
			"label": _("Permission Studio"),
			"color": "blue",
			"icon": "octicon octicon-shield",
			"type": "module",
			"description": _("Group users and choose the records they may access."),
		}
	]
