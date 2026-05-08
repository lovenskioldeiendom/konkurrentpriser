"""
Maxbo scraper — Playwright-basert.

GJETNINGER (verifiser ved første kjøring og juster):
- Butikkvelger åpnes ved klikk på "Velg din butikk"-knapp i toppmeny
- Pris vises i et element med klasse som inneholder "price" eller "Pris"
- "Ikke på lager" indikeres med tekst "Ikke på lager" eller en disabled kjøpsknapp
- NOBB står i HTML som "NOBB [tall]"

URL-mønster på Maxbo: https://www.maxbo.no/[produktnavn-med-bindestrek]-p[produktid]/
Vi trenger et NOBB → URL-oppslag (se README i scraper-mappa).

Ved første kjøring: kjør med --kjede maxbo --limit 1 og inspiser HTML
hvis selectors ikke matcher.
"""

import asyncio
import logging
import re
from pathlib import Path

from playwright.async_api import async_playwright, Page, TimeoutError as PlaywrightTimeout

log = logging.getLogger('maxbo')

# Oppslagstabell NOBB → produkt-URL på maxbo.no.
# Bygg denne én gang ved å crawle Maxbos kategorisider eller via PIM-eksport.
# Inntil videre fyller du den manuelt for testproduktene.
NOBB_TIL_URL = {
    '25410978': 'https://www.maxbo.no/terrassebord-cu-impregnert-furu-p968264/',
    # Legg til flere etter hvert som du finner dem.
    # Tips: søk i Maxbos kategorier, finn produkt-ID i URL, kombiner med NOBB fra produktsiden.
}


async def velg_butikk(page: Page, butikknavn: str):
    """
    Velger Maxbo-butikk i Oslo. Krever interaksjon med butikkvelgeren.
    GJETNING: knappen "Velg din butikk" finnes i toppmenyen.
    """
    try:
        # Forsøk 1: åpne butikkvelger via knapp/lenke
        await page.get_by_text("Velg din butikk", exact=False).first.click(timeout=5000)
        await page.wait_for_timeout(500)

        # Søk eller velg butikknavnet
        # GJETNING: det er et input-felt for å filtrere butikker
        search_input = page.locator('input[type="search"], input[placeholder*="søk" i], input[placeholder*="butikk" i]').first
        if await search_input.count() > 0:
            await search_input.fill(butikknavn)
            await page.wait_for_timeout(500)

        # Klikk på første treff som matcher butikknavnet
        await page.get_by_text(re.compile(f"Maxbo.*{butikknavn}", re.IGNORECASE)).first.click(timeout=5000)
        await page.wait_for_timeout(1000)
        log.info(f"Valgte butikk: Maxbo {butikknavn}")
        return True
    except PlaywrightTimeout:
        log.warning(f"Klarte ikke velge butikk via UI — fortsetter uten butikkvalg")
        return False


async def scrape_produkt(page: Page, nobb: str, url: str) -> dict | None:
    """Henter pris og lagerstatus for ett produkt."""
    try:
        await page.goto(url, wait_until='domcontentloaded', timeout=15000)

        # Vent på at pris renderes via JS
        # GJETNING: prisen vises etter at JS har lastet, typisk innen 3 sekunder
        await page.wait_for_timeout(2500)

        html = await page.content()

        # GJETNING 1: pris i tekst med kr-suffiks. Forsøk flere mønstre.
        pris = None
        forpris = None

        # Mønster: "1 234,56 kr" eller "1.234,56 kr" eller "1234 kr"
        pris_patterns = [
            r'(\d[\d\s\.]*,\d{2})\s*kr',           # 1 234,56 kr
            r'(\d[\d\s\.]*)\s*kr(?!\w)',           # 1234 kr
            r'class="[^"]*price[^"]*"[^>]*>([^<]+)<',  # generisk price-klasse
        ]

        for pattern in pris_patterns:
            matches = re.findall(pattern, html, re.IGNORECASE)
            if matches:
                # Heuristikk: ta laveste tall som "pris", høyeste som "forpris" hvis det er flere
                tall = []
                for m in matches[:5]:  # bare første 5 treff
                    try:
                        rens = m.replace(' ', '').replace('.', '').replace(',', '.')
                        tall.append(float(rens))
                    except ValueError:
                        continue
                if tall:
                    pris = min(tall)
                    if len(tall) > 1 and max(tall) > min(tall) * 1.05:
                        forpris = max(tall)
                    break

        # GJETNING 2: lagerstatus — finn tekst som "På lager" / "Ikke på lager"
        lagerstatus = 'ukjent'
        if re.search(r'ikke\s+p[åa]\s+lager', html, re.IGNORECASE):
            lagerstatus = 'ikke_paa_lager'
        elif re.search(r'p[åa]\s+lager', html, re.IGNORECASE):
            lagerstatus = 'paa_lager'

        if pris is None:
            log.warning(f"Fant ikke pris for NOBB {nobb} på {url}")
            return None

        return {
            'pris': pris,
            'forpris': forpris,
            'lagerstatus': lagerstatus,
            'url': url,
            'butikk': 'Maxbo Sinsen',
        }

    except PlaywrightTimeout:
        log.error(f"Timeout ved henting av {url}")
        return None
    except Exception as e:
        log.error(f"Feil ved {url}: {e}")
        return None


async def scrape_maxbo(produkter: list[dict], butikk: str = 'Sinsen') -> dict:
    """Scraper Maxbo for alle produkter med kjent URL. Returnerer {nobb: prisdata}."""
    resultater = {}

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            locale='nb-NO',
            user_agent='Mozilla/5.0 (Maxbo Prismatrise; intern bruk)',
        )
        page = await context.new_page()

        # Gå til forsiden og velg butikk én gang
        await page.goto('https://www.maxbo.no/', wait_until='domcontentloaded')
        await page.wait_for_timeout(1500)
        await velg_butikk(page, butikk)

        # Loop produktene
        for i, prod in enumerate(produkter, 1):
            nobb = prod['nobb']
            url = NOBB_TIL_URL.get(nobb)
            if not url:
                log.warning(f"[{i}/{len(produkter)}] NOBB {nobb} mangler URL i NOBB_TIL_URL — hopper over")
                continue

            log.info(f"[{i}/{len(produkter)}] {prod['produktnavn'][:50]}")
            data = await scrape_produkt(page, nobb, url)
            if data:
                resultater[nobb] = data

            # Rate limiting — vær snill med eget nettsted
            await asyncio.sleep(1.5)

        await browser.close()

    return resultater
