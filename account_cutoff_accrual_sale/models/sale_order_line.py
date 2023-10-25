# Copyright 2018 Jacques-Etienne Baudoux (BCIM sprl) <je@bcim.be>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class SaleOrderLine(models.Model):
    _name = "sale.order.line"
    _inherit = ["sale.order.line", "order.line.cutoff.accrual.mixin"]

    account_cutoff_line_ids = fields.One2many(
        "account.cutoff.line",
        "sale_line_id",
        string="Account Cutoff Lines",
        readonly=True,
    )

    def _get_cutoff_accrual_partner(self):
        return self.order_id.partner_invoice_id

    def _get_cutoff_accrual_product_qty(self):
        return self.product_uom_qty

    @api.model
    def _get_cutoff_accrual_lines_query(self):
        query = super()._get_cutoff_accrual_lines_query()
        self.flush_model(["display_type", "qty_delivered", "qty_invoiced"])
        query.add_where(
            f'"{self._table}".display_type IS NULL AND '
            f'"{self._table}".qty_delivered != "{self._table}".qty_invoiced'
        )
        return query

    def _prepare_cutoff_accrual_line(self, cutoff):
        res = super()._prepare_cutoff_accrual_line(cutoff)
        if not res:
            return
        res["sale_line_id"] = self.id
        return res

    def _get_cutoff_accrual_lines_invoiced_after(self, cutoff):
        cutoff_nextday = cutoff._nextday_start_dt()
        # Take all invoices impacting the cutoff
        # FIXME: what about ("move_id.payment_state", "=", "invoicing_legacy")
        domain = [
            ("move_id.move_type", "in", ("out_invoice", "out_refund")),
            ("sale_line_ids", "!=", False),
            "|",
            ("move_id.state", "=", "draft"),
            "&",
            ("move_id.state", "=", "posted"),
            ("move_id.date", ">=", cutoff_nextday),
        ]
        if self.env.company.cutoff_exclude_locked_orders:
            domain += [("sale_line_ids.order_id.state", "!=", "done")]
        invoice_line_after = self.env["account.move.line"].search(domain, order="id")
        _logger.debug(
            "Sales Invoice Lines done after cutoff: %s" % len(invoice_line_after)
        )
        sale_ids = set(invoice_line_after.sale_line_ids.order_id.ids)
        sales = self.env["sale.order"].browse(sale_ids)
        return sales.order_line

    def _get_cutoff_accrual_lines_delivered_after(self, cutoff):
        # FIXME sale_stock
        cutoff_nextday = cutoff._nextday_start_dt()
        # Take all moves done after the cutoff date
        moves_after = self.env["stock.move"].search(
            [
                ("state", "=", "done"),
                ("date", ">=", cutoff_nextday),
                ("sale_line_id", "!=", False),
            ],
            order="id",
        )
        sale_ids = set(moves_after.sale_line_id.order_id.ids)
        sales = self.env["sale.order"].browse(sale_ids)
        return sales.order_line

    def _get_cutoff_accrual_delivered_quantity(self, cutoff):
        self.ensure_one()
        return self.qty_delivered

    @api.model
    def _cron_cutoff_accrual(self):
        self._cron_cutoff("accrued_revenue", self._model)
