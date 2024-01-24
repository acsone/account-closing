# Copyright 2018 Jacques-Etienne Baudoux (BCIM) <je@bcim.be>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo import api, fields, models


class AccountCutoffLine(models.Model):
    _inherit = "account.cutoff.line"

    sale_line_id = fields.Many2one(
        comodel_name="sale.order.line", string="Sales Order Line", readonly=True
    )
    sale_order_id = fields.Many2one(related="sale_line_id.order_id")

    def _get_order_line(self):
        if self.sale_line_id:
            return self.sale_line_id
        return super()._get_order_line()

    @api.depends("sale_line_id")
    def _compute_invoice_lines(self):
        for rec in self:
            if rec.sale_line_id:
                rec.invoice_line_ids = rec.sale_line_id.invoice_lines
        super()._compute_invoice_lines()
        return

    @api.depends("invoiced_qty", "received_qty")
    def _compute_quantity(self):
        on_order = self.filtered(
            lambda rec: rec.parent_id.order_line_model
            and rec.sale_line_id
            and rec.product_id.invoice_policy == "order"
        )
        for rec in on_order:
            rec.quantity = rec.sale_line_id.product_uom_qty - rec.invoiced_qty
        other = self - on_order
        if other:
            super(AccountCutoffLine, other)._compute_quantity()
        return
