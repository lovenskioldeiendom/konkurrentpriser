"""
Monter scraper — Playwright-basert.

GJETNINGER:
- "Velg lagersted"-knappen er øverst, åpner et panel
- Pris vises etter at lagersted er valgt (priser varierer mellom lagre)
- NOBB står som "NOBB [tall]" på produktsiden

URL-mønster: må slås opp via NOBB → URL-tabell, eller via Monters søke-API.
Monter har ikke NOBB i URL-en, men de har ofte produktnavn som speed.
"""

import asyncio
import logging
import re

from playwright.async_api import async_playwright, Page, TimeoutError as PlaywrightTimeout

log = logging.getLogger('monter')

# Bygg denne over tid eller via Monter sin sitemap.
# Eksempel på mønster: https://www.monter.no/[kategori]/[underkategori]/[produkt-slug]
NOBB_TIL_URL = {
    '25410978': 'https://www.monter.no/trelast/terrassebord/impregnert-terrassebord/terrassebord-impregnert-furu-klasse-1-28x120-mm',
    # Fyll på etter hvert. Tips: monter.no/sitemap.xml kan inneholde alle produkt-URL-er.
}


async def velg_lagersted(page: Page, lagersted: str):
    """GJETNING: lagerstedsvalg er en knapp/dropdown med tekst 'Velg lagersted'."""
    try:
        await page.get_by_text("Velg lagersted", exact=False).first.click(timeout=5000)
        await page.wait_for_timeout(800)

        # Skriv inn lagernavn i søkefeltet hvis det finnes
        search = page.locator('input[type="search"], input[placeholder*="søk" i]').first
        if await search.count() > 0:
            await search.fill(lagersted)
            await page.wait_for_timeout(500)

        await page.get_by_text(re.compile(f"Mont[ée]r {lagersted}", re.IGNORECASE)).first.click(timeout=5000)
        await page.wait_for_timeout(1500)
        log.info(f"Valgte lagersted: Montér {lagersted}")
        return True
    except PlaywrightTimeout:
        log.warning("Klarte ikke velge lagersted — fortsetter uten")
        return False


async def scrape_produkt(page: Page, nobb: str, url: str) -> dict | None:
    try:
        await page.goto(url, wait_until='domcontentloaded', timeout=15000)
        await page.wait_for_timeout(2500)
        html = await page.content()

        # Pris
        pris = None
        forpris = None
        for pattern in [
            r'(\d[\d\s\.]*,\d{2})\s*kr',
            r'(\d[\d\s\.]*)\s*kr(?!\w)',
        ]:
            matches = re.findall(pattern, html, re.IGNORECASE)
            tall = []
            for m in matches[:5]:
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

        # Lagerstatus
        lagerstatus = 'ukjent'
        if re.search(r'ikke\s+p[åa]\s+lager', html, re.IGNORECASE):
            lagerstatus = 'ikke_paa_lager'
        elif re.search(r'p[åa]\s+lager', html, re.IGNORECASE):
            lagerstatus = 'paa_lager'

        if pris is None:
            log.warning(f"Fant ikke pris for NOBB {nobb}")
            return None

        return {
            'pris': pris,
            'forpris': forpris,
            'lagerstatus': lagerstatus,
            'url': url,
            'butikk': 'Montér Alnabru',
        }
    except Exception as e:
        log.error(f"Feil ved {url}: {e}")
        return None


async def scrape_monter(produkter: list[dict], butikk: str = 'Alnabru') -> dict:
    resultater = {}
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            locale='nb-NO',
            user_agent='Mozilla/5.0 (Maxbo Prismatrise; intern bruk)',
        )
        page = await context.new_page()

        await page.goto('https://www.monter.no/', wait_until='domcontentloaded')
        await page.wait_for_timeout(1500)
        await velg_lagersted(page, butikk)

        for i, prod in enumerate(produkter, 1):
            nobb = prod['nobb']
            url = NOBB_TIL_URL.get(nobb)
            if not url:
                log.warning(f"[{i}/{len(produkter)}] NOBB {nobb} mangler URL — hopper over")
                continue

            log.info(f"[{i}/{len(produkter)}] {prod['produktnavn'][:50]}")
            data = await scrape_produkt(page, nobb, url)
            if data:
                resultater[nobb] = data

            await asyncio.sleep(2.0)  # Vær snill — eksternt nettsted

        await browser.close()
    return resultater
