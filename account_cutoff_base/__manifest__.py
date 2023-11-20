# Copyright 2013-2021 Akretion
# Copyright 2018-2021 Camptocamp
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

{
    "name": "Account Cut-off Base",
    "version": "16.0.1.3.0",
    "category": "Accounting & Finance",
    "license": "AGPL-3",
    "summary": "Base module for Account Cut-offs",
    "author": "Akretion,Odoo Community Association (OCA)",
    "maintainers": ["alexis-via", "jbaudoux"],
    "website": "https://github.com/OCA/account-closing",
    "depends": ["account"],
    "data": [
        "security/account_cutoff_base_security.xml",
        "security/ir.model.access.csv",
        "views/res_config_settings.xml",
        "views/account_cutoff.xml",
        "views/account_cutoff_line.xml",
        "views/account_cutoff_tax_line.xml",
        "views/account_cutoff_mapping.xml",
        "views/account_tax.xml",
    ],
    "installable": True,
}
