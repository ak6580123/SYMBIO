"""Three roles, one table, and no inheritance (§3).

The whole permission system is this file plus the tenant scope in
`db/repositories.py`. A role is a name; a permission is a verb the endpoint needs.
Anything that would need a fourth concept - delegated access, per-field rules,
time-boxed grants - is not in this product, and the table is small enough that a
reviewer can read all of it in one screen, which is worth more here than a framework.

Two rules that are not negotiable:

* Reading is scoped by organisation first and by role second. A viewer may see
  everything in *their* tenant and nothing in another; that is the repositories' job,
  not this file's.
* Nothing in here can grant a capability the deterministic layers refuse. A role can
  let someone publish a listing; it cannot let them mark their own organisation
  verified, override a safety gate or change a score.
"""

from __future__ import annotations

ROLE_ADMIN = "organization_admin"
ROLE_OPERATOR = "operator"
ROLE_VIEWER = "viewer"

ROLES: dict[str, dict[str, str]] = {
    ROLE_ADMIN: {"label": "Administrator", "summary": "Runs the organisation: profile, listings, members."},
    ROLE_OPERATOR: {"label": "Operator", "summary": "Works the material: runs analyses and keeps listings current."},
    ROLE_VIEWER: {"label": "Viewer", "summary": "Reads the organisation's data and changes nothing."},
}

# action -> roles allowed to perform it
PERMISSIONS: dict[str, tuple[str, ...]] = {
    "edit_organization": (ROLE_ADMIN,),
    "edit_profile": (ROLE_ADMIN,),
    "manage_members": (ROLE_ADMIN,),
    "edit_facility": (ROLE_ADMIN, ROLE_OPERATOR),
    "publish_listing": (ROLE_ADMIN, ROLE_OPERATOR),
    "edit_listing": (ROLE_ADMIN, ROLE_OPERATOR),
    "deactivate_listing": (ROLE_ADMIN, ROLE_OPERATOR),
    "run_analysis": (ROLE_ADMIN, ROLE_OPERATOR),
    "save_analysis": (ROLE_ADMIN, ROLE_OPERATOR),
    "view_analyses": (ROLE_ADMIN, ROLE_OPERATOR, ROLE_VIEWER),
    "view_organization": (ROLE_ADMIN, ROLE_OPERATOR, ROLE_VIEWER),
}


def can(role: str, action: str) -> bool:
    return role in PERMISSIONS.get(action, ())


def allowed_roles(action: str) -> tuple[str, ...]:
    return PERMISSIONS.get(action, ())


def describe() -> list[dict[str, object]]:
    """For `/api/org/permissions` and for the tests that keep this table honest."""
    return [
        {
            "action": action,
            "roles": sorted(roles),
            "labels": [ROLES[role]["label"] for role in sorted(roles)],
        }
        for action, roles in sorted(PERMISSIONS.items())
    ]
