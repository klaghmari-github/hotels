"""
Scraping all.accor.com — version prod (fiche unitaire).

Modules livrés ici :
  hotels.py     extraction d'une fiche /hotel/{code}/index.fr.shtml
  http_util.py  fetch HTTP avec pause / User-Agent raisonnable

Le parcours user appelle ça via user.services.hotel_fetch quand un code
n'est pas encore dans hotel_data.

Les pipelines bulk (plages d'IDs, world scrape, marques massives) restent
dans l'archive accor_1_0_0 si besoin de reconstituer un parc.
"""

__version__ = "1.0.0"
