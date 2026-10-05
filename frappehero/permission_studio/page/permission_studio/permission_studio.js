frappe.provide("frappehero");

frappe.pages["permission-studio"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Permission Studio"),
		single_column: true,
	});
	frappe.require("/assets/frappehero/css/permission_studio.css");
	wrapper.studio = new frappehero.Studio(wrapper, page);
};

frappe.pages["permission-studio"].on_page_show = function (wrapper) {
	if (wrapper.studio) {
		wrapper.studio.on_show();
	}
};

frappehero.Studio = class Studio {
	constructor(wrapper, page) {
		this.wrapper = wrapper;
		this.page = page;
		this.state = {
			view: "groups",
			tab: "members",
			filters: {
				search: "",
				user: "",
				user_label: "",
				reference_doctype: "",
				status: "all",
				preset: "all",
				sort: "modified",
				value: "",
			},
			coverage: {
				query: "",
				user: "",
				permission_group: "",
				reference_doctype: "",
				enabled_only: 1,
				defaults_only: 0,
				narrowed_only: 0,
			},
			offset: 0,
			coverage_offset: 0,
			groups: [],
			summary: { groups: 0, users: 0, rules: 0 },
			total: 0,
			limit: 24,
			coverage_rows: [],
			coverage_total: 0,
			coverage_limit: 50,
			options: { groups: [], users: [], doctypes: [] },
			draft: null,
			dirty: false,
			saving: false,
			selected_rule: null,
		};
		this.queue_groups = frappe.utils.debounce(() => this.load_groups(), 250);
		this.queue_coverage = frappe.utils.debounce(() => this.load_coverage(), 250);
		this.make();
		this.on_show();
	}

	make() {
		this.body = $(this.wrapper).find(".layout-main-section");
		if (!this.body.length) {
			this.body = $(this.page.main);
		}
		this.body.addClass("fp-page");
		this.body.append(`
			<div class="fp-studio">
				<div class="fp-explainer"></div>
				<div class="fp-toolbar"></div>
				<div class="fp-stage"></div>
			</div>
		`);
		$(".fp-studio-drawer").remove();
		this.$drawer = $(`<div class="fp-studio-drawer" hidden></div>`).appendTo(document.body);
		this.$explainer = this.body.find(".fp-explainer");
		this.$toolbar = this.body.find(".fp-toolbar");
		this.$stage = this.body.find(".fp-stage");
		this.body.on("click", "[data-action]", (event) => this.on_click(event));
		this.body.on("input", "[data-bind]", (event) => this.on_bind(event));
		this.body.on("change", "[data-bind]", (event) => this.on_bind(event));
		this.$drawer.on("click", "[data-action]", (event) => this.on_click(event));
		this.$drawer.on("input", "[data-drawer]", (event) => this.on_drawer_input(event));
		this.$drawer.on("change", "[data-drawer]", (event) => this.on_drawer_input(event));
		this.$drawer.on("change", "[data-pick]", (event) => this.on_pick(event));
		this.render_explainer();
	}

	on_show() {
		const route = frappe.get_route() || [];
		const key = route.join("/");
		if (key === this.last_route) {
			return;
		}
		this.last_route = key;
		const target = route[1] ? decodeURIComponent(route[1]) : "";
		if (target) {
			this.fetch_group(target);
			return;
		}
		if (this.state.view === "editor" && this.state.draft && !this.state.draft.name) {
			this.render();
			return;
		}
		this.state.view = "groups";
		this.load_options();
		this.load_groups();
	}

	remember(name) {
		this.last_route = name ? `permission-studio/${name}` : "permission-studio";
	}

	call(method, args) {
		return frappe
			.call({
				method: `frappehero.permission_studio.api.${method}`,
				args: args || {},
			})
			.then((response) => response.message);
	}

	render_explainer() {
		let dismissed = false;
		try {
			dismissed = localStorage.getItem("frappehero-hint") === "1";
		} catch (error) {
			dismissed = false;
		}
		if (dismissed) {
			this.$explainer.empty();
			return;
		}
		this.$explainer.html(`
			<div class="fp-hint">
				<p>${__(
					"Permission groups narrow which records people can see. They do not grant roles. Adding Company → Acme means those members only see Acme."
				)}</p>
				<button type="button" data-action="dismiss-hint">${__("Dismiss")}</button>
			</div>
		`);
	}

	render() {
		this.sync_actions();
		this.render_toolbar();
		if (this.state.view === "groups") {
			this.render_groups();
		} else if (this.state.view === "coverage") {
			this.render_coverage();
		} else {
			this.render_editor();
		}
	}

	sync_actions() {
		if (this.page.clear_inner_toolbar) {
			this.page.clear_inner_toolbar();
		}
		this.page.clear_primary_action();
		if (this.page.clear_secondary_action) {
			this.page.clear_secondary_action();
		}
		if (this.state.view === "editor") {
			this.page.set_primary_action(
				this.state.saving ? __("Saving") : __("Save"),
				() => this.save(),
				"save"
			);
			this.page.add_inner_button(__("Back"), () => this.back());
			if (this.state.draft && this.state.draft.name) {
				this.page.add_inner_button(__("Duplicate"), () => this.duplicate());
				this.page.add_inner_button(__("Reapply"), () => this.resync());
				this.page.add_inner_button(__("Delete"), () => this.remove_group());
			}
			return;
		}
		this.page.set_primary_action(__("New Group"), () => this.new_group(), "add");
	}

	render_toolbar() {
		if (this.state.view === "editor") {
			this.$toolbar.empty();
			return;
		}
		if (this.state.view === "coverage") {
			this.render_coverage_toolbar();
			return;
		}
		const filters = this.state.filters;
		this.$toolbar.html(`
			<div class="fp-toolbar-row">
				<div class="fp-switcher">
					<button type="button" class="is-active" data-action="set-view" data-view="groups">${__("Groups")}</button>
					<button type="button" data-action="set-view" data-view="coverage">${__("Coverage")}</button>
				</div>
				<label class="fp-search">
					<span class="fp-sr">${__("Search")}</span>
					<input type="search" data-bind="search" value="${esc(filters.search)}" placeholder="${__(
						"Search groups, users, or values"
					)}">
				</label>
				<label class="fp-select">
					<span>${__("Sort")}</span>
					<select data-bind="sort">
						${option("modified", __("Recent"), filters.sort)}
						${option("name", __("Name"), filters.sort)}
						${option("members", __("Most members"), filters.sort)}
						${option("rules", __("Most values"), filters.sort)}
					</select>
				</label>
			</div>
			<div class="fp-toolbar-row">
				<div class="fp-chips">
					${chip("status", "all", __("All"), filters.status)}
					${chip("status", "active", __("Active"), filters.status)}
					${chip("status", "disabled", __("Disabled"), filters.status)}
					${chip("preset", "mine", __("Mine"), filters.preset)}
					${chip("preset", "empty", __("Incomplete"), filters.preset)}
					${chip("preset", "inactive", __("Turned off"), filters.preset)}
				</div>
				<div class="fp-combo">
					<label>
						<span>${__("User")}</span>
						<input type="search" data-bind="user-query" value="${esc(
							filters.user_label || filters.user
						)}" placeholder="${__("Any user")}">
					</label>
					<div class="fp-suggest" data-suggest="user" hidden></div>
					${filters.user ? `<button type="button" data-action="clear-filter" data-filter="user">${__("Clear")}</button>` : ""}
				</div>
				<div class="fp-combo">
					<label>
						<span>${__("DocType")}</span>
						<input type="search" data-bind="doctype-query" value="${esc(
							filters.reference_doctype
						)}" placeholder="${__("Any DocType")}">
					</label>
					<div class="fp-suggest" data-suggest="doctype" hidden></div>
					${
						filters.reference_doctype
							? `<button type="button" data-action="clear-filter" data-filter="reference_doctype">${__("Clear")}</button>`
							: ""
					}
				</div>
				<label class="fp-search fp-value-filter">
					<span>${__("Value")}</span>
					<input type="search" data-bind="value" value="${esc(filters.value)}" placeholder="${__(
						"Contains"
					)}">
				</label>
			</div>
		`);
	}

	render_coverage_toolbar() {
		const coverage = this.state.coverage;
		const groups = this.state.options.groups || [];
		const users = this.state.options.users || [];
		const doctypes = this.state.options.doctypes || [];
		this.$toolbar.html(`
			<div class="fp-toolbar-row">
				<div class="fp-switcher">
					<button type="button" data-action="set-view" data-view="groups">${__("Groups")}</button>
					<button type="button" class="is-active" data-action="set-view" data-view="coverage">${__(
						"Coverage"
					)}</button>
				</div>
				<label class="fp-search">
					<span class="fp-sr">${__("Search coverage")}</span>
					<input type="search" data-bind="coverage-query" value="${esc(
						coverage.query
					)}" placeholder="${__("Search user, group, DocType, or value")}">
				</label>
			</div>
			<div class="fp-toolbar-row">
				<label class="fp-select">
					<span>${__("User")}</span>
					<select data-bind="coverage-user">
						<option value="">${__("Any user")}</option>
						${users
							.map(
								(user) =>
									`<option value="${esc(user.user)}" ${
										user.user === coverage.user ? "selected" : ""
									}>${esc(user.full_name || user.user)}</option>`
							)
							.join("")}
					</select>
				</label>
				<label class="fp-select">
					<span>${__("Group")}</span>
					<select data-bind="coverage-group">
						<option value="">${__("Any group")}</option>
						${groups
							.map(
								(group) =>
									`<option value="${esc(group.name)}" ${
										group.name === coverage.permission_group ? "selected" : ""
									}>${esc(group.group_name)}</option>`
							)
							.join("")}
					</select>
				</label>
				<label class="fp-select">
					<span>${__("DocType")}</span>
					<select data-bind="coverage-doctype">
						<option value="">${__("Any DocType")}</option>
						${doctypes
							.map(
								(doctype) =>
									`<option value="${esc(doctype)}" ${
										doctype === coverage.reference_doctype ? "selected" : ""
									}>${esc(doctype)}</option>`
							)
							.join("")}
					</select>
				</label>
				<label class="fp-check"><input type="checkbox" data-bind="enabled_only" ${
					coverage.enabled_only ? "checked" : ""
				}> ${__("Enabled groups only")}</label>
				<label class="fp-check"><input type="checkbox" data-bind="defaults_only" ${
					coverage.defaults_only ? "checked" : ""
				}> ${__("Defaults only")}</label>
				<label class="fp-check"><input type="checkbox" data-bind="narrowed_only" ${
					coverage.narrowed_only ? "checked" : ""
				}> ${__("Narrowed to one DocType")}</label>
			</div>
		`);
	}

	async load_options() {
		try {
			this.state.options = (await this.call("get_filter_options")) || this.state.options;
			if (this.state.view === "coverage") {
				this.render_toolbar();
			}
		} catch (error) {
			// The desk already shows the server message.
		}
	}

	async load_groups() {
		this.$stage.html(`<div class="fp-loading">${__("Loading groups…")}</div>`);
		try {
			const result = await this.call("get_studio", {
				filters: {
					...this.state.filters,
					limit: this.state.limit,
					offset: this.state.offset,
				},
			});
			this.state.groups = result.groups || [];
			this.state.summary = result.summary || { groups: 0, users: 0, rules: 0 };
			this.state.total = result.total || 0;
			this.render_groups();
		} catch (error) {
			this.$stage.html(`<div class="fp-empty">${__("Groups could not be loaded.")}</div>`);
		}
	}

	render_groups() {
		const summary = this.state.summary;
		const cards = this.state.groups
			.map((group) => {
				const doctypes = (group.doctypes || [])
					.slice(0, 4)
					.map(
						(item) =>
							`<span class="fp-chip-doctype" style="--hue:${hue(item.doctype)}">${esc(
								item.doctype
							)} · ${item.count}</span>`
					)
					.join("");
				const extra = (group.doctypes || []).length - 4;
				const avatars = (group.members || [])
					.slice(0, 5)
					.map((member) => avatar(member.user, member.full_name, member.user_image))
					.join("");
				const overflow = group.member_count - Math.min(group.member_count, 5);
				return `
					<article class="fp-card ${group.enabled ? "" : "is-off"}" data-action="open-group" data-name="${esc(
						group.name
					)}">
						<header>
							<h3>${esc(group.group_name)}</h3>
							<button type="button" class="fp-switch ${group.enabled ? "is-on" : ""}" role="switch" aria-checked="${
								group.enabled ? "true" : "false"
							}" data-action="toggle-group" data-name="${esc(group.name)}" data-enabled="${
								group.enabled ? "1" : "0"
							}" title="${group.enabled ? __("Disable group") : __("Enable group")}">
								<span></span>
							</button>
						</header>
						<p>${esc(group.description || __("No description"))}</p>
						<div class="fp-avatars">${avatars}${
							overflow > 0 ? `<span class="fp-more">+${overflow}</span>` : ""
						}</div>
						<div class="fp-doctype-row">${doctypes}${
							extra > 0 ? `<span class="fp-more-types">+${extra}</span>` : ""
						}</div>
						<footer>
							<span>${__("{0} members", [group.member_count])}</span>
							<span>${__("{0} values", [group.rule_count])}</span>
						</footer>
					</article>
				`;
			})
			.join("");
		const page = Math.floor(this.state.offset / this.state.limit) + 1;
		const pages = Math.max(1, Math.ceil(this.state.total / this.state.limit));
		this.$stage.html(`
			<div class="fp-stats">
				<div><strong>${summary.groups || 0}</strong><span>${__("Groups")}</span></div>
				<div><strong>${summary.users || 0}</strong><span>${__("Users")}</span></div>
				<div><strong>${summary.rules || 0}</strong><span>${__("Values")}</span></div>
			</div>
			${
				cards
					? `<div class="fp-cards">${cards}</div>`
					: `<div class="fp-empty">
						<h3>${__("No groups match")}</h3>
						<p>${__("Create a group, add people, then choose the records they are allowed to see.")}</p>
						<button type="button" class="btn btn-primary btn-sm" data-action="new-group">${__("New Group")}</button>
					</div>`
			}
			${
				this.state.total > this.state.limit
					? `<div class="fp-pager">
						<button type="button" data-action="page" data-dir="-1" ${page <= 1 ? "disabled" : ""}>${__("Previous")}</button>
						<span>${__("{0} of {1}", [page, pages])}</span>
						<button type="button" data-action="page" data-dir="1" ${page >= pages ? "disabled" : ""}>${__("Next")}</button>
					</div>`
					: ""
			}
		`);
	}

	async load_coverage() {
		this.$stage.html(`<div class="fp-loading">${__("Loading coverage…")}</div>`);
		try {
			const result = await this.call("get_coverage", {
				filters: {
					...this.state.coverage,
					limit: this.state.coverage_limit,
					offset: this.state.coverage_offset,
				},
			});
			this.state.coverage_rows = result.rows || [];
			this.state.coverage_total = result.total || 0;
			this.render_coverage();
		} catch (error) {
			this.$stage.html(`<div class="fp-empty">${__("Coverage could not be loaded.")}</div>`);
		}
	}

	render_coverage() {
		const rows = this.state.coverage_rows
			.map(
				(row) => `
				<tr>
					<td>
						<div class="fp-person">
							${avatar(row.user, row.full_name, row.user_image)}
							<div>
								<strong>${esc(row.full_name || row.user)}</strong>
								<span>${esc(row.user)}</span>
							</div>
						</div>
					</td>
					<td><button type="button" class="btn-link fp-link" data-action="open-group" data-name="${esc(
						row.permission_group
					)}">${esc(row.group_name)}</button></td>
					<td><span class="fp-chip-doctype" style="--hue:${hue(row.reference_doctype)}">${esc(
						row.reference_doctype
					)}</span></td>
					<td>${esc(row.for_value)}</td>
					<td>${esc(row.applies_to)}</td>
					<td>${row.is_default ? __("Yes") : ""}</td>
					<td>${row.hide_descendants ? __("Hidden") : ""}</td>
					<td><span class="fp-status ${row.enabled ? "is-on" : ""}">${
						row.enabled ? __("Applied") : __("Not applied")
					}</span></td>
				</tr>`
			)
			.join("");
		const page = Math.floor(this.state.coverage_offset / this.state.coverage_limit) + 1;
		const pages = Math.max(1, Math.ceil(this.state.coverage_total / this.state.coverage_limit));
		this.$stage.html(`
			<p class="fp-note">${__(
				"Each row is one record a member is limited to. Disabled groups are kept here but are not applied until you turn them on."
			)}</p>
			<div class="fp-table-wrap">
				<table class="fp-table">
					<thead>
						<tr>
							<th>${__("User")}</th>
							<th>${__("Group")}</th>
							<th>${__("DocType")}</th>
							<th>${__("Value")}</th>
							<th>${__("Applies to")}</th>
							<th>${__("Default")}</th>
							<th>${__("Descendants")}</th>
							<th>${__("Status")}</th>
						</tr>
					</thead>
					<tbody>
						${
							rows ||
							`<tr><td colspan="8" class="fp-empty-cell">${__("Nothing matches these filters.")}</td></tr>`
						}
					</tbody>
				</table>
			</div>
			${
				this.state.coverage_total > this.state.coverage_limit
					? `<div class="fp-pager">
						<button type="button" data-action="coverage-page" data-dir="-1" ${page <= 1 ? "disabled" : ""}>${__(
							"Previous"
						)}</button>
						<span>${__("{0} of {1}", [String(page), String(pages)])} · ${this.state.coverage_total}</span>
						<button type="button" data-action="coverage-page" data-dir="1" ${page >= pages ? "disabled" : ""}>${__(
							"Next"
						)}</button>
					</div>`
					: `<p class="fp-count">${__("{0} rows", [this.state.coverage_total])}</p>`
			}
		`);
	}

	new_group() {
		this.state.draft = {
			name: null,
			group_name: "",
			description: "",
			enabled: 1,
			modified: null,
			members: [],
			rules: [],
		};
		this.state.dirty = false;
		this.state.tab = "members";
		this.state.selected_rule = null;
		this.state.view = "editor";
		this.remember(null);
		frappe.set_route("permission-studio");
		this.render();
		this.body.find("[data-bind='group_name']").trigger("focus");
	}

	async fetch_group(name) {
		this.state.view = "editor";
		this.$toolbar.empty();
		this.$stage.html(`<div class="fp-loading">${__("Loading group…")}</div>`);
		this.sync_actions();
		try {
			this.state.draft = await this.call("get_group", { name });
			this.state.dirty = false;
			this.state.tab = "members";
			this.state.selected_rule = null;
			this.render();
		} catch (error) {
			this.$stage.html(`<div class="fp-empty">${__("This group could not be opened.")}</div>`);
		}
	}

	render_editor() {
		const draft = this.state.draft;
		if (!draft) {
			return;
		}
		const tabs = ["members", "permissions", "preview"]
			.map((tab) => {
				const labels = {
					members: __("Members ({0})", [draft.members.length]),
					permissions: __("Records ({0})", [draft.rules.length]),
					preview: __("Access preview"),
				};
				return `<button type="button" class="${this.state.tab === tab ? "is-active" : ""}" data-action="editor-tab" data-tab="${tab}">${labels[tab]}</button>`;
			})
			.join("");
		this.$stage.html(`
			<div class="fp-editor ${draft.enabled ? "" : "is-off"}">
				<div class="fp-editor-head">
					<div class="fp-title-block">
						<input class="fp-title" data-bind="group_name" value="${esc(
							draft.group_name
						)}" placeholder="${__("Group name")}">
						<textarea data-bind="description" rows="2" placeholder="${__(
							"Who is this for?"
						)}">${esc(draft.description)}</textarea>
					</div>
					<label class="fp-enable">
						<span>${draft.enabled ? __("Restrictions active") : __("Restrictions lifted")}</span>
						<button type="button" class="fp-switch ${draft.enabled ? "is-on" : ""}" role="switch" data-action="draft-enabled" aria-checked="${
							draft.enabled ? "true" : "false"
						}"><span></span></button>
					</label>
				</div>
				<p class="fp-note">${
					draft.enabled
						? __(
								"Saving writes a User Permission for every member and value. Members will only see those values."
							)
						: __(
								"This group is off. Saving removes its User Permissions, so members may see more records."
							)
				}</p>
				<div class="fp-tabs">${tabs}</div>
				<div class="fp-panel">${this.panel_html()}</div>
			</div>
		`);
	}

	panel_html() {
		if (this.state.tab === "permissions") {
			return this.permissions_html();
		}
		if (this.state.tab === "preview") {
			return this.preview_html();
		}
		return this.members_html();
	}

	members_html() {
		const query = (this.state.member_query || "").toLowerCase();
		const members = this.state.draft.members.filter((member) => {
			if (!query) {
				return true;
			}
			return (
				(member.full_name || "").toLowerCase().includes(query) ||
				(member.user || "").toLowerCase().includes(query)
			);
		});
		const rows = members
			.map(
				(member) => `
				<div class="fp-row">
					${avatar(member.user, member.full_name, member.user_image)}
					<div>
						<strong>${esc(member.full_name || member.user)}</strong>
						<span>${esc(member.user)}${member.enabled ? "" : " · " + __("Disabled")}</span>
					</div>
					<button type="button" data-action="remove-member" data-user="${esc(member.user)}" aria-label="${__(
						"Remove"
					)}">×</button>
				</div>`
			)
			.join("");
		return `
			<div class="fp-panel-bar">
				<input type="search" data-bind="member-query" value="${esc(
					this.state.member_query || ""
				)}" placeholder="${__("Filter members")}">
				<button type="button" class="btn btn-default btn-sm" data-action="add-members">${__("Add members")}</button>
			</div>
			<div class="fp-list">
				${
					rows ||
					`<div class="fp-empty"><p>${__("No members yet. Add people, or everyone who has a role.")}</p></div>`
				}
			</div>
		`;
	}

	permissions_html() {
		const query = (this.state.rule_query || "").toLowerCase();
		const grouped = {};
		this.state.draft.rules.forEach((rule, index) => {
			const blob = `${rule.reference_doctype} ${rule.for_value} ${rule.value_label || ""}`.toLowerCase();
			if (query && !blob.includes(query)) {
				return;
			}
			grouped[rule.reference_doctype] = grouped[rule.reference_doctype] || [];
			grouped[rule.reference_doctype].push({ rule, index });
		});
		const sections = Object.keys(grouped)
			.map((doctype) => {
				const values = grouped[doctype]
					.map(({ rule, index }) => {
						const flags = [
							rule.is_default ? __("Default") : "",
							rule.hide_descendants ? __("Hide children") : "",
							rule.apply_to_all_doctypes ? "" : rule.applicable_for || __("Narrowed"),
						].filter(Boolean);
						return `
							<button type="button" class="fp-value ${
								this.state.selected_rule === index ? "is-selected" : ""
							}" data-action="select-rule" data-index="${index}">
								<span>${esc(rule.value_label || rule.for_value)}</span>
								${flags.map((flag) => `<em>${esc(flag)}</em>`).join("")}
								<span class="fp-x" data-action="remove-rule" data-index="${index}" aria-label="${__("Remove")}">×</span>
							</button>`;
					})
					.join("");
				return `
					<section class="fp-doctype">
						<header>
							<span class="fp-swatch" style="--hue:${hue(doctype)}"></span>
							<strong>${esc(doctype)}</strong>
							<span>${__("{0} values", [grouped[doctype].length])}</span>
						</header>
						<div class="fp-values">${values}</div>
					</section>`;
			})
			.join("");
		return `
			<div class="fp-panel-bar">
				<input type="search" data-bind="rule-query" value="${esc(
					this.state.rule_query || ""
				)}" placeholder="${__("Filter DocTypes or values")}">
				<button type="button" class="btn btn-default btn-sm" data-action="add-values">${__("Add records")}</button>
			</div>
			${sections || `<div class="fp-empty"><p>${__("No records yet. Choose a DocType, then the values members may see.")}</p></div>`}
			${this.rule_editor_html()}
		`;
	}

	rule_editor_html() {
		const rule = this.state.draft.rules[this.state.selected_rule];
		if (!rule) {
			return "";
		}
		return `
			<div class="fp-rule-editor">
				<strong>${esc(rule.reference_doctype)} · ${esc(rule.value_label || rule.for_value)}</strong>
				<label class="fp-check"><input type="checkbox" data-bind="rule-all" ${
					rule.apply_to_all_doctypes ? "checked" : ""
				}> ${__("Apply to all document types")}</label>
				${
					rule.apply_to_all_doctypes
						? ""
						: `<label class="fp-select"><span>${__("Applicable For")}</span>
							<input type="search" data-bind="rule-applicable" value="${esc(
								rule.applicable_for || ""
							)}" placeholder="${__("DocType")}">
							<div class="fp-suggest" data-suggest="applicable" hidden></div>
						</label>`
				}
				<label class="fp-check"><input type="checkbox" data-bind="rule-default" ${
					rule.is_default ? "checked" : ""
				}> ${__("Default value on new documents")}</label>
				${
					rule.is_tree
						? `<label class="fp-check"><input type="checkbox" data-bind="rule-hide" ${
								rule.hide_descendants ? "checked" : ""
							}> ${__("Hide descendant records")}</label>`
						: ""
				}
			</div>
		`;
	}

	preview_html() {
		if (!this.state.preview) {
			return `
				<div class="fp-empty">
					<p>${__("See the records each member will be limited to, including their other groups.")}</p>
					<button type="button" class="btn btn-default btn-sm" data-action="run-preview">${__("Show access")}</button>
				</div>`;
		}
		if (!this.state.preview.length) {
			return `<div class="fp-empty"><p>${__("Add members to preview access.")}</p></div>`;
		}
		return this.state.preview
			.map((person) => {
				const blocks = (person.doctypes || [])
					.map(
						(bucket) => `
						<div class="fp-preview-dt">
							<span class="fp-chip-doctype" style="--hue:${hue(bucket.doctype)}">${esc(bucket.doctype)}</span>
							<div>${bucket.values
								.map(
									(value) =>
										`<span class="fp-preview-value">${esc(value.value)} <em>${esc(
											(value.sources || []).join(", ")
										)}</em></span>`
								)
								.join("")}</div>
						</div>`
					)
					.join("");
				return `
					<article class="fp-preview">
						<header>${avatar(person.user, person.full_name, person.user_image)}
							<div><strong>${esc(person.full_name)}</strong><span>${esc(person.user)}</span></div>
						</header>
						${
							blocks ||
							`<p>${__("No record restrictions. They can see every record their roles allow.")}</p>`
						}
					</article>`;
			})
			.join("");
	}

	async run_preview() {
		this.state.preview = null;
		this.state.tab = "preview";
		this.render_editor();
		try {
			this.state.preview = await this.call("preview", { payload: this.payload() });
			this.render_editor();
		} catch (error) {
			this.state.preview = [];
		}
	}

	on_click(event) {
		const target = event.currentTarget;
		const action = target.dataset.action;
		const innermost = $(event.target).closest("[data-action]").get(0);
		if (!action || innermost !== target) {
			return;
		}
		if (action === "toggle-group" || action === "remove-rule") {
			event.stopPropagation();
		}
		if (action === "open-group") {
			event.preventDefault();
			this.open_group(target.dataset.name);
		} else if (action === "toggle-group") {
			event.preventDefault();
			this.toggle_group(target.dataset.name, target.dataset.enabled !== "1");
		} else if (action === "new-group") {
			this.new_group();
		} else if (action === "set-view") {
			this.set_view(target.dataset.view);
		} else if (action === "status" || action === "preset") {
			this.set_chip(action, target.dataset.value);
		} else if (action === "page") {
			this.turn_page(Number(target.dataset.dir));
		} else if (action === "coverage-page") {
			this.turn_coverage(Number(target.dataset.dir));
		} else if (action === "clear-filter") {
			this.clear_filter(target.dataset.filter);
		} else if (action === "dismiss-hint") {
			try {
				localStorage.setItem("frappehero-hint", "1");
			} catch (error) {
				// Ignore storage failures.
			}
			this.render_explainer();
		} else if (action === "editor-tab") {
			this.state.tab = target.dataset.tab;
			this.render_editor();
			if (target.dataset.tab === "preview" && !this.state.preview) {
				this.run_preview();
			}
		} else if (action === "draft-enabled") {
			this.state.draft.enabled = this.state.draft.enabled ? 0 : 1;
			this.touch();
			this.render_editor();
		} else if (action === "add-members") {
			this.open_member_drawer();
		} else if (action === "add-values") {
			this.open_value_drawer();
		} else if (action === "close-drawer") {
			this.close_drawer();
		} else if (action === "remove-member") {
			this.state.draft.members = this.state.draft.members.filter(
				(member) => member.user !== target.dataset.user
			);
			this.touch();
			this.render_editor();
		} else if (action === "remove-rule") {
			const index = Number(target.dataset.index);
			this.state.draft.rules.splice(index, 1);
			this.state.selected_rule = null;
			this.touch();
			this.render_editor();
		} else if (action === "select-rule") {
			this.state.selected_rule = Number(target.dataset.index);
			this.render_editor();
		} else if (action === "pick-suggest") {
			this.pick_suggest(target.dataset.suggest, target.dataset.value, target.dataset.label || "");
		} else if (action === "add-selected-users") {
			this.add_selected_users();
		} else if (action === "add-role-users") {
			this.add_role_users();
		} else if (action === "pick-doctype") {
			this.pick_doctype(target.dataset.value, Number(target.dataset.tree));
		} else if (action === "add-selected-values") {
			this.add_selected_values();
		} else if (action === "run-preview") {
			this.run_preview();
		}
	}

	on_bind(event) {
		const input = event.currentTarget;
		const bind = input.dataset.bind;
		if (bind === "search" || bind === "value" || bind === "sort") {
			if (bind === "sort") {
				this.state.filters.sort = input.value;
			} else if (bind === "value") {
				this.state.filters.value = input.value;
			} else {
				this.state.filters.search = input.value;
			}
			this.state.offset = 0;
			this.queue_groups();
			return;
		}
		if (bind === "user-query") {
			this.suggest("user", input.value);
			return;
		}
		if (bind === "doctype-query") {
			this.suggest("doctype", input.value);
			return;
		}
		if (bind === "coverage-query") {
			this.state.coverage.query = input.value;
			this.state.coverage_offset = 0;
			this.queue_coverage();
			return;
		}
		if (bind === "coverage-user" || bind === "coverage-group" || bind === "coverage-doctype") {
			const map = {
				"coverage-user": "user",
				"coverage-group": "permission_group",
				"coverage-doctype": "reference_doctype",
			};
			this.state.coverage[map[bind]] = input.value;
			this.state.coverage_offset = 0;
			this.load_coverage();
			return;
		}
		if (bind === "enabled_only" || bind === "defaults_only" || bind === "narrowed_only") {
			this.state.coverage[bind] = input.checked ? 1 : 0;
			this.state.coverage_offset = 0;
			this.load_coverage();
			return;
		}
		if (!this.state.draft) {
			return;
		}
		if (bind === "group_name") {
			this.state.draft.group_name = input.value;
			this.touch();
		} else if (bind === "description") {
			this.state.draft.description = input.value;
			this.touch();
		} else if (bind === "member-query") {
			this.state.member_query = input.value;
			this.render_editor();
			const field = this.body.find("[data-bind='member-query']");
			field.trigger("focus");
			const element = field.get(0);
			if (element) {
				element.setSelectionRange(element.value.length, element.value.length);
			}
		} else if (bind === "rule-query") {
			this.state.rule_query = input.value;
			this.render_editor();
			this.body.find("[data-bind='rule-query']").trigger("focus");
		} else if (bind === "rule-all" || bind === "rule-default" || bind === "rule-hide") {
			this.update_selected_rule(bind, input.checked);
		} else if (bind === "rule-applicable") {
			const rule = this.state.draft.rules[this.state.selected_rule];
			if (rule) {
				rule.applicable_for = input.value.trim();
				rule.apply_to_all_doctypes = 0;
				this.touch();
			}
			this.suggest("applicable", input.value);
		}
	}

	update_selected_rule(bind, checked) {
		const rule = this.state.draft.rules[this.state.selected_rule];
		if (!rule) {
			return;
		}
		if (bind === "rule-all") {
			rule.apply_to_all_doctypes = checked ? 1 : 0;
			if (checked) {
				rule.applicable_for = "";
			}
		} else if (bind === "rule-default") {
			rule.is_default = checked ? 1 : 0;
			if (checked) {
				this.state.draft.rules.forEach((other, index) => {
					if (index !== this.state.selected_rule && other.reference_doctype === rule.reference_doctype) {
						other.is_default = 0;
					}
				});
			}
		} else if (bind === "rule-hide") {
			rule.hide_descendants = checked ? 1 : 0;
		}
		this.touch();
		this.render_editor();
	}

	async suggest(kind, query) {
		const box = this.body.find(`[data-suggest='${kind}']`);
		if (!query) {
			box.attr("hidden", "hidden").empty();
			if (kind === "applicable") {
				const rule = this.state.draft.rules[this.state.selected_rule];
				if (rule) {
					rule.applicable_for = "";
					this.touch();
				}
			}
			return;
		}
		const rows =
			kind === "user"
				? await this.call("search_users", { query, limit: 8 })
				: await this.call("search_doctypes", { query, limit: 8 });
		const html = (rows || [])
			.map((row) => {
				if (kind === "user") {
					return `<button type="button" data-action="pick-suggest" data-suggest="user" data-value="${esc(
						row.name
					)}" data-label="${esc(row.full_name || row.name)}">${esc(row.full_name || row.name)} <span>${esc(
						row.name
					)}</span></button>`;
				}
				const value = row.name;
				return `<button type="button" data-action="pick-suggest" data-suggest="${kind}" data-value="${esc(
					value
				)}">${esc(value)} <span>${esc(row.module || "")}</span></button>`;
			})
			.join("");
		box.html(html || `<div class="fp-suggest-empty">${__("No matches")}</div>`).removeAttr("hidden");
	}

	pick_suggest(kind, value, label) {
		if (kind === "user") {
			this.state.filters.user = value;
			this.state.filters.user_label = label || value;
			this.state.offset = 0;
			this.render_toolbar();
			this.load_groups();
		} else if (kind === "doctype") {
			this.state.filters.reference_doctype = value;
			this.state.offset = 0;
			this.render_toolbar();
			this.load_groups();
		} else if (kind === "applicable") {
			const rule = this.state.draft.rules[this.state.selected_rule];
			if (rule) {
				rule.applicable_for = value;
				rule.apply_to_all_doctypes = 0;
				this.touch();
				this.render_editor();
			}
		}
	}

	set_view(view) {
		if (view === this.state.view) {
			return;
		}
		const go = () => {
			this.state.view = view;
			this.close_drawer();
			if (view === "groups") {
				this.remember(null);
				frappe.set_route("permission-studio");
				this.render();
				this.load_groups();
			} else if (view === "coverage") {
				this.remember(null);
				frappe.set_route("permission-studio");
				this.load_options().then(() => {
					this.render();
					this.load_coverage();
				});
			}
		};
		if (this.state.view === "editor" && this.state.dirty) {
			frappe.confirm(__("Leave without saving this group?"), go);
			return;
		}
		go();
	}

	set_chip(kind, value) {
		if (kind === "preset" && this.state.filters.preset === value) {
			this.state.filters.preset = "all";
		} else {
			this.state.filters[kind] = value;
		}
		this.state.offset = 0;
		this.render_toolbar();
		this.load_groups();
	}

	clear_filter(name) {
		this.state.filters[name] = "";
		if (name === "user") {
			this.state.filters.user_label = "";
		}
		this.state.offset = 0;
		this.render_toolbar();
		this.load_groups();
	}

	turn_page(direction) {
		const next = this.state.offset + direction * this.state.limit;
		if (next < 0 || next >= this.state.total) {
			return;
		}
		this.state.offset = next;
		this.load_groups();
	}

	turn_coverage(direction) {
		const next = this.state.coverage_offset + direction * this.state.coverage_limit;
		if (next < 0 || next >= this.state.coverage_total) {
			return;
		}
		this.state.coverage_offset = next;
		this.load_coverage();
	}

	open_group(name) {
		const go = () => {
			this.close_drawer();
			this.remember(name);
			frappe.set_route("permission-studio", name);
			this.fetch_group(name);
		};
		if (this.state.dirty) {
			frappe.confirm(__("Leave without saving this group?"), go);
			return;
		}
		go();
	}

	toggle_group(name, enabled) {
		const proceed = () => {
			this.call("set_enabled", { name, enabled: enabled ? 1 : 0 }).then(() => this.load_groups());
		};
		if (!enabled) {
			frappe.confirm(
				__(
					"Disabling this group removes its restrictions. Members may see more records until you turn it back on."
				),
				proceed
			);
			return;
		}
		proceed();
	}

	back() {
		const go = () => {
			this.state.dirty = false;
			this.state.draft = null;
			this.set_view("groups");
		};
		if (this.state.dirty) {
			frappe.confirm(__("Leave without saving this group?"), go);
			return;
		}
		go();
	}

	touch() {
		this.state.dirty = true;
		this.state.preview = null;
	}

	payload() {
		const draft = this.state.draft;
		return {
			name: draft.name,
			group_name: (draft.group_name || "").trim(),
			description: draft.description || "",
			enabled: draft.enabled ? 1 : 0,
			modified: draft.modified,
			members: draft.members.map((member) => ({ user: member.user })),
			rules: draft.rules.map((rule) => ({
				reference_doctype: rule.reference_doctype,
				for_value: rule.for_value,
				apply_to_all_doctypes: rule.apply_to_all_doctypes ? 1 : 0,
				applicable_for: rule.apply_to_all_doctypes ? "" : rule.applicable_for || "",
				hide_descendants: rule.hide_descendants ? 1 : 0,
				is_default: rule.is_default ? 1 : 0,
			})),
		};
	}

	async save() {
		if (this.state.saving || !this.state.draft) {
			return;
		}
		if (!(this.state.draft.group_name || "").trim()) {
			frappe.msgprint(__("Enter a group name."));
			return;
		}
		this.state.saving = true;
		this.sync_actions();
		try {
			const result = await this.call("save_group", { payload: this.payload() });
			this.state.draft = result.group;
			this.state.dirty = false;
			this.state.preview = null;
			const sync = result.sync || {};
			frappe.show_alert({
				message: __("Saved. {0} restrictions applied, {1} removed.", [
					String(sync.applied || 0),
					String(sync.removed || 0),
				]),
				indicator: "green",
			});
			this.remember(result.group.name);
			frappe.set_route("permission-studio", result.group.name);
			this.render();
		} finally {
			this.state.saving = false;
			this.sync_actions();
		}
	}

	duplicate() {
		if (!this.state.draft || !this.state.draft.name) {
			return;
		}
		this.call("duplicate_group", { name: this.state.draft.name }).then((result) => {
			frappe.show_alert({ message: __("Group duplicated"), indicator: "green" });
			this.state.dirty = false;
			this.open_group(result.group.name);
		});
	}

	resync() {
		if (!this.state.draft || !this.state.draft.name || this.state.dirty) {
			frappe.msgprint(__("Save the group before reapplying it."));
			return;
		}
		this.call("resync_group", { name: this.state.draft.name }).then((result) => {
			const sync = result.sync || {};
			frappe.show_alert({
				message: __("Reapplied. {0} restrictions are active.", [String(sync.applied || 0)]),
				indicator: "green",
			});
		});
	}

	remove_group() {
		const draft = this.state.draft;
		if (!draft || !draft.name) {
			return;
		}
		frappe.confirm(
			__(
				"Delete {0}? Members will no longer be limited by this group. Role permissions stay as they are.",
				[draft.group_name]
			),
			() => {
				this.call("delete_group", { name: draft.name }).then(() => {
					this.state.dirty = false;
					this.state.draft = null;
					this.set_view("groups");
				});
			}
		);
	}

	open_member_drawer() {
		this.drawer = {
			kind: "members",
			query: "",
			role: "",
			include_disabled: 0,
			results: [],
			selected: {},
		};
		this.render_member_drawer();
		this.refresh_drawer_results();
	}

	render_member_drawer() {
		const drawer = this.drawer;
		this.$drawer.removeAttr("hidden").html(`
			<div class="fp-drawer-backdrop" data-action="close-drawer"></div>
			<aside class="fp-drawer-panel">
				<header>
					<h3>${__("Add members")}</h3>
					<button type="button" data-action="close-drawer" aria-label="${__("Close")}">×</button>
				</header>
				<input type="search" data-drawer="user-query" value="${esc(drawer.query)}" placeholder="${__(
					"Search by name or email"
				)}">
				<div class="fp-drawer-row">
					<input type="search" data-drawer="role-query" value="${esc(drawer.role)}" placeholder="${__(
						"Exact role name"
					)}">
					<label class="fp-check"><input type="checkbox" data-drawer="include-disabled" ${
						drawer.include_disabled ? "checked" : ""
					}> ${__("Include disabled")}</label>
				</div>
				<div class="fp-picks">${this.member_picks_html()}</div>
				<footer>
					<button type="button" class="btn btn-primary btn-sm" data-action="add-selected-users">${__(
						"Add selected"
					)}</button>
					<button type="button" class="btn btn-default btn-sm" data-action="add-role-users">${__(
						"Add everyone with this role"
					)}</button>
				</footer>
			</aside>
		`);
	}

	async refresh_drawer_results() {
		if (!this.drawer || this.drawer.kind !== "members") {
			return;
		}
		this.drawer.results = await this.call("search_users", {
			query: this.drawer.query,
			role: this.drawer.role,
			include_disabled: this.drawer.include_disabled,
			limit: 30,
		});
		const picks = this.$drawer.find(".fp-picks");
		if (!picks.length) {
			this.render_member_drawer();
			return;
		}
		picks.html(this.member_picks_html());
	}

	member_picks_html() {
		const drawer = this.drawer;
		const results = (drawer.results || [])
			.map((user) => {
				const checked = drawer.selected[user.name] ? "checked" : "";
				return `
					<label class="fp-pick">
						<input type="checkbox" data-pick="1" data-value="${esc(user.name)}" data-label="${esc(
							user.full_name || user.name
						)}" ${checked}>
						${avatar(user.name, user.full_name, user.user_image)}
						<span><strong>${esc(user.full_name || user.name)}</strong><em>${esc(user.name)}</em></span>
					</label>`;
			})
			.join("");
		return results || `<p class="fp-muted">${__("No users match.")}</p>`;
	}

	on_drawer_input(event) {
		if (!this.drawer) {
			return;
		}
		const input = event.currentTarget;
		const key = input.dataset.drawer;
		if (this.drawer.kind === "members") {
			if (key === "user-query") {
				this.drawer.query = input.value;
			} else if (key === "role-query") {
				this.drawer.role = input.value;
			} else if (key === "include-disabled") {
				this.drawer.include_disabled = input.checked ? 1 : 0;
			}
			this.queue_drawer();
			return;
		}
		if (key === "doctype-query") {
			this.drawer.doctype_query = input.value;
			this.queue_drawer();
		} else if (key === "value-query") {
			this.drawer.value_query = input.value;
			this.queue_drawer();
		} else if (key === "apply-all") {
			this.drawer.apply_all = input.checked ? 1 : 0;
			this.render_value_drawer();
		} else if (key === "applicable") {
			this.drawer.applicable_for = input.value;
		} else if (key === "hide-descendants") {
			this.drawer.hide_descendants = input.checked ? 1 : 0;
		} else if (key === "is-default") {
			this.drawer.is_default = input.checked ? 1 : 0;
		}
	}

	queue_drawer() {
		if (!this.queue_drawer_search) {
			this.queue_drawer_search = frappe.utils.debounce(() => {
				if (!this.drawer) {
					return;
				}
				if (this.drawer.kind === "members") {
					this.refresh_drawer_results();
				} else {
					this.refresh_value_drawer();
				}
			}, 200);
		}
		this.queue_drawer_search();
	}

	on_pick(event) {
		if (!this.drawer) {
			return;
		}
		const input = event.currentTarget;
		const value = input.dataset.value;
		if (input.checked) {
			this.drawer.selected[value] = input.dataset.label || value;
		} else {
			delete this.drawer.selected[value];
		}
	}

	add_selected_users() {
		const existing = new Set(this.state.draft.members.map((member) => member.user));
		Object.keys(this.drawer.selected).forEach((user) => {
			if (existing.has(user)) {
				return;
			}
			const row = (this.drawer.results || []).find((item) => item.name === user) || {};
			this.state.draft.members.push({
				user,
				full_name: row.full_name || this.drawer.selected[user] || user,
				user_image: row.user_image,
				enabled: row.enabled == null ? 1 : row.enabled,
			});
		});
		this.touch();
		this.close_drawer();
		this.render_editor();
	}

	async add_role_users() {
		const role = (this.drawer.role || "").trim();
		if (!role) {
			frappe.msgprint(__("Enter a role first."));
			return;
		}
		const users = await this.call("search_users", { role, limit: 200, query: this.drawer.query });
		const existing = new Set(this.state.draft.members.map((member) => member.user));
		(users || []).forEach((user) => {
			if (!existing.has(user.name)) {
				this.state.draft.members.push({
					user: user.name,
					full_name: user.full_name || user.name,
					user_image: user.user_image,
					enabled: user.enabled,
				});
			}
		});
		if ((users || []).length >= 200) {
			frappe.show_alert({
				message: __("Added the first 200 users with this role."),
				indicator: "orange",
			});
		}
		this.touch();
		this.close_drawer();
		this.render_editor();
	}

	open_value_drawer() {
		this.drawer = {
			kind: "values",
			doctype_query: "",
			value_query: "",
			doctypes: [],
			values: [],
			selected: {},
			doctype: null,
			apply_all: 1,
			applicable_for: "",
			hide_descendants: 0,
			is_default: 0,
		};
		this.render_value_drawer();
		this.refresh_value_drawer();
	}

	doctype_picks_html() {
		const drawer = this.drawer;
		const doctypes = (drawer.doctypes || [])
			.map(
				(row) => `
				<button type="button" class="fp-doctype-pick ${
					drawer.doctype && drawer.doctype.name === row.name ? "is-selected" : ""
				}" data-action="pick-doctype" data-value="${esc(row.name)}" data-tree="${row.is_tree ? 1 : 0}">
					<span class="fp-swatch" style="--hue:${hue(row.name)}"></span>
					<strong>${esc(row.name)}</strong>
					<em>${esc(row.module || "")}</em>
				</button>`
			)
			.join("");
		return doctypes || `<p class="fp-muted">${__("No DocTypes match.")}</p>`;
	}

	value_picks_html() {
		const drawer = this.drawer;
		if (!drawer.doctype) {
			return `<p class="fp-muted">${__("Pick a DocType to browse its records.")}</p>`;
		}
		const values = (drawer.values || [])
			.map((row) => {
				const checked = drawer.selected[row.value] ? "checked" : "";
				return `
					<label class="fp-pick">
						<input type="checkbox" data-pick="1" data-value="${esc(row.value)}" data-label="${esc(
							row.description || row.value
						)}" ${checked}>
						<span><strong>${esc(row.description || row.value)}</strong>${
							row.description ? `<em>${esc(row.value)}</em>` : ""
						}</span>
					</label>`;
			})
			.join("");
		return values || `<p class="fp-muted">${__("No records match.")}</p>`;
	}

	render_value_drawer() {
		const drawer = this.drawer;
		this.$drawer.removeAttr("hidden").html(`
			<div class="fp-drawer-backdrop" data-action="close-drawer"></div>
			<aside class="fp-drawer-panel fp-drawer-wide">
				<header>
					<h3>${__("Add records")}</h3>
					<button type="button" data-action="close-drawer" aria-label="${__("Close")}">×</button>
				</header>
				<div class="fp-drawer-split">
					<div>
						<input type="search" data-drawer="doctype-query" value="${esc(
							drawer.doctype_query
						)}" placeholder="${__("Search DocTypes")}">
						<div class="fp-picks">${this.doctype_picks_html()}</div>
					</div>
					<div>
						<input type="search" data-drawer="value-query" value="${esc(
							drawer.value_query
						)}" placeholder="${drawer.doctype ? __("Search {0}", [drawer.doctype.name]) : __("Choose a DocType")}">
						<div class="fp-picks">${this.value_picks_html()}</div>
					</div>
				</div>
				<div class="fp-drawer-options">
					<label class="fp-check"><input type="checkbox" data-drawer="apply-all" ${
						drawer.apply_all ? "checked" : ""
					}> ${__("Apply to all document types")}</label>
					${
						drawer.apply_all
							? ""
							: `<input type="search" data-drawer="applicable" value="${esc(
									drawer.applicable_for
								)}" placeholder="${__("Applicable For DocType")}">`
					}
					<label class="fp-check"><input type="checkbox" data-drawer="is-default" ${
						drawer.is_default ? "checked" : ""
					}> ${__("Make the first value the default")}</label>
					${
						drawer.doctype && drawer.doctype.is_tree
							? `<label class="fp-check"><input type="checkbox" data-drawer="hide-descendants" ${
									drawer.hide_descendants ? "checked" : ""
								}> ${__("Hide descendant records")}</label>`
							: ""
					}
				</div>
				<footer>
					<button type="button" class="btn btn-primary btn-sm" data-action="add-selected-values">${__(
						"Add selected"
					)}</button>
				</footer>
			</aside>
		`);
	}

	async refresh_value_drawer() {
		if (!this.drawer || this.drawer.kind !== "values") {
			return;
		}
		this.drawer.doctypes = await this.call("search_doctypes", {
			query: this.drawer.doctype_query,
			limit: 20,
		});
		if (this.drawer.doctype) {
			this.drawer.values = await this.call("search_values", {
				doctype: this.drawer.doctype.name,
				query: this.drawer.value_query,
				limit: 30,
			});
		}
		const picks = this.$drawer.find(".fp-drawer-split .fp-picks");
		if (picks.length < 2) {
			this.render_value_drawer();
			return;
		}
		picks.eq(0).html(this.doctype_picks_html());
		picks.eq(1).html(this.value_picks_html());
	}

	async pick_doctype(name, isTree) {
		this.drawer.doctype = { name, is_tree: isTree ? 1 : 0 };
		this.drawer.selected = {};
		this.drawer.values = await this.call("search_values", {
			doctype: name,
			query: this.drawer.value_query,
			limit: 30,
		});
		const info = await this.call("get_doctype_info", { doctype: name });
		this.drawer.doctype.is_tree = info.is_tree;
		this.render_value_drawer();
	}

	add_selected_values() {
		const drawer = this.drawer;
		if (!drawer.doctype) {
			frappe.msgprint(__("Choose a DocType."));
			return;
		}
		if (!drawer.apply_all && !(drawer.applicable_for || "").trim()) {
			frappe.msgprint(__("Choose the DocType this limit applies to, or apply it everywhere."));
			return;
		}
		const keys = new Set(
			this.state.draft.rules.map(
				(rule) =>
					`${rule.reference_doctype}::${rule.for_value}::${rule.applicable_for || ""}::${
						rule.apply_to_all_doctypes ? 1 : 0
					}`
			)
		);
		let usedDefault = this.state.draft.rules.some(
			(rule) => rule.reference_doctype === drawer.doctype.name && rule.is_default
		);
		Object.keys(drawer.selected).forEach((value) => {
			const applyAll = drawer.apply_all ? 1 : 0;
			const applicable = applyAll ? "" : (drawer.applicable_for || "").trim();
			const key = `${drawer.doctype.name}::${value}::${applicable}::${applyAll}`;
			if (keys.has(key)) {
				return;
			}
			const isDefault = drawer.is_default && !usedDefault ? 1 : 0;
			if (isDefault) {
				usedDefault = true;
			}
			this.state.draft.rules.push({
				reference_doctype: drawer.doctype.name,
				for_value: value,
				value_label: drawer.selected[value] || value,
				apply_to_all_doctypes: applyAll,
				applicable_for: applicable,
				hide_descendants: drawer.doctype.is_tree ? drawer.hide_descendants : 0,
				is_default: isDefault,
				is_tree: drawer.doctype.is_tree ? 1 : 0,
			});
		});
		this.touch();
		this.close_drawer();
		this.state.tab = "permissions";
		this.render_editor();
	}

	close_drawer() {
		this.drawer = null;
		this.$drawer.attr("hidden", "hidden").empty();
	}
};

function esc(value) {
	return frappe.utils.escape_html(value == null ? "" : String(value));
}

function option(value, label, current) {
	return `<option value="${esc(value)}" ${value === current ? "selected" : ""}>${esc(label)}</option>`;
}

function chip(action, value, label, current) {
	return `<button type="button" class="fp-filter ${current === value ? "is-active" : ""}" data-action="${action}" data-value="${esc(
		value
	)}">${esc(label)}</button>`;
}

function hue(text) {
	let hash = 0;
	const source = text || "";
	for (let index = 0; index < source.length; index++) {
		hash = (hash * 31 + source.charCodeAt(index)) % 360;
	}
	return hash;
}

function initials(name) {
	const parts = String(name || "?")
		.trim()
		.split(/\s+/)
		.slice(0, 2);
	return parts.map((part) => part.charAt(0)).join("").toUpperCase() || "?";
}

function safe_image(url) {
	const value = String(url || "");
	if (
		value.startsWith("/files/") ||
		value.startsWith("/private/files/") ||
		value.startsWith("https://") ||
		value.startsWith("http://")
	) {
		return value;
	}
	return "";
}

function avatar(user, fullName, image) {
	const src = safe_image(image);
	if (src) {
		return `<img class="fp-avatar" alt="" src="${esc(src)}">`;
	}
	return `<span class="fp-avatar fp-initials" style="--hue:${hue(user)}">${esc(
		initials(fullName || user)
	)}</span>`;
}
