"""
Byggmakker scraper — enkel HTTP + BeautifulSoup.

Byggmakker har NOBB direkte i URL-en:
    https://www.byggmakker.no/produkt/[slug]/[NOBB]

Det gjør oppslaget trivielt — vi trenger ikke noe søk.
Pris ligger i HTML-en på produktsiden.
"""

import asyncio
import logging
import re

import requests
from bs4 import BeautifulSoup

log = logging.getLogger('byggmakker')

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Maxbo Prismatrise; intern bruk)',
    'Accept-Language': 'nb-NO,nb;q=0.9,no;q=0.8,en;q=0.5',
}

SOK_URL = 'https://www.byggmakker.no/sok'  # For å finne produkt-slug før vi vet URL-en


def hent_via_direkte_url(nobb: str) -> dict | None:
    """
    Byggmakker har NOBB i URL. Men vi må vite slug-en først.
    Vi prøver å hente via søket: returnerer første treff som matcher NOBB.
    """
    try:
        r = requests.get(SOK_URL, params={'q': nobb}, headers=HEADERS, timeout=10, allow_redirects=True)
        r.raise_for_status()

        # Hvis søket fant et eksakt treff, kan det allerede ha redirected til produktsiden
        if f'/produkt/' in r.url and nobb in r.url:
            return parse_produktside(r.text, r.url)

        # Ellers: finn første lenke til /produkt/.../{nobb}
        soup = BeautifulSoup(r.text, 'html.parser')
        produkt_lenke = soup.find('a', href=re.compile(rf'/produkt/[^/]+/{nobb}'))
        if not produkt_lenke:
            log.debug(f"NOBB {nobb} ikke funnet i Byggmakker-søk")
            return None

        produkt_url = 'https://www.byggmakker.no' + produkt_lenke['href']

        # Hent selve produktsiden for full pris/lagerinfo
        r2 = requests.get(produkt_url, headers=HEADERS, timeout=10)
        r2.raise_for_status()
        return parse_produktside(r2.text, produkt_url)

    except requests.RequestException as e:
        log.error(f"HTTP-feil for NOBB {nobb}: {e}")
        return None


def parse_produktside(html: str, url: str) -> dict | None:
    """Plukker pris og lagerstatus fra Byggmakker-produktside."""
    soup = BeautifulSoup(html, 'html.parser')
    tekst = soup.get_text(separator=' ', strip=True)

    # Byggmakker-pris-mønster: "Førpris: 169 kr / m2  118 30kr / m2"
    # eller bare "152 35kr / Stykk"
    pris = None
    forpris = None

    # Forpris (hvis kampanje)
    forpris_match = re.search(r'F[øo]rpris:\s*(\d[\d\s\.]*)\s*(?:,\d+)?\s*kr', tekst)
    if forpris_match:
        try:
            forpris = float(forpris_match.group(1).replace(' ', '').replace('.', '').replace(',', '.'))
        except ValueError:
            pass

    # Hovedpris — to mønstre: "152 35kr" eller "152 kr"
    pris_patterns = [
        r'(\d[\d\s]*)\s+(\d{2})\s*kr',  # 152 35 kr (hele + desimaler)
        r'(\d[\d\s\.]*),(\d{2})\s*kr', # 152,35 kr
        r'(\d[\d\s\.]*)\s*kr(?!\w)',    # 152 kr
    ]
    for pat in pris_patterns:
        m = re.search(pat, tekst)
        if m:
            try:
                if len(m.groups()) == 2:
                    hel = m.group(1).replace(' ', '').replace('.', '')
                    pris = float(f'{hel}.{m.group(2)}')
                else:
                    pris = float(m.group(1).replace(' ', '').replace('.', '').replace(',', '.'))
                break
            except ValueError:
                continue

    if pris is None:
        return None

    # Lagerstatus
    lagerstatus = 'ukjent'
    if 'Ikke på nettlager' in tekst or 'Ikke på lager' in tekst:
        lagerstatus = 'ikke_paa_lager'
    elif 'På nettlager' in tekst or 'På lager' in tekst:
        lagerstatus = 'paa_lager'

    return {
        'pris': pris,
        'forpris': forpris,
        'lagerstatus': lagerstatus,
        'url': url,
    }


async def scrape_byggmakker(produkter: list[dict]) -> dict:
    resultater = {}
    loop = asyncio.get_event_loop()

    for i, prod in enumerate(produkter, 1):
        nobb = prod['nobb']
        log.info(f"[{i}/{len(produkter)}] {prod['produktnavn'][:50]}")
        data = await loop.run_in_executor(None, hent_via_direkte_url, nobb)
        if data:
            resultater[nobb] = data
        await asyncio.sleep(0.8)

    return resultater
