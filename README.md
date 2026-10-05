# Frappe Hero

Graphical permission groups for [Frappe](https://frappeframework.com). Group users, then choose the DocTypes and record values they are allowed to see.

Permission Studio writes standard **User Permission** records, so the limits apply everywhere in the desk: lists, links, and reports. It does not grant roles. Roles still decide which documents someone can open and what they can do.

Adding **Company → Acme** means those members only see Acme, not every company. Turning a group off, or deleting it, removes the User Permissions that group created. Members may then see more records. A User Permission that already existed is left in place.

## Install

From your bench:

```bash
bench get-app https://github.com/agilasoft/frappehero
bench --site your-site install-app frappehero
bench --site your-site migrate
bench build --app frappehero
```

Open **Permission Studio** from the desk search, the Frappe Hero workspace, or `/desk/permission-studio`.

On Frappe 15 the desk lives under `/app`, so the page is `/app/permission-studio`. The same workspace and awesome bar entry work there.

Requires Frappe 15 or 16. Only **System Manager** can open the studio.

## Use it

1. Create a group and give it a name.
2. Add members one by one, or everyone who has a role.
3. Add records: pick a DocType, search its values, and add the ones members may see.
4. Save. Frappe Hero creates one User Permission per member and value.

Useful filters on the group list:

- Search across group name, description, member, and value
- Active, disabled, mine, or incomplete (no members or no values)
- User, DocType, and value
- Sort by recent, name, members, or values

**Coverage** lists every user, group, DocType, and value in one table. Filter by user, group, DocType, defaults only, or limits that apply to a single DocType. The same view is available as the **Permission Coverage** report.

Inside a group:

- Filter the member list and the record list
- Mark a value as the default for new documents
- Apply a value only while working in one DocType
- Hide descendant records for tree DocTypes such as Company or Territory
- Preview the combined limits from this group and the member's other groups

The standard Permission Group form is still there if you prefer a document. It has the same rules and a button back to the studio.

## What gets stored

| DocType | Purpose |
| --- | --- |
| Permission Group | Members and the values they may see |
| Permission Group Grant | Which group is responsible for each User Permission |
| User Permission | The restriction Frappe enforces. Frappe Hero marks the rows it owns |

Two groups that allow the same value share one User Permission. It is removed only when the last group stops granting it.

## Tests

Rule checks that do not need a site:

```bash
python -m unittest frappehero.permission_studio.test_normalize
```

On a site with the app installed:

```bash
bench --site your-site run-tests --app frappehero
```

## License

MIT. Copyright (c) 2026 Agilasoft Cloud Technologies.
