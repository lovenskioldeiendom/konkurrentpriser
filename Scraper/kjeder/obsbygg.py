"""
Obs Bygg scraper — enkel HTTP + BeautifulSoup.

Priser ligger i HTML-en på kategorisidene (jeg så det ved analyse).
URL-mønster: https://www.obsbygg.no/[kategori-sti]/[produkt-id]?v=ObsBygg-[GTIN]

NOBB matcher GTIN på Obs Bygg (i URL-parameteren v=ObsBygg-[GTIN]).
Vi bruker Obs Bygg sitt eget søk for å finne produkter — og det er IKKE blokkert.
"""

import asyncio
import logging
import re

import requests
from bs4 import BeautifulSoup

log = logging.getLogger('obsbygg')

SOK_URL = 'https://www.obsbygg.no/sok'  # Returnerer søkeresultater i HTML
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Maxbo Prismatrise; intern bruk)',
    'Accept-Language': 'nb-NO,nb;q=0.9,no;q=0.8,en;q=0.5',
}


def parse_pris(tekst: str) -> float | None:
    """Plukker første pris-aktige tall fra en streng."""
    if not tekst:
        return None
    # Obs Bygg viser pris som to elementer: "725" og "00" — vi henter både
    rens = tekst.replace(' ', '').replace('\xa0', '').replace(',', '.')
    m = re.search(r'(\d+\.?\d*)', rens)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            return None
    return None


def hent_produkt_via_sok(nobb: str) -> dict | None:
    """Søker etter NOBB hos Obs Bygg, returnerer prisinfo for første treff."""
    try:
        r = requests.get(
            SOK_URL,
            params={'q': nobb},
            headers=HEADERS,
            timeout=10,
        )
        r.raise_for_status()
        soup = BeautifulSoup(r.text, 'html.parser')

        # GJETNING: produkter er a-tags som lenker til /xxx?v=ObsBygg-NOBB
        produkt_lenke = soup.find('a', href=re.compile(rf'v=ObsBygg-{nobb}'))
        if not produkt_lenke:
            log.debug(f"NOBB {nobb} ikke funnet i Obs Bygg-søk")
            return None

        produkt_url = 'https://www.obsbygg.no' + produkt_lenke['href']

        # Pris ligger som regel i samme produkt-card. Let etter tall i nærheten.
        kort = produkt_lenke.find_parent() or produkt_lenke
        kort_tekst = kort.get_text(separator=' ', strip=True)

        # Heuristikk: finn alle tall som ser ut som priser (3-5 sifre, ev. desimaler)
        # Obs Bygg har "Medlem 69 00 Ikke medlem 149 00" — vi vil ha medlemspris hvis tilgjengelig
        priser_funnet = re.findall(r'\b(\d{1,4})\s*(\d{2})\s*(?=stk|På lager|Medlem|Ikke|per|$)', kort_tekst)
        # Fallback: bare to tall etter hverandre der andre er 2-sifret (decimaldelen)
        if not priser_funnet:
            priser_funnet = re.findall(r'\b(\d{1,4})\s+(\d{2})\b', kort_tekst)

        priser_tall = []
        for hel, des in priser_funnet:
            try:
                priser_tall.append(float(f'{hel}.{des}'))
            except ValueError:
                continue

        if not priser_tall:
            log.warning(f"Fant produktlenke for NOBB {nobb} men ingen pris i kortet")
            return None

        pris = min(priser_tall)
        forpris = max(priser_tall) if max(priser_tall) > min(priser_tall) * 1.05 else None

        # Lagerstatus
        lagerstatus = 'ukjent'
        if 'Ikke på lager' in kort_tekst:
            lagerstatus = 'ikke_paa_lager'
        elif 'På lager' in kort_tekst:
            lagerstatus = 'paa_lager'

        return {
            'pris': pris,
            'forpris': forpris,
            'lagerstatus': lagerstatus,
            'url': produkt_url,
        }

    except requests.RequestException as e:
        log.error(f"HTTP-feil for NOBB {nobb}: {e}")
        return None


async def scrape_obsbygg(produkter: list[dict]) -> dict:
    """Async wrapper rundt synkrone HTTP-kall (bruker thread pool internt)."""
    resultater = {}
    loop = asyncio.get_event_loop()

    for i, prod in enumerate(produkter, 1):
        nobb = prod['nobb']
        log.info(f"[{i}/{len(produkter)}] {prod['produktnavn'][:50]}")
        data = await loop.run_in_executor(None, hent_produkt_via_sok, nobb)
        if data:
            resultater[nobb] = data
        await asyncio.sleep(0.8)  # Rate limiting

    return resultater
