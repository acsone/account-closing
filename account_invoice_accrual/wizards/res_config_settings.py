# Copyright 2023 ACSONE SA/NV
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class ResConfigSettings(models.TransientModel):

    _inherit = "res.config.settings"

    default_accrual_revenue_journal_id = fields.Many2one(
        related="company_id.default_accrual_revenue_journal_id",
    )
    default_accrual_expense_journal_id = fields.Many2one(
        related="company_id.default_accrual_expense_journal_id",
    )
