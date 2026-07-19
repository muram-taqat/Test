# Copyright 2026 TAQAT Trading And Business Solutions
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
"""Pre-migration for base_tier_validation v17.0.4.0.0.

Drops the stale ir_model_data + underlying records that were removed when the
``allow_to_delegate`` feature came out in v17.0.4.0.0:

Direct ``base_tier_validation`` removals:

* ir.ui.view ``base_tier_validation.tier_setting_view_form`` — the settings form
  view that exposed the ``allow_to_delegate`` toggle.
* ir.model.fields ``base_tier_validation.field_res_config_settings__allow_to_delegate``
  — the Boolean field itself. The strict view validator in Odoo 17 refuses to
  load the registry if any view (including stale ones) references a non-existent
  field, so the field cleanup MUST happen before XML data load.
* ir.ui.menu ``base_tier_validation.menu_tier_setting`` — the settings menu entry.
* ir.model.access ``base_tier_validation.access_tier_definition_settings`` — the
  ACL row that paired with the removed view.

Cross-module orphan cleanup (downstream of the same feature removal):

* res.groups ``base_tier_validation.delegation_requests_user`` /
  ``delegation_requests_administrator`` are auto-unlinked by Odoo at end of
  module update because the new manifest no longer ships them. They are
  referenced by orphan ir.model.access rows under the non-existent
  ``access_tier`` module (xml_ids ``access_tier.definition.filter`` /
  ``access_tier.tag``). Those FK references block the group unlink with::

      ForeignKeyViolation: ir_model_access_group_id_fkey

  We drop any orphan ``access_tier``-prefixed ir.model.access rows here so the
  end-of-update group cleanup succeeds.

Without these cleanups, any DB sitting on a pre-v4 ``base_tier_validation``
version fails registry load with the ParseError above, then on a re-run with
fixes fails again with the FK violation. Both manifest the same root cause:
v17.0.4.0.0 removed a feature without a migration to clean up its DB footprint.

Idempotent: each ir_model_data lookup is a no-op when the row is already gone
(fresh-on-v4 installs land here with nothing to delete).
"""
from openupgradelib import openupgrade

STALE_XML_IDS = (
    "base_tier_validation.tier_setting_view_form",
    "base_tier_validation.menu_tier_setting",
    "base_tier_validation.access_tier_definition_settings",
    "base_tier_validation.field_res_config_settings__allow_to_delegate",
)

# Orphan ACL records owned by the non-existent ``access_tier`` module that
# reference soon-to-be-deleted base_tier_validation groups.
ORPHAN_MODULES = ("access_tier",)


@openupgrade.migrate()
def migrate(env, version):
    # 1. Direct base_tier_validation stale records.
    for xmlid in STALE_XML_IDS:
        module, name = xmlid.split(".", 1)
        env.cr.execute(
            "SELECT id, res_id, model FROM ir_model_data WHERE module=%s AND name=%s",
            (module, name),
        )
        row = env.cr.fetchone()
        if not row:
            continue
        imd_id, res_id, model = row
        if model and res_id:
            table = model.replace(".", "_")
            env.cr.execute(
                "DELETE FROM %s WHERE id = %%s" % table,
                (res_id,),
            )
        env.cr.execute("DELETE FROM ir_model_data WHERE id = %s", (imd_id,))

    # 2. Orphan ir.model.access rows from non-existent modules (e.g. access_tier)
    # that reference base_tier_validation groups, so the end-of-update group
    # unlink can succeed without FK violations.
    for module in ORPHAN_MODULES:
        env.cr.execute(
            """
            SELECT imd.id AS imd_id, imd.res_id, imd.model
            FROM ir_model_data imd
            WHERE imd.module = %s AND imd.model = 'ir.model.access'
            """,
            (module,),
        )
        for imd_id, res_id, model in env.cr.fetchall():
            if model and res_id:
                table = model.replace(".", "_")
                env.cr.execute(
                    "DELETE FROM %s WHERE id = %%s" % table,
                    (res_id,),
                )
            env.cr.execute("DELETE FROM ir_model_data WHERE id = %s", (imd_id,))
