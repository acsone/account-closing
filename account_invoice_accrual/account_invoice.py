# -*- coding: utf-8 -*-
#
#
#    Authors: Laetitia Gangloff
#    Copyright (c) 2014 Acsone SA/NV (http://www.acsone.eu)
#    All Rights Reserved
#
#    WARNING: This program as such is intended to be used by professional
#    programmers who take the whole responsibility of assessing all potential
#    consequences resulting from its eventual inadequacies and bugs.
#    End users who are looking for a ready-to-use solution with commercial
#    guarantees and support are strongly advised to contact a Free Software
#    Service Company.
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
#

from openerp.osv import fields, orm


class account_invoice(orm.Model):
    _inherit = "account.invoice"

    _columns = {
        'accrual_move_id': fields.many2one(
            'account.move', 'Accrual Journal Entry',
            readonly=True, select=1, ondelete='restrict',
            help="Link to the Accrual Journal Items."),
        'accrual_move_name': fields.char('Accrual Journal Entry', size=64,
                                         readonly=True),
        'to_be_reversed': fields.related(
            'accrual_move_id', 'to_be_reversed', type='boolean',
            relation='account.move', string='To be reversed',
            store=False, readonly=True),
    }

    def reverse_invoice(self, cr, uid, ids, context=None):
        # get the list of invoice to reverse
        id_to_reverse = []
        for invoice in self.browse(cr, uid, ids, context=context):
            if invoice.accrual_move_id:
                id_to_reverse.append(invoice.id)
        # call reverse method
        if id_to_reverse:
            wiz_obj = self.pool.get("account.move.reverse")
            wiz_context = dict(context, active_ids=id_to_reverse,
                               active_model="account.invoice")
            wizard_id = wiz_obj.create(cr, uid, {}, context=wiz_context)
            wiz_obj.action_reverse(cr, uid, [wizard_id], context=wiz_context)

    def action_cancel(self, cr, uid, ids, context=None):
        if context is None:
            context = {}
        self.reverse_invoice(cr, uid, ids, context)
        res = super(account_invoice, self).action_cancel(
            cr, uid, ids, context=context)
        return res

    def invoice_validate(self, cr, uid, ids, context=None):
        if context is None:
            context = {}
        self.reverse_invoice(cr, uid, ids, context)
        res = super(account_invoice, self).invoice_validate(
            cr, uid, ids, context=context)
        return res

    def unlink(self, cr, uid, ids, context=None):
        if context is None:
            context = {}
        self.reverse_invoice(cr, uid, ids, context)
        res = super(account_invoice, self).unlink(
            cr, uid, ids, context=context)
        return res

    def _move_accrual(self, cr, uid, invoice, accrual_date, account_id,
                      accrual_period_id=False, accrual_journal_id=False,
                      move_prefix=False, move_line_prefix=False,
                      context=None):
        """
        Create the accrual of a move

        :param invoice: browse instance of the invoice to accrue
        :param accrual_date: when the accrual must be input
        :param accrual_period_id: facultative period to write on the move
                                   (use the period of the date if empty
        :param accrual_journal_id: facultative journal on which create
                                    the move
        :param move_prefix: prefix for the move's name
        :param move_line_prefix: prefix for the move line's names

        :return: Returns the id of the created accrual move
        """
        if context is None:
            context = {}
        period_obj = self.pool.get('account.period')
        ait_obj = self.pool.get('account.invoice.tax')
        cur_obj = self.pool.get('res.currency')
        payment_term_obj = self.pool.get('account.payment.term')
        move_obj = self.pool.get('account.move')
        company_currency = self.pool['res.company'].browse(
            cr, uid, invoice.company_id.id).currency_id.id
        period_ctx = context.copy()
        period_ctx['company_id'] = invoice.company_id.id
        period_ctx['account_period_prefer_normal'] = True

        if not accrual_period_id:
            accrual_period_id = period_obj.find(
                cr, uid, accrual_date, context=period_ctx)[0]
        if not accrual_journal_id:
            accrual_journal_id = invoice.journal_id.id

        accrual_ref = ''.join(
            [x for x in [move_prefix, invoice.reference and
                         invoice.reference or invoice.name, ] if x])

        iml = self._get_analytic_lines(cr, uid, invoice.id, context=context)
        # check if taxes are all computed
        compute_taxes = ait_obj.compute(cr, uid, invoice.id, context=context)
        self.check_tax_lines(cr, uid, invoice, compute_taxes, ait_obj)

        # one move line per tax line
        iml += ait_obj.move_line_get(cr, uid, invoice.id)

        diff_currency_p = invoice.currency_id.id != company_currency
        # create one move line for the total and possibly adjust the other
        # lines amount
        total, total_currency, iml = self.compute_invoice_totals(
            cr, uid, invoice, company_currency, accrual_ref, iml,
            context=period_ctx)

        name = '/'
        totlines = False
        if invoice.payment_term:
            totlines = payment_term_obj.compute(
                cr, uid, invoice.payment_term.id, total,
                invoice.date_invoice or False, context=period_ctx)
        if totlines:
            res_amount_currency = total_currency
            i = 0
            period_ctx.update({'date': invoice.date_invoice})
            for t in totlines:
                if invoice.currency_id.id != company_currency:
                    amount_currency = cur_obj.compute(
                        cr, uid, company_currency,
                        invoice.currency_id.id, t[1], context=period_ctx)
                else:
                    amount_currency = False

                # last line add the diff
                res_amount_currency -= amount_currency or 0
                i += 1
                if i == len(totlines):
                    amount_currency += res_amount_currency

                iml.append({
                    'type': 'dest',
                    'name': name,
                    'price': t[1],
                    'account_id': account_id,
                    'date_maturity': t[0],
                    'amount_currency': diff_currency_p and
                    amount_currency or False,
                    'currency_id': diff_currency_p and invoice.currency_id.id
                    or False,
                    'ref': accrual_ref,
                })
        else:
            iml.append({
                'type': 'dest',
                'name': name,
                'price': total,
                'account_id': account_id,
                'date_maturity': invoice.date_due or False,
                'amount_currency': diff_currency_p and total_currency or False,
                'currency_id': diff_currency_p and invoice.currency_id.id
                or False,
                'ref': accrual_ref
            })

        part = self.pool.get("res.partner")._find_accounting_partner(
            invoice.partner_id)
        line = map(lambda x: (0, 0, self.line_get_convert(
            cr, uid, x, part.id, accrual_date, context=period_ctx)), iml)
        line = self.group_lines(cr, uid, iml, line, invoice)
        line = self.finalize_invoice_move_lines(cr, uid, invoice, line)

        if move_line_prefix:
            # update all move name with prefix
            for ml in line:
                ml[2]['name'] = ' '.join(
                    [x for x in [move_line_prefix, ml[2]['name']] if x])

        move = {
            'ref': accrual_ref,
            'line_id': line,
            'journal_id': accrual_journal_id,
            'date': accrual_date,
            'narration': invoice.comment,
            'company_id': invoice.company_id.id,
        }

        move['period_id'] = accrual_period_id
        for i in line:
            i[2]['period_id'] = accrual_period_id

        period_ctx.update(invoice=invoice)
        accrual_move_id = move_obj.create(cr, uid, move, context=period_ctx)
        new_move_name = move_obj.browse(
            cr, uid, accrual_move_id, context=period_ctx).name
        # make the invoice point to that move
        self.write(cr, uid, [invoice.id], {'accrual_move_id': accrual_move_id,
                                           'accrual_move_name': new_move_name},
                   context=period_ctx)
        # Pass invoice in context in method post: used if you want to get the
        # same account move reference when creating the same invoice after a
        # cancelled one:
        move_obj.validate(cr, uid, [accrual_move_id], context=period_ctx)

        return accrual_move_id

    def create_accruals(self, cr, uid, ids, accrual_date, account_id,
                        accrual_period_id=False, accrual_journal_id=False,
                        move_prefix=False, move_line_prefix=False,
                        context=None):
        """
        Create the accrual of one or multiple invoices

        :param accrual_date: when the accrual must be input
        :param accrual_period_id: facultative period to write on the move
                                   (use the period of the date if empty
        :param accrual_journal_id: facultative journal on which create
                                    the move
        :param move_prefix: prefix for the move's name
        :param move_line_prefix: prefix for the move line's names

        :return: Returns a list of ids of the created accrual moves
        """

        accrued_move_ids = []
        for invoice in self.browse(cr, uid, ids, context=context):
            if invoice.state not in ('draft', 'proforma2'):
                continue  # skip the accrual creation if state is not draft

            accrual_move_id = self._move_accrual(
                cr, uid, invoice, accrual_date,
                account_id, accrual_period_id=accrual_period_id,
                accrual_journal_id=accrual_journal_id,
                move_prefix=move_prefix, move_line_prefix=move_line_prefix,
                context=context)

            if accrual_move_id:
                accrued_move_ids.append(accrual_move_id)

        return accrued_move_ids