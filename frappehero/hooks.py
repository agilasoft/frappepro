app_name = "frappehero"
app_title = "Frappe Hero"
app_publisher = "Agilasoft Cloud Technologies"
app_description = "Graphical permission groups for Frappe. Group users and choose the records they may access."
app_email = "info@agilasoft.com"
app_license = "MIT"
app_logo_url = "/assets/frappehero/images/logo.svg"
app_home = "/desk/permission-studio"

# Send non-GET requests for this app's endpoints as JSON bodies.
use_json_request_body = True

add_to_apps_screen = [
	{
		"name": "frappehero",
		"logo": "/assets/frappehero/images/logo.svg",
		"title": "Frappe Hero",
		"route": app_home,
		"has_permission": "frappehero.permission_studio.api.has_app_permission",
	}
]

# Installation
# ------------
after_install = "frappehero.install.after_install"
after_migrate = "frappehero.install.after_migrate"

# Uninstallation
# ------------
before_uninstall = "frappehero.uninstall.before_uninstall"

# Testing
# -------
before_tests = "frappehero.install.before_tests"

export_python_type_annotations = True
require_type_annotated_api_methods = True
