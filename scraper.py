import time
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

BASE_URL = "https://lespepitestech.com"
CATEGORY_URL = f"{BASE_URL}/startup-collection"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
}
REQUEST_DELAY = 1.0  # seconds between requests


class PepitesScraper:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)

    def fetch_categories(self):
        """Fetch available categories from multiple sources.

        Combines:
        - Sidebar "Les collections" (major collections with startup counts)
        - Tags from the first few homepage pages (finer categories)

        Returns dict: {slug: {"name": str, "count": int or None}}
        """
        cats = {}

        # 1) Sidebar collections from a category page (major categories with counts)
        try:
            resp = self.session.get(f"{CATEGORY_URL}/saas", timeout=15)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
            sidebar = soup.select_one(".view-collections-side .view-content__wrapper")
            if sidebar:
                for div in sidebar.find_all("div", recursive=False):
                    count_el = div.select_one(".views-field-title .field-content")
                    name_el = div.select_one(".views-field-name a")
                    if name_el:
                        name = name_el.get_text(strip=True)
                        href = name_el.get("href", "")
                        slug = href.split("/startup-collection/")[-1]
                        count = None
                        if count_el:
                            digits = count_el.get_text(strip=True)
                            if digits.isdigit():
                                count = int(digits)
                        if slug:
                            cats[slug] = {"name": name, "count": count}
        except Exception:
            pass

        # 2) Tags from the first 5 startup-collection pages
        for page in range(5):
            try:
                resp = self.session.get(f"{CATEGORY_URL}?page={page}", timeout=15)
                resp.raise_for_status()
                soup = BeautifulSoup(resp.text, "html.parser")
                for a in soup.select(
                    ".lpt-dropdown-category a, .lpt-dropdown-all-categories a"
                ):
                    name = a.get_text(strip=True)
                    href = a.get("href", "")
                    if name and href and "/startup-collection/" in href:
                        slug = href.split("/startup-collection/")[-1]
                        if slug and slug not in cats:
                            cats[slug] = {"name": name, "count": None}
            except Exception:
                break
            time.sleep(0.3)

        return dict(sorted(cats.items(), key=lambda x: x[1]["name"].lower()))

    def scrape_listing_page(self, page_number, category=None):
        """Scrape a single listing page and return a list of startup dicts."""
        if category:
            url = f"{CATEGORY_URL}/{category}?page={page_number}"
        else:
            url = f"{CATEGORY_URL}?page={page_number}"
        resp = self.session.get(url, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        startups = []
        cards = soup.select(".lpt-card")
        for card in cards:
            startup = self._parse_card(card)
            if startup:
                startups.append(startup)
        return startups

    def _parse_card(self, card):
        """Extract data from a single .lpt-card element."""
        data = {
            "nom": "",
            "description": "",
            "site_web": "",
            "categories": "",
            "votes": 0,
            "localisation": "",
            "detail_url": "",
            "fondateur": "",
            "twitter": "",
            "linkedin": "",
        }

        # Name (h3 inside .s-e-title)
        h3 = card.select_one("h3")
        if h3:
            data["nom"] = h3.get_text(strip=True)

        # Detail URL (a.startup-entry-hitbox)
        hitbox = card.select_one("a.startup-entry-hitbox")
        if hitbox:
            href = hitbox.get("href", "").strip()
            if href:
                data["detail_url"] = urljoin(BASE_URL, href)

        # Description (.s-u-summary)
        desc = card.select_one(".s-u-summary")
        if desc:
            data["description"] = desc.get_text(strip=True)

        # Tags / Categories (visible tag + dropdown tags)
        tags = []
        for a in card.select(".lpt-dropdown-category a"):
            t = a.get_text(strip=True)
            if t:
                tags.append(t)
        for a in card.select(".lpt-dropdown-all-categories a"):
            t = a.get_text(strip=True)
            if t:
                tags.append(t)
        data["categories"] = ", ".join(tags)

        # Votes (.alternate-votes-display)
        vote_el = card.select_one(".alternate-votes-display")
        if vote_el:
            text = vote_el.get_text(strip=True)
            digits = "".join(c for c in text if c.isdigit())
            if digits:
                data["votes"] = int(digits)

        # External website link (contains utm_source)
        site_link = card.select_one("a[href*='utm_source']")
        if site_link:
            data["site_web"] = site_link.get("href", "")

        return data

    def scrape_detail_page(self, detail_url):
        """Visit a startup detail page and return extra info."""
        extra = {"fondateur": "", "twitter": "", "linkedin": "", "localisation": ""}
        try:
            time.sleep(REQUEST_DELAY)
            resp = self.session.get(detail_url, timeout=15)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")

            # Founder (.founder contains a link with name + title as strings)
            founder_el = soup.select_one(".founder a")
            if founder_el:
                texts = list(founder_el.stripped_strings)
                if texts:
                    extra["fondateur"] = texts[0]

            # Social links (inside .startup-social, excludes share buttons)
            for a in soup.select(".startup-social a[href]"):
                href = a.get("href", "")
                if ("twitter.com" in href or "x.com" in href) and not extra["twitter"]:
                    extra["twitter"] = href
                elif "linkedin.com" in href and not extra["linkedin"]:
                    extra["linkedin"] = href

            # Location
            loc_el = soup.select_one(".th-location")
            if loc_el:
                extra["localisation"] = loc_el.get_text(strip=True)

            # Website (from detail page)
            site_link = soup.select_one("a[href*='utm_source=LesPepitesTech']")
            if site_link:
                extra["site_web"] = site_link.get("href", "")

        except Exception as e:
            print(f"Error scraping detail {detail_url}: {e}")

        return extra

    def scrape(self, num_pages=1, with_details=False, category=None, progress_callback=None):
        """Main scraping method. Returns list of startup dicts.

        Args:
            num_pages: Number of listing pages to scrape. 0 = all pages (auto-stop).
            with_details: If True, also visit each startup's detail page.
            category: Category slug to filter by (e.g. "b2b", "application-mobile").
            progress_callback: Optional callable(current, total, message).
        """
        all_startups = []
        scrape_all = num_pages == 0
        label = f" [{category}]" if category else ""
        page = 0
        total_steps = num_pages if not scrape_all else 1  # updated dynamically

        while True:
            if not scrape_all and page >= num_pages:
                break

            if progress_callback:
                if scrape_all:
                    progress_callback(
                        page, max(page + 1, total_steps),
                        f"Scraping{label} page {page + 1}... ({len(all_startups)} startups)",
                    )
                else:
                    progress_callback(
                        page, total_steps,
                        f"Scraping{label} page {page + 1}/{num_pages}...",
                    )
            try:
                startups = self.scrape_listing_page(page, category=category)
                if not startups:
                    break  # no more results
                all_startups.extend(startups)
            except Exception as e:
                print(f"Error on page {page}: {e}")
                break
            page += 1
            time.sleep(REQUEST_DELAY)

        pages_scraped = page
        if with_details and all_startups:
            total_steps = pages_scraped + len(all_startups)
            for i, startup in enumerate(all_startups):
                if progress_callback:
                    progress_callback(
                        pages_scraped + i,
                        total_steps,
                        f"Détails {i + 1}/{len(all_startups)}: {startup['nom']}",
                    )
                if startup.get("detail_url"):
                    extra = self.scrape_detail_page(startup["detail_url"])
                    if extra.get("fondateur"):
                        startup["fondateur"] = extra["fondateur"]
                    if extra.get("twitter"):
                        startup["twitter"] = extra["twitter"]
                    if extra.get("linkedin"):
                        startup["linkedin"] = extra["linkedin"]
                    if extra.get("localisation"):
                        startup["localisation"] = extra["localisation"]
                    if extra.get("site_web") and not startup.get("site_web"):
                        startup["site_web"] = extra["site_web"]

        if progress_callback:
            progress_callback(total_steps, total_steps, "Terminé !")

        return all_startups
