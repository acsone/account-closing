# Copyright 2018 Jacques-Etienne Baudoux (BCIM) <je@bcim.be>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo import Command, fields

from odoo.addons.account_cutoff_accrual_order_base.tests.common import (
    TestAccountCutoffAccrualOrderCommon,
)


class TestAccountCutoffAccrualSaleCommon(TestAccountCutoffAccrualOrderCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.tax_sale = cls.env.company.account_sale_tax_id
        cls.cutoff_account = cls.env["account.account"].create(
            {
                "name": "account accrued revenue",
                "code": "accountAccruedExpense",
                "account_type": "asset_current",
                "company_id": cls.env.company.id,
            }
        )
        cls.tax_sale.account_accrued_revenue_id = cls.cutoff_account
        # Removing all existing SO
        cls.env.cr.execute("DELETE FROM sale_order;")
        # Create SO
        cls.so = cls.env["sale.order"].create(
            {
                "partner_id": cls.partner.id,
                "partner_invoice_id": cls.partner.id,
                "partner_shipping_id": cls.partner.id,
                "order_line": [
                    Command.create(
                        {
                            "name": p.name,
                            "product_id": p.id,
                            "product_uom_qty": 5,
                            "product_uom": p.uom_id.id,
                            "price_unit": 100,
                            "analytic_distribution": {
                                str(cls.analytic_account.id): 100.0
                            },
                            "tax_id": [Command.set(cls.tax_sale.ids)],
                        },
                    )
                    for p in cls.products
                ],
                "pricelist_id": cls.env.ref("product.list0").id,
            }
        )
        type_cutoff = "accrued_revenue"
        cls.revenue_cutoff = (
            cls.env["account.cutoff"]
            .with_context(default_cutoff_type=type_cutoff)
            .create(
                {
                    "cutoff_type": type_cutoff,
                    "order_line_model": "sale.order.line",
                    "company_id": 1,
                    "cutoff_date": fields.Date.today(),
                }
            )
        )

    def _confirm_so_and_do_picking(self, qty_done):
        self.so.action_confirm()
        self.assertEqual(
            self.so.invoice_status,
            "no",
            'SO invoice_status should be "nothing to invoice" after confirming',
        )
        # Deliver
        pick = self.so.picking_ids
        pick.action_assign()
        pick.move_line_ids.write({"qty_done": qty_done})  # receive 2/5  # deliver 2/5
        pick._action_done()
        self.assertEqual(
            self.so.invoice_status,
            "to invoice",
            'SO invoice_status should be "to invoice" after partial delivery',
        )
        qties = [sol.qty_delivered for sol in self.so.order_line]
        self.assertEqual(
            qties,
            [qty_done for p in self.products],
            "Delivered quantities are wrong after partial delivery",
        )
