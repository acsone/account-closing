# Copyright 2018 Jacques-Etienne Baudoux (BCIM) <je@bcim.be>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import _, models
from odoo.exceptions import UserError


class AccountMove(models.Model):
    _inherit = "account.move"

    def _post(self, soft=True):
        res = super()._post(soft=soft)
        self._update_cutoff_accrual_order()
        return res

    def unlink(self):
        # In case the invoice was posted, we need to check any affected cutoff
        self._update_cutoff_accrual_order()
        return super().unlink()

    def _get_cutoff_accrual_order_lines(self):
        """Return a list of order lines to process"""
        self.ensure_one()
        return []

    def _update_cutoff_accrual_order(self):
        for move in self:
            if not move.is_invoice():
                continue
            for model_order_lines in move._get_cutoff_accrual_order_lines():
                for order_line in model_order_lines:
                    self._update_cutoff_accrual_order_line(order_line)

    def _update_cutoff_accrual_order_line(self, order_line):
        order_line.ensure_one()
        if (
            order_line.order_id.state == "done"
            and self.env.company.cutoff_exclude_locked_orders
        ):
            return
        order_line.account_cutoff_line_ids.invalidate_recordset(["invoice_line_ids"])
        for cutoff_line in order_line.account_cutoff_line_ids:
            cutoff = cutoff_line.parent_id
            invoiced_qty = (
                cutoff_line._get_order_line()._get_cutoff_accrual_invoiced_quantity(
                    cutoff
                )
            )
            if cutoff.state == "done" and invoiced_qty != cutoff_line.invoiced_qty:
                raise UserError(
                    _(
                        "You cannot validate an invoice for an accounting date "
                        "that modifies a closed cutoff (i.e. for which an "
                        "accounting entry has already been created).\n"
                        " - Cut-off: {cutoff}\n"
                        " - Product: {product}\n"
                        " - Previous invoiced quantity: {prev_inv_qty}\n"
                        " - New invoiced quantity: {new_inv_qty}"
                    ).format(
                        cutoff=cutoff.display_name,
                        product=cutoff_line.product_id.display_name,
                        prev_inv_qty=cutoff_line.invoiced_qty,
                        new_inv_qty=invoiced_qty,
                    )
                )
            cutoff_line.invoiced_qty = invoiced_qty
        # search missing cutoff entries - start at first reception
        delivery_min_date = order_line._get_cutoff_accrual_delivered_min_date()
        if delivery_min_date:
            date = min(delivery_min_date, self.date)
        else:
            date = self.date
        cutoffs = self.env["account.cutoff"].search(
            [
                ("cutoff_date", ">=", date),
                (
                    "id",
                    "not in",
                    order_line.account_cutoff_line_ids.parent_id.ids,
                ),
                ("cutoff_type", "in", ("accrued_expense", "accrued_revenue")),
            ]
        )
        values = []
        for cutoff in cutoffs:
            data = order_line._prepare_cutoff_accrual_line(cutoff)
            if not data:
                continue
            if cutoff.state == "done":
                raise UserError(
                    _(
                        "You cannot validate an invoice for an accounting date "
                        "that generates an entry in a closed cut-off (i.e. for "
                        "which an accounting entry has already been created).\n"
                        " - Cut-off: {cutoff}\n"
                        " - Product: {product}\n"
                    ).format(
                        cutoff=cutoff.display_name,
                        product=order_line.product_id.display_name,
                    )
                )
            values.append(data)
        self.env["account.cutoff.line"].create(values)
