# Copyright (c) 2026, Agilasoft Cloud Technologies and contributors
# License: MIT. See license.txt

from frappe.model.document import Document

from frappehero.permission_studio.sync import clear_group, sync_group, validate_group


class PermissionGroup(Document):
	def validate(self):
		validate_group(self)

	def on_update(self):
		sync_group(self)

	def on_trash(self):
		clear_group(self.name)
