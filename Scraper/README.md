# Scraper

Daglig scraping av priser fra Maxbo, Monter, Obs Bygg og Byggmakker.

## Oppsett

```bash
cd scraper
python3 -m venv venv
source venv/bin/activate          # Mac/Linux
# venv\Scripts\activate            # Windows

pip install -r requirements.txt
playwright install chromium
```

## Kjøring

```bash
# Full kjøring (alle produkter, alle kjeder)
python scrape.py

# Bare første 5 produkter (for testing)
python scrape.py --limit 5

# Bare én kjede
python scrape.py --kjede obs_bygg --limit 5
python scrape.py --kjede byggmakker --limit 5
python scrape.py --kjede maxbo --limit 1
python scrape.py --kjede monter --limit 1
```

Scraperen skriver ferdig `data.json` til prosjektroten (én mappe opp), som er det dashboardet leser.

## Anbefalt rekkefølge for første gangs oppsett

1. **Test Byggmakker først.** Den er enklest fordi NOBB står i URL-en og prisene er i HTML.
   ```bash
   python scrape.py --kjede byggmakker --limit 3
   ```
   Se i loggen at du får treff. Hvis selectors er feil, er det her du ser det først.

2. **Test Obs Bygg.** Litt vanskeligere fordi vi går via søkesiden.
   ```bash
   python scrape.py --kjede obs_bygg --limit 3
   ```

3. **Bygg NOBB → URL-tabellen for Maxbo og Monter.** Disse trenger Playwright og må vite eksakt produkt-URL. Se under.

4. **Test Maxbo og Monter med Playwright.** Disse er tregere og krever justering av selectors.
   ```bash
   python scrape.py --kjede maxbo --limit 1
   python scrape.py --kjede monter --limit 1
   ```

5. **Full kjøring** når alle fire fungerer enkeltvis.

## Bygg NOBB → URL-tabellen for Maxbo

Maxbo og Monter har ikke NOBB direkte i URL-en, så vi trenger en oppslagstabell. Tre måter å bygge denne på:

**A) Manuelt for de første 40 produktene.** Søk etter hvert produkt på maxbo.no, kopier URL-en, lim inn i `kjeder/maxbo.py` i `NOBB_TIL_URL`-dictet. Dette tar 30 minutter og er fint for å komme i gang.

**B) Crawl Maxbos sitemap.** `https://www.maxbo.no/sitemap.xml` (hvis tilgjengelig) inneholder alle produkt-URL-er. Et engangsskript kan hente alle URL-ene, besøke hver, plukke ut NOBB fra HTML, og bygge tabellen.

**C) Eksport fra PIM.** Hvis Maxbo har et PIM-system med URL-er, kan en eksport gi NOBB → URL-mapping direkte. Spør IT.

Tilsvarende for Monter via `https://www.monter.no/sitemap.xml`.

## GJETNINGER som må verifiseres

Jeg har gjettet på selectors og pris-parsing-mønstre basert på det jeg så da jeg analyserte sidene. Du må sannsynligvis justere:

**Maxbo** (`kjeder/maxbo.py`):
- Knapp for butikkvalg — testet ikke om "Velg din butikk"-teksten er presis nok
- Pris-pattern — bruker regex på hele HTML, kan plukke feil tall hvis siden har mange tall
- Lagerstatus — heuristikk basert på tekst, kan gi false positives

**Monter** (`kjeder/monter.py`):
- Samme typer gjetninger som Maxbo
- "Velg lagersted"-knappen kan være skjult i en dropdown

**Obs Bygg** (`kjeder/obsbygg.py`):
- Søke-URL-en `/sok?q=NOBB` — bekreftet at søk finnes, men ikke testet med NOBB direkte
- Pris-parser bruker regex som kan trenge justering

**Byggmakker** (`kjeder/byggmakker.py`):
- Bekreftet at NOBB er i URL-mønsteret `/produkt/[slug]/[NOBB]`
- Selektor for førpris vs hovedpris kan trenge justering

## Feilsøking

**"Fant ikke pris"** — siden er sannsynligvis lastet, men selectoren matcher ikke. Kjør med `--kjede X --limit 1` og legg til debug-utskrifter:

```python
import logging
logging.getLogger().setLevel(logging.DEBUG)
```

Eller åpne en Playwright-debug-sesjon:

```python
browser = await p.chromium.launch(headless=False, slow_mo=500)
```

Da ser du nettleseren mens den jobber.

**Timeout** — øk `timeout=15000` til 30000 hvis nettverket er tregt.

**Cloudflare/bot-blokkering** — hvis dere får 403 eller captcha, må vi vurdere om brukeragent-strengen må endres, eller om dere trenger å kjøre fra en spesifikk IP. Foreløpig identifiserer scraperen seg ærlig som "Maxbo Prismatrise; intern bruk".

## Etisk og juridisk

Scraperen er rate-limited (0.8–2 sekunder mellom forespørsler) og identifiserer seg selv. Det er en lavbelastnings-scraping av offentlige priser.

Send en kort e-post til kjedene hvis dere planlegger å scale opp til mange tusen produkter. For 40–80 produkter daglig er det helt innenfor det som regnes som akseptabel bruk.

For Maxbo (eget nettsted): formelt OK, men snakk gjerne med IT/webteam før produksjon.

## GitHub Actions

Når scraperen kjører lokalt, sett den opp som scheduled workflow:

```yaml
# .github/workflows/scrape.yml
name: Daglig prisscraping
on:
  schedule:
    - cron: '0 3 * * *'  # 04:00 norsk tid
  workflow_dispatch:    # Tillater manuell trigger

jobs:
  scrape:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - name: Installer avhengigheter
        run: |
          cd scraper
          pip install -r requirements.txt
          playwright install --with-deps chromium
      - name: Kjør scraper
        run: |
          cd scraper
          python scrape.py
      - name: Commit og push data.json
        run: |
          git config user.name "scrape-bot"
          git config user.email "scrape-bot@maxbo.no"
          git add data.json
          git diff --cached --quiet || git commit -m "Snapshot $(date +%F)"
          git push
```
