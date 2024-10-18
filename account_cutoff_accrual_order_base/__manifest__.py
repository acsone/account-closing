# Copyright 2018 Jacques-Etienne Baudoux (BCIM) <je@bcim.be>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)


{
    "name": "Account Cut-off Accrual Order Base",
    "version": "16.0.1.0.0",
    "category": "Accounting & Finance",
    "license": "AGPL-3",
    "summary": "Accrued Order Base",
    "author": "BCIM, Akretion, Odoo Community Association (OCA)",
    "maintainers": ["jbaudoux"],
    "website": "https://github.com/OCA/account-closing",
    "depends": ["account_cutoff_base"],
    "data": [
        "views/account_cutoff_view.xml",
        "views/account_cutoff_line_view.xml",
    ],
    "installable": True,
    "application": False,
}
