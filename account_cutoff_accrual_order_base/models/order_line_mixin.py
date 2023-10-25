# Copyright 2013 Alexis de Lattre (Akretion) <alexis.delattre@akretion.com>
# Copyright 2018 Jacques-Etienne Baudoux (BCIM) <je@bcim.be>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

import logging

from odoo import Command, _, api, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class OrderLineCutoffAccrualMixin(models.AbstractModel):
    _name = "order.line.cutoff.accrual.mixin"
    _description = "Cutoff Accrual Order Line Mixin"

    def _get_cutoff_accrual_partner(self):
        self.ensure_one()
        return self.order_id.partner_id

    def _get_cutoff_accrual_fiscal_position(self):
        self.ensure_one()
        return self.order_id.fiscal_position_id

    def _get_cutoff_accrual_product(self):
        self.ensure_one()
        return self.product_id

    def _get_cutoff_accrual_product_qty(self):
        return self.product_qty

    def _get_cutoff_accrual_price_unit(self):
        self.ensure_one()
        product_qty = self._get_cutoff_accrual_product_qty()
        if product_qty:
            return self.price_subtotal / product_qty
        return 0

    def _get_cutoff_accrual_invoice_lines(self):
        self.ensure_one()
        return self.invoice_lines

    def _get_cutoff_accrual_invoiced_quantity(self, cutoff):
        self.ensure_one()
        cutoff_nextday = cutoff._nextday_start_dt()
        invoiced_qty = sum(
            line.quantity
            * (-1 if line.move_id.move_type in ("in_refund", "out_refund") else 1)
            for line in self._get_cutoff_accrual_invoice_lines()
            if (
                line.move_id.state == "posted"
                and line.move_id.date <= cutoff.cutoff_date
            )
            or (
                line.move_id.state == "draft"
                and line.move_id.move_type == "in_refund"
                and line.move_id.create_date < cutoff_nextday
            )
        )
        return invoiced_qty

    def _get_cutoff_accrual_line_invoiced_after(self, cutoff):
        """Return order lines"""
        return NotImplemented()

    def _get_cutoff_accrual_line_delivered_after(self, cutoff):
        """Return order lines"""
        return self.browse()

    def _get_cutoff_accrual_delivered_quantity(self, cutoff):
        return NotImplemented()

    def _get_cutoff_accrual_delivered_min_date(self):
        """Return first delivery date"""
        return

    def _get_cutoff_accrual_taxes(self, cutoff, quantity):
        self.ensure_one()
        if cutoff.cutoff_type == "accrued_revenue":
            tax_account_field_name = "account_accrued_revenue_id"
            tax_account_field_label = "Accrued Revenue Tax Account"
            sign = 1
        elif cutoff.cutoff_type == "accrued_expense":
            tax_account_field_name = "account_accrued_expense_id"
            tax_account_field_label = "Accrued Expense Tax Account"
            sign = -1
        else:
            return
        tax_line_ids = [Command.clear()]
        base_line = self._convert_to_tax_base_line_dict()
        base_line["quantity"] = quantity
        tax_info = self.env["account.tax"]._compute_taxes([base_line])
        for tax_line in tax_info["tax_lines_to_add"]:
            amount = tax_line["tax_amount"] * sign
            if cutoff.company_currency_id != self.currency_id:
                currency_at_date = self.currency_id.with_context(
                    date=self.parent_id.cutoff_date
                )
                tax_cutoff_amount = currency_at_date.compute(
                    amount, cutoff.company_currency_id
                )
            else:
                tax_cutoff_amount = amount
            tax = self.env["account.tax"].browse(tax_line["tax_id"])
            tax_cutoff_account_id = tax[tax_account_field_name]
            if not tax_cutoff_account_id:
                raise UserError(
                    _(
                        "Error: Missing '%(label)s' on tax '%(name)s'.",
                        label=tax_account_field_label,
                        name=tax.display_name,
                    )
                )
            tax_line_ids.append(
                Command.create(
                    {
                        "tax_id": tax_line["tax_id"],
                        "base": tax_line["base_amount"],
                        "amount": amount,
                        "cutoff_account_id": tax_cutoff_account_id.id,
                        "cutoff_amount": tax_cutoff_amount,
                    },
                )
            )
        return tax_line_ids

    @api.model
    def _get_cutoff_accrual_lines_query(self):
        domain = []
        if self.env.company.cutoff_exclude_locked_orders:
            domain.append(("order_id.state", "not in", ("cancel", "done")))
        else:
            domain.append(("order_id.state", "!=", "cancel"))
        self._flush_search(domain)
        query = self._where_calc(domain)
        self._apply_ir_rules(query, "read")
        return query

    def _prepare_cutoff_accrual_line(self, cutoff):
        """
        Calculate accrual using order line
        """
        self.ensure_one()
        if cutoff.cutoff_type not in ("accrued_expense", "accrued_revenue"):
            return UserError(_("Wrong cutoff type %s") % cutoff.cutoff_type)
        price_unit = self._get_cutoff_accrual_price_unit()
        if not price_unit:
            return {}
        fpos = self._get_cutoff_accrual_fiscal_position()
        account = cutoff._get_product_account(self.product_id, fpos)
        cutoff_account_id = cutoff._get_mapping_dict().get(account.id, account.id)
        res = {
            "parent_id": cutoff.id,
            "partner_id": self._get_cutoff_accrual_partner().id,
            "name": self.name,
            "account_id": account.id,
            "cutoff_account_id": cutoff_account_id,
            "analytic_distribution": self.analytic_distribution,
            "currency_id": self.currency_id.id,
            "product_id": self._get_cutoff_accrual_product().id,
            "price_unit": price_unit,
        }
        delivered_qty = self._get_cutoff_accrual_delivered_quantity(cutoff)
        invoiced_qty = self._get_cutoff_accrual_invoiced_quantity(cutoff)
        if delivered_qty == invoiced_qty:
            return {}
        res["received_qty"] = delivered_qty
        res["invoiced_qty"] = invoiced_qty
        quantity = delivered_qty - invoiced_qty
        if self.env.company.accrual_taxes:
            res["tax_line_ids"] = self._get_cutoff_accrual_taxes(cutoff, quantity)
        return res

    def _cron_cutoff_accrual(self):
        return NotImplemented()
