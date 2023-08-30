# Copyright 2018-2021 Jacques-Etienne Baudoux (BCIM sprl) <je@bcim.be>

from datetime import datetime, timedelta

from dateutil.relativedelta import relativedelta

from odoo import Command, fields
from odoo.tests.common import Form, TransactionCase


class TestAccountCutoffAccrualPicking(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.ref("base.main_company")
        cls.accrual_journal = cls.env["account.journal"].create(
            {
                "code": "cop0",
                "company_id": cls.company.id,
                "name": "Accrual Journal Picking",
                "type": "general",
            }
        )
        cls.accrual_account = cls.env["account.account"].create(
            {
                "name": "Accrual account",
                "code": "ACC480000",
                "company_id": cls.company.id,
                "account_type": "liability_current",
            }
        )
        cls.company.write(
            {
                "default_accrued_revenue_account_id": cls.accrual_account.id,
                "default_accrued_expense_account_id": cls.accrual_account.id,
                "default_cutoff_journal_id": cls.accrual_journal.id,
            }
        )

        cls.partner = cls.env.ref("base.res_partner_1")
        cls.products = cls.env.ref("product.product_delivery_01") | cls.env.ref(
            "product.product_delivery_02"
        )
        cls.stock_location = cls.env.ref("stock.stock_location_stock")
        for p in cls.products:
            cls.env["stock.quant"]._update_available_quantity(
                p, cls.stock_location, 100
            )
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
                    "company_id": 1,
                    "cutoff_date": fields.Date.today(),
                }
            )
        )

        # Removing all existing PO
        cls.env.cr.execute("DELETE FROM purchase_order;")
        # Create PO
        cls.po = cls.env["purchase.order"].create(
            {
                "partner_id": cls.partner.id,
                "order_line": [
                    Command.create(
                        {
                            "name": p.name,
                            "product_id": p.id,
                            "product_qty": 5,
                            "product_uom": p.uom_po_id.id,
                            "price_unit": 100,
                            "date_planned": fields.Date.to_string(
                                datetime.today() + relativedelta(days=-15)
                            ),
                        },
                    )
                    for p in cls.products
                ],
            }
        )
        type_cutoff = "accrued_expense"
        cls.expense_cutoff = (
            cls.env["account.cutoff"]
            .with_context(default_cutoff_type=type_cutoff)
            .create(
                {
                    "cutoff_type": type_cutoff,
                    "company_id": 1,
                    "cutoff_date": fields.Date.today(),
                }
            )
        )

    def _refund_invoice(self, invoice, post=True):
        credit_note_wizard = (
            self.env["account.move.reversal"]
            .with_context(
                **{
                    "active_ids": invoice.ids,
                    "active_id": invoice.id,
                    "active_model": "account.move",
                }
            )
            .create(
                {
                    "refund_method": "refund",
                    "reason": "refund",
                    "journal_id": invoice.journal_id.id,
                }
            )
        )
        invoice_refund = self.env["account.move"].browse(
            credit_note_wizard.reverse_moves()["res_id"]
        )
        invoice_refund.ref = invoice_refund.id
        if post:
            invoice_refund.action_post()
        return invoice_refund

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

    def test_accrued_revenue_empty(self):
        """Test cutoff when there is no SO."""
        cutoff = self.revenue_cutoff
        cutoff.get_lines()
        self.assertEqual(
            len(cutoff.line_ids), 0, "There should be no SO line to process"
        )

    def test_accrued_revenue_on_so_not_invoiced(self):
        """Test cutoff based on SO where qty_delivered > qty_invoiced."""
        cutoff = self.revenue_cutoff
        self._confirm_so_and_do_picking(2)
        cutoff.get_lines()
        self.assertEqual(len(cutoff.line_ids), 2, "2 cutoff lines should be found")
        for line in cutoff.line_ids:
            self.assertEqual(
                line.cutoff_amount, 100 * 2, "SO line cutoff amount incorrect"
            )
        # Make invoice
        self.so._create_invoices(final=True)
        # - invoice is in draft, no change to cutoff
        self.assertEqual(len(cutoff.line_ids), 2, "2 cutoff lines should be found")
        for line in cutoff.line_ids:
            self.assertEqual(
                line.cutoff_amount, 100 * 2, "SO line cutoff amount incorrect"
            )
        # Validate invoice
        self.so.invoice_ids.action_post()
        self.assertEqual(len(cutoff.line_ids), 2, "2 cutoff lines should be found")
        for line in cutoff.line_ids:
            self.assertEqual(line.cutoff_amount, 0, "SO line cutoff amount incorrect")
        # Make a refund - the refund reset the SO lines qty_invoiced
        self._refund_invoice(self.so.invoice_ids)
        self.assertEqual(len(cutoff.line_ids), 2, "2 cutoff lines should be found")
        for line in cutoff.line_ids:
            self.assertEqual(line.cutoff_amount, 200, "SO line cutoff amount incorrect")

    def test_accrued_revenue_on_so_all_invoiced(self):
        """Test cutoff based on SO where qty_delivered = qty_invoiced."""
        cutoff = self.revenue_cutoff
        self._confirm_so_and_do_picking(2)
        # Make invoice
        self.so._create_invoices(final=True)
        # Validate invoice
        self.so.invoice_ids.action_post()
        cutoff.get_lines()
        self.assertEqual(len(cutoff.line_ids), 0, "No cutoff lines should be found")
        # Make a refund - the refund reset qty_invoiced
        self._refund_invoice(self.so.invoice_ids)
        self.assertEqual(len(cutoff.line_ids), 2, "No cutoff lines should be found")
        for line in cutoff.line_ids:
            self.assertEqual(line.cutoff_amount, 200, "SO line cutoff amount incorrect")

    def test_accrued_revenue_on_so_draft_invoice(self):
        """Test cutoff based on SO where qty_delivered = qty_invoiced but the.

        invoice is still in draft
        """
        cutoff = self.revenue_cutoff
        self._confirm_so_and_do_picking(2)
        # Make invoice
        self.so._create_invoices(final=True)
        # - invoice is in draft, no change to cutoff
        cutoff.get_lines()
        self.assertEqual(len(cutoff.line_ids), 2, "2 cutoff lines should be found")
        for line in cutoff.line_ids:
            self.assertEqual(
                line.cutoff_amount, 100 * 2, "SO line cutoff amount incorrect"
            )
        # Validate invoice
        self.so.invoice_ids.action_post()
        self.assertEqual(len(cutoff.line_ids), 2, "no cutoff lines should be found")
        for line in cutoff.line_ids:
            self.assertEqual(line.cutoff_amount, 0, "SO line cutoff amount incorrect")
        # Make a refund - the refund reset SO lines qty_invoiced
        self._refund_invoice(self.so.invoice_ids)
        self.assertEqual(len(cutoff.line_ids), 2, "2 cutoff lines should be found")
        for line in cutoff.line_ids:
            self.assertEqual(line.cutoff_amount, 200, "SO line cutoff amount incorrect")

    def test_accrued_revenue_on_so_not_invoiced_after_cutoff(self):
        """Test cutoff based on SO where qty_delivered > qty_invoiced.

        And make invoice after cutoff date
        """
        cutoff = self.revenue_cutoff
        self._confirm_so_and_do_picking(2)
        cutoff.get_lines()
        # Make invoice
        self.so._create_invoices(final=True)
        # - invoice is in draft, no change to cutoff
        self.assertEqual(len(cutoff.line_ids), 2, "2 cutoff lines should be found")
        for line in cutoff.line_ids:
            self.assertEqual(
                line.cutoff_amount, 100 * 2, "SO line cutoff amount incorrect"
            )
        # Validate invoice after cutoff
        self.so.invoice_ids.invoice_date = cutoff.cutoff_date + timedelta(days=1)
        self.so.invoice_ids.action_post()
        self.assertEqual(len(cutoff.line_ids), 2, "2 cutoff lines should be found")
        for line in cutoff.line_ids:
            self.assertEqual(
                line.cutoff_amount, 100 * 2, "SO line cutoff amount incorrect"
            )
        # Make a refund after cutoff
        refund = self._refund_invoice(self.so.invoice_ids, post=False)
        refund.date = cutoff.cutoff_date + timedelta(days=1)
        refund.action_post()
        self.assertEqual(len(cutoff.line_ids), 2, "2 cutoff lines should be found")
        for line in cutoff.line_ids:
            self.assertEqual(
                line.cutoff_amount, 100 * 2, "SO line cutoff amount incorrect"
            )

    def test_accrued_revenue_on_so_all_invoiced_after_cutoff(self):
        """Test cutoff based on SO where qty_delivered = qty_invoiced.

        And make invoice after cutoff date
        """
        cutoff = self.revenue_cutoff
        self._confirm_so_and_do_picking(2)
        # Make invoice
        self.so._create_invoices(final=True)
        # Validate invoice after cutoff
        self.so.invoice_ids.invoice_date = cutoff.cutoff_date + timedelta(days=1)
        self.so.invoice_ids.action_post()
        cutoff.get_lines()
        self.assertEqual(len(cutoff.line_ids), 2, "2 cutoff lines should be found")
        for line in cutoff.line_ids:
            self.assertEqual(
                line.cutoff_amount, 2 * 100, "SO line cutoff amount incorrect"
            )
        # Make a refund - the refund reset SO lines qty_invoiced
        refund = self._refund_invoice(self.so.invoice_ids, post=False)
        refund.date = cutoff.cutoff_date + timedelta(days=1)
        refund.action_post()
        self.assertEqual(len(cutoff.line_ids), 2, "no cutoff lines should be found")
        for line in cutoff.line_ids:
            self.assertEqual(
                line.cutoff_amount, 100 * 2, "SO line cutoff amount incorrect"
            )

    def test_accrued_expense_empty(self):
        """Test cutoff when there is no PO."""
        cutoff = self.expense_cutoff
        cutoff.get_lines()
        self.assertEqual(
            len(cutoff.line_ids), 0, "There should be no PO line to process"
        )

    def _confirm_po_and_do_picking(self, qty_done):
        self.po.button_confirm()
        self.po.button_approve(force=True)
        pick = self.po.picking_ids
        pick.action_assign()
        pick.move_line_ids.write({"qty_done": qty_done})
        pick._action_done()
        qties = [pol.qty_received for pol in self.po.order_line]
        self.assertEqual(
            qties,
            [qty_done for p in self.products],
            "Delivered quantities are wrong after partial delivery",
        )

    def _create_po_invoice(self, date):
        invoice_form = Form(
            self.env["account.move"].with_context(
                default_move_type="in_invoice", default_purchase_id=self.po.id
            )
        )
        invoice_form.invoice_date = date
        return invoice_form.save()

    def test_accrued_expense_on_po_not_invoiced(self):
        """Test cutoff based on PO where qty_received > qty_invoiced."""
        cutoff = self.expense_cutoff
        self._confirm_po_and_do_picking(2)
        cutoff.get_lines()
        self.assertEqual(len(cutoff.line_ids), 2, "2 cutoff lines should be found")
        for line in cutoff.line_ids:
            self.assertEqual(
                line.cutoff_amount, -100 * 2, "PO line cutoff amount incorrect"
            )
        # Make invoice
        po_invoice = self._create_po_invoice(fields.Date.today())
        # - invoice is in draft, no change to cutoff
        self.assertEqual(len(cutoff.line_ids), 2, "2 cutoff lines should be found")
        for line in cutoff.line_ids:
            self.assertEqual(
                line.cutoff_amount, -100 * 2, "PO line cutoff amount incorrect"
            )
        # Validate invoice
        po_invoice.action_post()
        self.assertEqual(len(cutoff.line_ids), 2, "no cutoff lines should be found")
        for line in cutoff.line_ids:
            self.assertEqual(line.cutoff_amount, 0, "SO line cutoff amount incorrect")
        # Make a refund after cutoff - the refund is affecting the PO lines qty_invoiced
        refund = self._refund_invoice(po_invoice, post=False)
        refund.date = cutoff.cutoff_date + timedelta(days=1)
        refund.action_post()
        self.assertEqual(len(cutoff.line_ids), 2, "no cutoff lines should be found")
        for line in cutoff.line_ids:
            self.assertEqual(line.cutoff_amount, 0, "SO line cutoff amount incorrect")
        # Make a refund before cutoff
        # - the refund is affecting the PO lines qty_invoiced
        refund = self._refund_invoice(po_invoice)
        self.assertEqual(len(cutoff.line_ids), 2, "2 cutoff lines should be found")
        for line in cutoff.line_ids:
            self.assertEqual(
                line.cutoff_amount, -100 * 2, "PO line cutoff amount incorrect"
            )

    def test_accrued_expense_on_po_all_invoiced(self):
        """Test cutoff based on PO where qty_received = qty_invoiced."""
        cutoff = self.expense_cutoff
        self._confirm_po_and_do_picking(2)
        # Make invoice
        po_invoice = self._create_po_invoice(fields.Date.today())
        # Validate invoice
        po_invoice.action_post()
        cutoff.get_lines()
        self.assertEqual(len(cutoff.line_ids), 0, "No cutoff lines should be found")
        # Make a refund after cutoff - the refund is affecting the PO lines qty_invoiced
        refund = self._refund_invoice(po_invoice, post=False)
        refund.date = cutoff.cutoff_date + timedelta(days=1)
        refund.action_post()
        self.assertEqual(len(cutoff.line_ids), 0, "2 cutoff lines should be found")
        # Make a refund before cutoff
        # - the refund is affecting the PO lines qty_invoiced
        refund = self._refund_invoice(po_invoice)
        self.assertEqual(len(cutoff.line_ids), 2, "2 cutoff lines should be found")
        for line in cutoff.line_ids:
            self.assertEqual(
                line.cutoff_amount, -100 * 2, "PO line cutoff amount incorrect"
            )

    def test_accrued_expense_on_po_draft_invoice(self):
        """Test cutoff based on PO where qty_received = qty_invoiced but the.

        invoice is still in draft
        """
        cutoff = self.expense_cutoff
        self._confirm_po_and_do_picking(2)
        # Make invoice
        po_invoice = self._create_po_invoice(fields.Date.today())
        # - invoice is in draft, no change to cutoff
        cutoff.get_lines()
        self.assertEqual(len(cutoff.line_ids), 2, "2 cutoff lines should be found")
        for line in cutoff.line_ids:
            self.assertEqual(
                line.cutoff_amount, -100 * 2, "PO line cutoff amount incorrect"
            )
        # Validate invoice
        po_invoice.action_post()

        self.assertEqual(len(cutoff.line_ids), 2, "no cutoff lines should be found")
        for line in cutoff.line_ids:
            self.assertEqual(line.cutoff_amount, 0, "PO line cutoff amount incorrect")
        # Make a refund after cutoff - the refund is affecting the PO lines qty_invoiced
        refund = self._refund_invoice(po_invoice, post=False)
        refund.date = cutoff.cutoff_date + timedelta(days=1)
        refund.action_post()
        self.assertEqual(len(cutoff.line_ids), 2, "2 cutoff lines should be found")
        for line in cutoff.line_ids:
            self.assertEqual(line.cutoff_amount, 0, "PO line cutoff amount incorrect")
        # Make a refund before cutoff
        # - the refund is affecting the PO lines qty_invoiced
        refund = self._refund_invoice(po_invoice)

        self.assertEqual(len(cutoff.line_ids), 2, "2 cutoff lines should be found")
        for line in cutoff.line_ids:
            self.assertEqual(
                line.cutoff_amount, -100 * 2, "PO line cutoff amount incorrect"
            )

    def test_accrued_expense_on_po_draft_refund(self):
        """Test cutoff based on PO where qty_received = qty_invoiced but the.

        refund is still in draft
        """
        cutoff = self.expense_cutoff
        self._confirm_po_and_do_picking(2)
        # Make invoice for 5
        po_invoice = self._create_po_invoice(fields.Date.today())
        po_invoice.invoice_line_ids.write({"quantity": 5})
        # Validate invoice
        po_invoice.action_post()
        # Make a refund for the 3 that have not been received
        # - the refund is affecting the PO lines qty_invoiced
        refund = self._refund_invoice(po_invoice, post=False)
        refund.invoice_line_ids.write({"quantity": 3})
        cutoff.get_lines()
        self.assertEqual(len(cutoff.line_ids), 0, "No cutoff lines should be found")
        for line in cutoff.line_ids:
            self.assertEqual(line.cutoff_amount, 0, "PO line cutoff amount incorrect")
        refund.action_post()
        self.assertEqual(len(cutoff.line_ids), 0, "No cutoff lines should be found")
        for line in cutoff.line_ids:
            self.assertEqual(line.cutoff_amount, 0, "PO line cutoff amount incorrect")

    def test_accrued_expense_on_po_not_invoiced_after_cutoff(self):
        """Test cutoff based on PO where qty_received > qty_invoiced.

        And make invoice after cutoff date
        """
        cutoff = self.expense_cutoff
        self._confirm_po_and_do_picking(2)
        cutoff.get_lines()

        # Make invoice
        po_invoice = self._create_po_invoice(fields.Date.today())
        # - invoice is in draft, no change to cutoff

        self.assertEqual(len(cutoff.line_ids), 2, "2 cutoff lines should be found")
        for line in cutoff.line_ids:
            self.assertEqual(
                line.cutoff_amount, -100 * 2, "PO line cutoff amount incorrect"
            )
        # Validate invoice after cutoff
        po_invoice.date = cutoff.cutoff_date + timedelta(days=1)
        po_invoice.action_post()

        self.assertEqual(len(cutoff.line_ids), 2, "no cutoff lines should be found")
        for line in cutoff.line_ids:
            self.assertEqual(
                line.cutoff_amount, -100 * 2, "PO line cutoff amount incorrect"
            )
        # Make a refund after cutoff - the refund is affecting the PO lines qty_invoiced
        refund = self._refund_invoice(po_invoice, post=False)
        refund.date = cutoff.cutoff_date + timedelta(days=1)
        refund.action_post()
        self.assertEqual(len(cutoff.line_ids), 2, "2 cutoff lines should be found")
        for line in cutoff.line_ids:
            self.assertEqual(
                line.cutoff_amount, -100 * 2, "PO line cutoff amount incorrect"
            )
        # Make a refund before cutoff
        # - the refund is affecting the PO lines qty_invoiced
        refund = self._refund_invoice(po_invoice)

        self.assertEqual(len(cutoff.line_ids), 2, "2 cutoff lines should be found")
        for line in cutoff.line_ids:
            self.assertEqual(
                line.cutoff_amount, -100 * 2 * 2, "PO line cutoff amount incorrect"
            )

    def test_accrued_expense_on_po_all_invoiced_after_cutoff(self):
        """Test cutoff based on PO where qty_received = qty_invoiced.

        And make invoice after cutoff date
        """
        cutoff = self.expense_cutoff
        self._confirm_po_and_do_picking(2)
        # Make invoice
        po_invoice = self._create_po_invoice(fields.Date.today())
        # Validate invoice after cutoff
        po_invoice.date = cutoff.cutoff_date + timedelta(days=1)
        po_invoice.action_post()
        cutoff.get_lines()
        self.assertEqual(len(cutoff.line_ids), 2, "2 cutoff lines should be found")
        # Make a refund after cutoff - the refund is affecting the PO lines qty_invoiced
        refund = self._refund_invoice(po_invoice, post=False)
        refund.date = cutoff.cutoff_date + timedelta(days=1)
        refund.action_post()
        self.assertEqual(len(cutoff.line_ids), 2, "2 cutoff lines should be found")
        for line in cutoff.line_ids:
            self.assertEqual(
                line.cutoff_amount, -100 * 2, "PO line cutoff amount incorrect"
            )
        # Make a refund before cutoff
        # - the refund is affecting the PO lines qty_invoiced
        refund = self._refund_invoice(po_invoice)

        self.assertEqual(len(cutoff.line_ids), 2, "2 cutoff lines should be found")
        for line in cutoff.line_ids:
            self.assertEqual(
                line.cutoff_amount, -100 * 2 * 2, "PO line cutoff amount incorrect"
            )
