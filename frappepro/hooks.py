app_name = "frappepro"
app_title = "FrappePro"
app_publisher = "Agilasoft Cloud Technologies"
app_description = "Graphical permission groups for Frappe. Group users and choose the records they may access."
app_email = "info@agilasoft.com"
app_license = "MIT"
app_logo_url = "/assets/frappepro/images/logo.svg"
app_home = "/desk/permission-studio"

# Send non-GET requests for this app's endpoints as JSON bodies.
use_json_request_body = True

add_to_apps_screen = [
	{
		"name": "frappepro",
		"logo": "/assets/frappepro/images/logo.svg",
		"title": "FrappePro",
		"route": app_home,
		"has_permission": "frappepro.permission_studio.api.has_app_permission",
	}
]

# Installation
# ------------
after_install = "frappepro.install.after_install"
after_migrate = "frappepro.install.after_migrate"

# Uninstallation
# ------------
before_uninstall = "frappepro.uninstall.before_uninstall"

# Testing
# -------
before_tests = "frappepro.install.before_tests"

export_python_type_annotations = True
require_type_annotated_api_methods = True
