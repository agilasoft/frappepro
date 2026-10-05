# Copyright (c) 2026, Agilasoft Cloud Technologies and contributors
# License: MIT. See license.txt

from frappe.model.document import Document
from frappe.utils import cint

from frappehero.permission_studio.sync import release_user_permission


class PermissionGroupGrant(Document):
	def after_delete(self):
		release_user_permission(self.user_permission, self.permission_group, cint(self.adopted))
