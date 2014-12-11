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

{
    "name": "Account invoice accrual",
    "version" : "0.1",
    "author" : "ACSONE SA/NV",
    "category" : "Invoice",
    "website" : "http://www.acsone.eu",
    "depends" : ["account",
                 "account_reversal",  # from account-financial-tools/7.0
    ],
    "description": """

Account invoice accrual
=========================


""",
    "data" : [
              "res_partner_view.xml",
              "account_invoice_view.xml",
              "wizard/account_move_accrue_view.xml",
    ],
    "demo": [],
    "test": [
             "test/account_invoice_accrual_confirm.yml",
             "test/account_invoice_accrual_remove.yml",
             "test/account_invoice_accrual_reversal.yml",
     ],
    "active": False,
    "license": "AGPL-3",
    "installable": True,
    "auto_install": False,
    "application": False,
}