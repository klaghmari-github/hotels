"""
Scraping all.accor.com — marques + fiches hôtels.

* ``brands``  : page /a/fr/brands.html → marques.xlsx + logos PNG
* ``hotels``  : /hotel/{id}/index.fr.shtml → hotels_{start}_{end}.xlsx par plage
* ``orchestrator`` : attribution de plages sans collision multi-workers
"""

__version__ = "1.0.0"
