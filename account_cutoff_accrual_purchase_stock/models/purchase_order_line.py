# Copyright 2018 Jacques-Etienne Baudoux (BCIM sprl) <je@bcim.be>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import logging

from odoo import models

_logger = logging.getLogger(__name__)


class PurchaseOrderLine(models.Model):
    _name = "purchase.order.line"
    _inherit = ["purchase.order.line"]

    def _get_cutoff_accrual_lines_delivered_after(self, cutoff):
        lines = super()._get_cutoff_accrual_lines_delivered_after(cutoff)
        cutoff_nextday = cutoff._nextday_start_dt()
        # Take all moves done after the cutoff date
        moves_after = self.env["stock.move"].search(
            [
                ("state", "=", "done"),
                ("date", ">=", cutoff_nextday),
                ("purchase_line_id", "!=", False),
            ],
            order="id",
        )
        _logger.debug("Moves done after cutoff: %s" % len(moves_after))
        purchase_ids = set(moves_after.purchase_line_id.order_id.ids)
        purchases = self.env["purchase.order"].browse(purchase_ids)
        lines |= purchases.order_line
        return lines

    def _get_cutoff_accrual_delivered_min_date(self):
        """Return first delivery date"""
        self.ensure_one()
        stock_moves = self.move_ids.filtered(lambda m: m.state == "done")
        if not stock_moves:
            return
        return min(stock_moves.mapped("date")).date()

    def _get_cutoff_accrual_delivered_quantity(self, cutoff):
        self.ensure_one()
        received_qty = super()._get_cutoff_accrual_delivered_quantity(cutoff)
        # The quantity received on the PO line must be deducted from all
        # moves done after the cutoff date.
        cutoff_nextday = cutoff._nextday_start_dt()
        moves_after = self.move_ids
        for move in moves_after:
            if move.state != "done":
                continue
            if move.date < cutoff_nextday:
                continue
            if move.picking_code not in ("incoming" or "outgoing"):
                continue
            sign = 1 if move.picking_code == "incoming" else -1
            if move.product_uom != self.product_uom:
                received_qty -= sign * move.product_uom._compute_quantity(
                    move.product_uom_qty, self.product_uom
                )
            else:
                received_qty -= sign * move.product_uom_qty
        return received_qty
