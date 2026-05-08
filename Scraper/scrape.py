"""
Maxbo Prismatrise — daglig prisscraping

Kjører alle fire kjede-scrapere, samler resultatene, skriver data.json.

Bruk:
    python scrape.py                    # full kjøring, alle produkter
    python scrape.py --limit 5          # bare første 5 produkter (for testing)
    python scrape.py --kjede maxbo      # bare én kjede (for testing)

Avhengigheter:
    pip install playwright requests beautifulsoup4
    playwright install chromium
"""

import argparse
import asyncio
import csv
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

from kjeder.maxbo import scrape_maxbo
from kjeder.monter import scrape_monter
from kjeder.obsbygg import scrape_obsbygg
from kjeder.byggmakker import scrape_byggmakker


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%H:%M:%S'
)
log = logging.getLogger('scrape')


PROSJEKTROT = Path(__file__).parent.parent
PRODUKTER_CSV = PROSJEKTROT / 'produkter.csv'
DATA_JSON = PROSJEKTROT / 'data.json'


def les_produkter(limit=None):
    """Leser produkter.csv og returnerer liste av dicts. Hopper over rader uten NOBB."""
    produkter = []
    with open(PRODUKTER_CSV, encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if not row.get('nobb', '').strip():
                log.warning(f"Hopper over (mangler NOBB): {row.get('produktnavn')}")
                continue
            produkter.append({
                'nobb': row['nobb'].strip(),
                'kategori': row['kategori'].strip(),
                'produktnavn': row['produktnavn'].strip(),
                'leverandor': row['leverandor'].strip(),
                'enhet': row['enhet'].strip(),
            })
    if limit:
        produkter = produkter[:limit]
    log.info(f"Leste {len(produkter)} produkter med NOBB")
    return produkter


async def kjor_alle(produkter, valgte_kjeder):
    """
    Kjører de Playwright-baserte scraperne (Maxbo, Monter) i én browser-instans.
    Kjører de HTTP-baserte (Obs Bygg, Byggmakker) parallelt.
    """
    resultater_per_kjede = {}

    # Playwright-scrapere — kjøres sekvensielt i samme browser for å gjenbruke butikkvalg
    if 'maxbo' in valgte_kjeder:
        log.info("=== Maxbo (Playwright, butikk: Sinsen) ===")
        resultater_per_kjede['maxbo'] = await scrape_maxbo(produkter, butikk='Sinsen')

    if 'monter' in valgte_kjeder:
        log.info("=== Monter (Playwright, butikk: Alnabru) ===")
        resultater_per_kjede['monter'] = await scrape_monter(produkter, butikk='Alnabru')

    # HTTP-scrapere — kan kjøres parallelt
    http_oppgaver = []
    if 'obs_bygg' in valgte_kjeder:
        log.info("=== Obs Bygg (HTTP) ===")
        http_oppgaver.append(('obs_bygg', scrape_obsbygg(produkter)))
    if 'byggmakker' in valgte_kjeder:
        log.info("=== Byggmakker (HTTP) ===")
        http_oppgaver.append(('byggmakker', scrape_byggmakker(produkter)))

    if http_oppgaver:
        results = await asyncio.gather(*[oppg for _, oppg in http_oppgaver])
        for (navn, _), res in zip(http_oppgaver, results):
            resultater_per_kjede[navn] = res

    return resultater_per_kjede


def kombiner(produkter, resultater_per_kjede):
    """Slår sammen produktinfo og priser fra hver kjede til endelig data.json-format."""
    snapshot_dato = datetime.now().strftime('%Y-%m-%d')
    rader = []

    for prod in produkter:
        nobb = prod['nobb']
        priser = {}
        for kjede in ['maxbo', 'monter', 'obs_bygg', 'byggmakker']:
            kjede_res = resultater_per_kjede.get(kjede, {})
            priser[kjede] = kjede_res.get(nobb)  # None hvis ikke funnet

        rader.append({
            'snapshot_dato': snapshot_dato,
            'nobb': nobb,
            'kategori': prod['kategori'],
            'produktnavn': prod['produktnavn'],
            'leverandor': prod['leverandor'],
            'enhet': prod['enhet'],
            'priser': priser,
        })
    return rader


def skriv_data(rader):
    """Skriver data.json. Backup av forrige fil først."""
    if DATA_JSON.exists():
        backup = DATA_JSON.with_suffix('.json.forrige')
        DATA_JSON.replace(backup)
        log.info(f"Forrige data.json sikret som {backup.name}")
    DATA_JSON.write_text(
        json.dumps(rader, ensure_ascii=False, indent=2),
        encoding='utf-8'
    )
    log.info(f"Skrev {DATA_JSON} ({len(rader)} produkter)")


def oppsummer(rader):
    """Logger oversikt over hvor mange treff vi fikk per kjede."""
    log.info("=== Oppsummering ===")
    for kjede in ['maxbo', 'monter', 'obs_bygg', 'byggmakker']:
        treff = sum(1 for r in rader if r['priser'].get(kjede) is not None)
        andel = treff / len(rader) * 100 if rader else 0
        log.info(f"{kjede:12s}: {treff}/{len(rader)} ({andel:.0f}%)")


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--limit', type=int, help='Begrens antall produkter (testing)')
    ap.add_argument(
        '--kjede',
        choices=['maxbo', 'monter', 'obs_bygg', 'byggmakker', 'alle'],
        default='alle',
        help='Kjør bare én kjede (testing)'
    )
    args = ap.parse_args()

    valgte = ['maxbo', 'monter', 'obs_bygg', 'byggmakker'] if args.kjede == 'alle' else [args.kjede]

    produkter = les_produkter(limit=args.limit)
    if not produkter:
        log.error("Ingen produkter med NOBB å scrape — sjekk produkter.csv")
        sys.exit(1)

    resultater = await kjor_alle(produkter, valgte)
    rader = kombiner(produkter, resultater)
    skriv_data(rader)
    oppsummer(rader)


if __name__ == '__main__':
    asyncio.run(main())
