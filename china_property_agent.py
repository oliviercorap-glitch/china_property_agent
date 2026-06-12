"""
Agent immobilier chinois — Secteur property, Evergrande, politiques logement
"""
import os, json, logging, hashlib
from datetime import datetime
from pathlib import Path
import requests, anthropic
import xml.etree.ElementTree as ET
from dotenv import load_dotenv

load_dotenv()
LOG_FILE  = Path("logs/agent_property.log")
SEEN_FILE = Path("seen_property.json")
Path("logs").mkdir(exist_ok=True)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler(LOG_FILE, encoding="utf-8")])
log = logging.getLogger(__name__)

SOURCES = [
    {"nom": "Caixin — Immobilier & finance", "url": "https://www.caixinglobal.com/rss/all.xml",
     "tags": ["property", "real estate", "Evergrande", "housing", "developer", "mortgage"]},
    {"nom": "BBC Business — Immobilier Chine", "url": "https://feeds.bbci.co.uk/news/business/rss.xml",
     "tags": ["China property", "real estate", "Evergrande", "housing market", "developer"]},
    {"nom": "SCMP — Property", "url": "https://www.scmp.com/rss/5/feed",
     "tags": ["property", "real estate", "housing", "developer", "Evergrande", "mortgage", "land"]},
    {"nom": "World Bank — Chine macro", "url": "https://blogs.worldbank.org/rss.xml",
     "tags": ["China property", "real estate", "housing", "construction", "investment"]},
    {"nom": "IMF — Risques financiers Chine", "url": "https://www.imf.org/en/News/rss?language=eng",
     "tags": ["China property", "real estate", "financial risk", "developer", "housing"]},
]

KEYWORDS = ["property", "real estate", "housing", "developer", "Evergrande", "Country Garden",
            "Vanke", "mortgage", "land sales", "construction", "home prices", "property tax",
            "housing market", "ghost city", "debt", "default", "rescue", "bailout",
            "property crisis", "presale", "new home", "second-hand", "tier-1 city"]

SYSTEM_PROMPT = """Tu es un analyste spécialisé dans le secteur immobilier chinois,
conseiller d'un CFO de multinationale étrangère dont l'activité peut être impactée
par la santé du secteur immobilier en Chine (demande de construction, activité économique,
confiance des consommateurs, commandes de matériel industriel lié aux chantiers).

Analyse les signaux immobiliers et leur impact :
- Santé des grands promoteurs (défauts, restructurations, ventes)
- Politiques gouvernementales de soutien ou restriction du marché
- Indicateurs de prix et volumes de transactions
- Impact sur la demande de matériel industriel et d'infrastructure
- Risques systémiques pour l'économie chinoise

Niveau : CRITIQUE / ÉLEVÉ / MODÉRÉ / INFO
En français, orienté impact business pour le CFO.
"""

def charger_vus():
    if SEEN_FILE.exists():
        with open(SEEN_FILE) as f: return set(json.load(f))
    return set()

def sauvegarder_vus(vus):
    with open(SEEN_FILE, "w") as f: json.dump(list(vus), f)

def fetch_rss(source):
    articles = []
    try:
        resp = requests.get(source["url"], timeout=15,
            headers={"User-Agent": "Mozilla/5.0 (compatible; CFO-PropertyAgent/1.0)"})
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
        items = root.findall(".//item") or root.findall(".//{http://www.w3.org/2005/Atom}entry")
        for item in items[:20]:
            titre = (getattr(item.find("title"), "text", "") or
                     getattr(item.find("{http://www.w3.org/2005/Atom}title"), "text", "") or "").strip()
            lien  = (getattr(item.find("link"), "text", "") or
                     getattr(item.find("{http://www.w3.org/2005/Atom}link"), "attrib", {}).get("href", "") or "").strip()
            desc  = (getattr(item.find("description"), "text", "") or
                     getattr(item.find("{http://www.w3.org/2005/Atom}summary"), "text", "") or "").strip()
            date  = (getattr(item.find("pubDate"), "text", "") or
                     getattr(item.find("{http://www.w3.org/2005/Atom}updated"), "text", "") or "").strip()
            if titre:
                articles.append({"source": source["nom"], "titre": titre, "lien": lien,
                                  "desc": desc[:500], "date": date,
                                  "id": hashlib.md5((titre+lien).encode()).hexdigest()})
    except Exception as e:
        log.warning(f"Erreur {source['nom']} : {e}")
    return articles

def filtrer(articles, vus):
    return [a for a in articles if a["id"] not in vus and
            any(kw.lower() in (a["titre"]+a["desc"]).lower() for kw in KEYWORDS)]

def analyser(articles):
    if not articles: return "Aucun signal immobilier significatif aujourd'hui."
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    date_str = datetime.now().strftime("%d %B %Y")
    txt = "\n".join(f"[{i+1}] {a['source']}\n    {a['titre']}\n    {a['desc']}\n    {a['lien']}"
                    for i, a in enumerate(articles))
    prompt = (f"Veille immobilier Chine — {date_str}\n{len(articles)} signaux\n\n{txt}\n\n"
              "Pour chaque signal : NIVEAU | ACTEUR/INDICATEUR | LECTURE DU MARCHÉ | IMPACT BUSINESS CFO\n"
              "Termine par : ÉTAT DU SECTEUR PROPERTY + IMPACT SUR DEMANDE INDUSTRIELLE")
    msg = client.messages.create(model="claude-sonnet-4-6", max_tokens=3000, system=SYSTEM_PROMPT,
                                  messages=[{"role": "user", "content": prompt}])
    return msg.content[0].text

def executer_agent():
    log.info("Démarrage agent immobilier Chine...")
    try:
        vus = charger_vus()
        tous = []
        for s in SOURCES:
            arts = fetch_rss(s)
            log.info(f"{s['nom']} : {len(arts)} articles")
            tous.extend(arts)
        pertinents = filtrer(tous, vus)
        log.info(f"Pertinents : {len(pertinents)}")
        analyse = analyser(pertinents)
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        rapport = "\n".join(["="*62, f"  VEILLE IMMOBILIER CHINE — {now}",
                             "  Promoteurs | Prix | Politiques | Demande", "="*62,
                             f"\n  {len(pertinents)} signal(s) détecté(s)\n", "-"*62,
                             "  ANALYSE & IMPACT BUSINESS", "-"*62, analyse, "="*62])
        Path("rapports").mkdir(exist_ok=True)
        fichier = Path("rapports") / f"property_{datetime.now().strftime('%Y%m%d_%H%M')}.txt"
        fichier.write_text(rapport, encoding="utf-8")
        print(rapport)
        for a in pertinents: vus.add(a["id"])
        sauvegarder_vus(vus)
        log.info("Terminé.")
    except Exception as e:
        log.exception(f"Erreur : {e}")

if __name__ == "__main__":
    executer_agent()
