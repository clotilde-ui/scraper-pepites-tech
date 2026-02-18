"""
Scraper des chefs d'établissements des lycées et collèges publics de France.

Source : API open data du Ministère de l'Éducation nationale
Dataset : fr-en-annuaire-education
URL     : https://data.education.gouv.fr/api/explore/v2.1/catalog/datasets/fr-en-annuaire-education/records
"""

import time
import requests

API_BASE = (
    "https://data.education.gouv.fr/api/explore/v2.1"
    "/catalog/datasets/fr-en-annuaire-education/records"
)

# Filtres : établissements publics de type lycée ou collège
WHERE_FILTER = (
    'statut_public_prive="Public" AND '
    'type_etablissement IN ("Lycée", "Collège", "Lycée professionnel", "Lycée polyvalent")'
)

FIELDS = ",".join([
    "nom_etablissement",
    "type_etablissement",
    "nom_chef_etablissement",
    "adresse_1",
    "commune",
    "code_postal",
    "departement",
    "region",
    "telephone",
    "mail",
    "nombre_eleves",
])

PAGE_SIZE = 100
REQUEST_DELAY = 0.3  # secondes entre chaque requête


def _derive_role(type_etablissement: str) -> str:
    """Déduit le titre du chef d'établissement d'après le type d'établissement."""
    t = (type_etablissement or "").strip().lower()
    if "collège" in t:
        return "Principal"
    return "Proviseur"


class ChefsEtablissementScraper:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (compatible; scraper-ecoles/1.0; +educational-data)",
            "Accept": "application/json",
        })

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def count_total(self, departement: str | None = None) -> int:
        """Retourne le nombre total d'enregistrements correspondant aux filtres."""
        params = {
            "where": self._build_where(departement),
            "limit": 1,
        }
        try:
            resp = self.session.get(API_BASE, params=params, timeout=15)
            resp.raise_for_status()
            return resp.json().get("total_count", 0)
        except Exception:
            return 0

    def scrape(
        self,
        departement: str | None = None,
        max_records: int = 0,
        progress_callback=None,
    ) -> list[dict]:
        """
        Récupère tous les chefs d'établissement via l'API Education nationale.

        Args:
            departement: Code ou nom de département pour filtrer (optionnel).
            max_records: Limite du nombre de résultats. 0 = tout récupérer.
            progress_callback: callable(current, total, message)

        Returns:
            Liste de dicts avec les informations de chaque chef d'établissement.
        """
        total = self.count_total(departement)
        if max_records and max_records < total:
            total = max_records

        if progress_callback:
            progress_callback(0, total, f"Total : {total} établissements à récupérer…")

        results = []
        offset = 0

        while True:
            limit = PAGE_SIZE
            if max_records:
                remaining = max_records - len(results)
                if remaining <= 0:
                    break
                limit = min(PAGE_SIZE, remaining)

            params = {
                "select": FIELDS,
                "where": self._build_where(departement),
                "limit": limit,
                "offset": offset,
                "order_by": "departement,nom_etablissement",
            }

            try:
                resp = self.session.get(API_BASE, params=params, timeout=20)
                resp.raise_for_status()
                data = resp.json()
            except Exception as e:
                print(f"Erreur API (offset={offset}): {e}")
                break

            records = data.get("results", [])
            if not records:
                break

            for rec in records:
                results.append(self._parse_record(rec))

            offset += len(records)

            if progress_callback:
                progress_callback(
                    len(results),
                    total,
                    f"Récupéré {len(results)}/{total} établissements…",
                )

            # Si l'API a renvoyé moins que demandé, on a tout récupéré
            if len(records) < limit:
                break

            time.sleep(REQUEST_DELAY)

        if progress_callback:
            progress_callback(len(results), len(results), "Terminé !")

        return results

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _build_where(self, departement: str | None) -> str:
        where = WHERE_FILTER
        if departement:
            dep = departement.strip().replace('"', "")
            where += f' AND departement="{dep}"'
        return where

    def _parse_record(self, rec: dict) -> dict:
        type_etab = rec.get("type_etablissement", "") or ""
        role = _derive_role(type_etab)

        return {
            "role": role,
            "nom_chef_etablissement": rec.get("nom_chef_etablissement", "") or "",
            "nom_etablissement": rec.get("nom_etablissement", "") or "",
            "type_etablissement": type_etab,
            "adresse": rec.get("adresse_1", "") or "",
            "code_postal": rec.get("code_postal", "") or "",
            "commune": rec.get("commune", "") or "",
            "departement": rec.get("departement", "") or "",
            "region": rec.get("region", "") or "",
            "telephone": rec.get("telephone", "") or "",
            "mail": rec.get("mail", "") or "",
            "nombre_eleves": rec.get("nombre_eleves", "") or "",
        }
