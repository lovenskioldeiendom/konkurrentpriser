# Maxbo Prismatrise

Internt dashboard for daglig overvåkning av priser hos Monter, Obs Bygg og Byggmakker, sammenlignet med Maxbo.

## Filer

```
maxbo-prismatrise/
├── index.html      # Dashboardet (selvstendig, ingen build-step)
├── data.json       # Dagens snapshot — overskrives av scraperen
├── produkter.csv   # Produktkatalog (NOBB-numre, kategorier)
└── README.md       # Denne filen
```

## Datamodell

`data.json` er en flat liste der hver post er ett produkt med priser fra alle fire kjeder:

```json
{
  "snapshot_dato": "2026-05-08",
  "nobb": "5709636009917",
  "kategori": "Plater",
  "produktnavn": "Gipsplate Norgips Standard 12.5x1200x2400",
  "leverandor": "Norgips",
  "enhet": "stk",
  "priser": {
    "maxbo":      { "pris": 149.00, "forpris": null, "lagerstatus": "paa_lager", "url": "...", "butikk": "Maxbo Sinsen" },
    "monter":     { "pris": 152.00, "forpris": null, "lagerstatus": "paa_lager", "url": "...", "butikk": "Monter Alnabru" },
    "obs_bygg":   { "pris": 145.00, "forpris": null, "lagerstatus": "paa_lager", "url": "..." },
    "byggmakker": { "pris": 152.35, "forpris": null, "lagerstatus": "paa_lager", "url": "..." }
  }
}
```

Felter:
- `pris`: gjeldende pris i NOK (inkl. mva)
- `forpris`: opprinnelig pris ved kampanje, eller `null`
- `lagerstatus`: `"paa_lager"` | `"ikke_paa_lager"` | `"ukjent"`
- `url`: dyplenke til produktet hos kjeden
- `butikk`: kun relevant for Maxbo og Monter (lokal pris)

Hvis et produkt mangler hos en kjede, sett hele kjede-objektet til `null` eller utelat det. Dashboardet håndterer begge.

## Scraperens ansvar

Scraperen kjører som en separat jobb (Playwright) og produserer `data.json` daglig. Forslag til oppsett:

- **Maxbo**: hent fra eget PIM-system / ERP — ikke scrape eget nettsted
- **Monter**: Playwright med valgt lagersted = Alnabru. Pris hentes fra produktsidens DOM etter at lagerstedsvelgeren er klikket
- **Obs Bygg**: enkel HTTP + BeautifulSoup mot kategorisidene (priser ligger i HTML-en)
- **Byggmakker**: enkel HTTP + BeautifulSoup mot produktsidene via NOBB i URL (priser i HTML-en)

Matching skjer på NOBB. Ved manglende treff: logg som `null` og la dashboardet vise "ikke tilgjengelig".

## Lokal kjøring

```bash
# Du trenger en enkel HTTP-server fordi index.html bruker fetch()
cd maxbo-prismatrise
python3 -m http.server 8000
# Aapne http://localhost:8000
```

Du kan ikke åpne `index.html` direkte fra disk (file://) — `fetch()` blokkeres av CORS.

## Deploy til GitHub Pages

```bash
# 1. Opprett repo
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin git@github.com:DERES-ORG/maxbo-prismatrise.git
git push -u origin main

# 2. Aktiver Pages i GitHub:
#    Settings → Pages → Source: "Deploy from a branch"
#    Branch: main, mappe: / (root)

# 3. Etter ~1 minutt er siden tilgjengelig paa:
#    https://DERES-ORG.github.io/maxbo-prismatrise/
```

For internt bruk: bruk et privat repo og inviter relevante kolleger. GitHub Pages fungerer på private repos for Pro/Team/Enterprise-kontoer.

## Daglig oppdatering via GitHub Actions

Scraperen kan kjøre som en scheduled workflow. Skissert oppsett (legg i `.github/workflows/scrape.yml`):

```yaml
name: Daglig prisscraping
on:
  schedule:
    - cron: '0 3 * * *'  # 04:00 norsk tid (UTC+1)
  workflow_dispatch:

jobs:
  scrape:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - run: pip install playwright requests beautifulsoup4
      - run: playwright install chromium
      - run: python scrape.py    # produserer data.json
      - run: |
          git config user.name "scrape-bot"
          git config user.email "scrape@maxbo.no"
          git add data.json
          git commit -m "Snapshot $(date +%F)" || echo "Ingen endringer"
          git push
```

Når `data.json` commitres, oppdateres siden automatisk via Pages.

## Utvidelse

For å øke fra 40 til 80+ produkter: legg til rader i `produkter.csv` og oppdater scraperens kildeliste. Dashboardet skalerer automatisk.

For å legge til en ny kjede: utvid `KJEDER`-arrayet i `index.html`, legg til kolonne i tabellen, og oppdater scraperen.

## Begrensninger og åpne spørsmål

- Daglig scraping er kanskje overkill for trelast og volumvarer. Vurder ukentlig scraping for stabile kategorier og daglig bare for sesong-/kampanjevarer (hage, elektroverktøy).
- Lokale priser hos Monter og Maxbo vises kun for én Oslo-butikk. Hvis dere vil ha flere geografier, må datamodellen utvides til å inkludere flere butikker per produkt.
- Per-meter vs per-stykk vs per-pakke-enheter må normaliseres i scraperen før prisene kan sammenlignes meningsfullt. Sjekk alltid `enhet`-feltet matcher før dere stoler på diff-tallet.
