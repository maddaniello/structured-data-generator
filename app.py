import streamlit as st
import requests
from bs4 import BeautifulSoup
import json
import xml.etree.ElementTree as ET
from urllib.parse import urljoin, urlparse
import openai
import re
from typing import List, Dict, Any
import time

# Configurazione della pagina
st.set_page_config(
    page_title="Generatore Dati Strutturati SEO",
    page_icon="🔍",
    layout="wide"
)

# Dati strutturati più comuni supportati da Google
COMMON_STRUCTURED_DATA = {
    "Product": "Prodotto",
    "Article": "Articolo",
    "LocalBusiness": "Attività Locale",
    "Organization": "Organizzazione",
    "Person": "Persona",
    "Recipe": "Ricetta",
    "Event": "Evento",
    "FAQ": "FAQ",
    "HowTo": "Come Fare",
    "JobPosting": "Offerta di Lavoro",
    "Review": "Recensione",
    "BreadcrumbList": "Breadcrumb",
    "VideoObject": "Video",
    "ImageObject": "Immagine",
    "WebSite": "Sito Web"
}

class SchemaOrgAnalyzer:
    """Classe per analizzare e suggerire dati strutturati basati su Schema.org"""
    
    def __init__(self):
        self.schema_types = self._load_common_schema_types()
    
    def _load_common_schema_types(self):
        """Carica i tipi di schema più comuni con le loro proprietà"""
        return {
            "Product": {
                "required": ["name"],
                "recommended": ["description", "image", "brand", "offers", "aggregateRating", "review"]
            },
            "Article": {
                "required": ["headline", "datePublished"],
                "recommended": ["author", "image", "dateModified", "publisher"]
            },
            "LocalBusiness": {
                "required": ["name", "address"],
                "recommended": ["telephone", "openingHours", "geo", "priceRange", "aggregateRating"]
            },
            "Organization": {
                "required": ["name"],
                "recommended": ["url", "logo", "contactPoint", "sameAs", "address"]
            },
            "Recipe": {
                "required": ["name", "recipeIngredient", "recipeInstructions"],
                "recommended": ["image", "author", "datePublished", "description", "prepTime", "cookTime", "nutrition"]
            },
            "Event": {
                "required": ["name", "startDate", "location"],
                "recommended": ["description", "endDate", "organizer", "offers", "performer"]
            }
        }

class WebScraper:
    """Classe per il web scraping e l'analisi delle pagine"""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
    
    def scrape_sitemap(self, sitemap_url: str) -> List[str]:
        """Estrae gli URL da una sitemap XML"""
        try:
            response = self.session.get(sitemap_url, timeout=10)
            response.raise_for_status()
            
            root = ET.fromstring(response.content)
            urls = []
            
            # Gestisce namespace XML
            namespaces = {'ns': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
            
            for url in root.findall('.//ns:url/ns:loc', namespaces):
                if url.text:
                    urls.append(url.text.strip())
            
            return urls[:50]  # Limita a 50 URL per performance
            
        except Exception as e:
            st.error(f"Errore nel parsing della sitemap: {str(e)}")
            return []
    
    def scrape_page(self, url: str) -> Dict[str, Any]:
        """Estrae informazioni da una singola pagina"""
        try:
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Estrae informazioni base
            page_info = {
                'url': url,
                'title': soup.title.string.strip() if soup.title else '',
                'meta_description': '',
                'headings': [],
                'images': [],
                'links': [],
                'content_type': self._detect_content_type(soup),
                'structured_data': self._extract_existing_structured_data(soup)
            }
            
            # Meta description
            meta_desc = soup.find('meta', attrs={'name': 'description'})
            if meta_desc:
                page_info['meta_description'] = meta_desc.get('content', '')
            
            # Headings
            for i in range(1, 7):
                headings = soup.find_all(f'h{i}')
                for h in headings[:5]:  # Max 5 per livello
                    page_info['headings'].append({
                        'level': i,
                        'text': h.get_text().strip()
                    })
            
            # Immagini
            images = soup.find_all('img')
            for img in images[:10]:  # Max 10 immagini
                src = img.get('src')
                if src:
                    page_info['images'].append({
                        'src': urljoin(url, src),
                        'alt': img.get('alt', ''),
                        'title': img.get('title', '')
                    })
            
            return page_info
            
        except Exception as e:
            st.error(f"Errore nello scraping di {url}: {str(e)}")
            return {'url': url, 'error': str(e)}
    
    def _detect_content_type(self, soup: BeautifulSoup) -> str:
        """Rileva il tipo di contenuto della pagina"""
        # Rileva prodotti
        if soup.find_all(['div', 'span'], class_=re.compile(r'price|prezzo', re.I)):
            return 'product'
        
        # Rileva articoli
        if soup.find_all(['article', 'div'], class_=re.compile(r'article|post|blog', re.I)):
            return 'article'
        
        # Rileva eventi
        if soup.find_all(['div', 'span'], class_=re.compile(r'event|evento|data', re.I)):
            return 'event'
        
        # Rileva business locali
        if soup.find_all(['div', 'span'], class_=re.compile(r'address|indirizzo|contact', re.I)):
            return 'local_business'
        
        return 'webpage'
    
    def _extract_existing_structured_data(self, soup: BeautifulSoup) -> List[Dict]:
        """Estrae dati strutturati esistenti dalla pagina"""
        structured_data = []
        
        # JSON-LD
        json_ld_scripts = soup.find_all('script', type='application/ld+json')
        for script in json_ld_scripts:
            try:
                data = json.loads(script.string)
                structured_data.append({
                    'type': 'json-ld',
                    'data': data
                })
            except:
                pass
        
        return structured_data

class StructuredDataGenerator:
    """Classe per generare dati strutturati usando OpenAI"""
    
    def __init__(self, api_key: str):
        self.client = openai.OpenAI(api_key=api_key)
    
    def suggest_structured_data(self, pages_info: List[Dict]) -> Dict[str, List[str]]:
        """Suggerisce tipi di dati strutturati basandosi sull'analisi delle pagine"""
        
        # Prepara il prompt per OpenAI
        pages_summary = []
        for page in pages_info[:5]:  # Analizza max 5 pagine
            if 'error' not in page:
                summary = f"URL: {page['url']}\nTitolo: {page['title']}\nTipo: {page['content_type']}\nHeadings: {[h['text'] for h in page['headings'][:3]]}"
                pages_summary.append(summary)
        
        prompt = f"""Analizza queste pagine web e suggerisci i migliori tipi di dati strutturati Schema.org da implementare:

{chr(10).join(pages_summary)}

Fornisci suggerimenti specifici per ogni tipo di pagina identificata, considerando:
1. I tipi di dati strutturati più efficaci per la SEO
2. La compatibilità con Google Rich Snippets
3. Le best practice di Schema.org

Rispondi in formato JSON con questa struttura:
{{
    "suggestions": [
        {{
            "schema_type": "Product",
            "pages": ["url1", "url2"],
            "reason": "Motivo della raccomandazione",
            "priority": "high|medium|low"
        }}
    ]
}}"""
        
        try:
            response = self.client.chat.completions.create(
                model="gpt-4",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3
            )
            
            result = json.loads(response.choices[0].message.content)
            return result
            
        except Exception as e:
            st.error(f"Errore nella generazione dei suggerimenti: {str(e)}")
            return {"suggestions": []}
    
    def generate_structured_data(self, page_info: Dict, schema_type: str, custom_schema: str = None) -> str:
        """Genera dati strutturati per una pagina specifica"""
        
        schema_to_use = custom_schema if custom_schema else schema_type
        
        prompt = f"""Genera dati strutturati JSON-LD ottimizzati per SEO utilizzando lo schema "{schema_to_use}" per questa pagina:

URL: {page_info['url']}
Titolo: {page_info['title']}
Meta Description: {page_info.get('meta_description', '')}
Headings: {page_info.get('headings', [])}
Immagini: {page_info.get('images', [])}

Requisiti:
1. Utilizza il formato JSON-LD
2. Includi tutte le proprietà obbligatorie per lo schema {schema_to_use}
3. Aggiungi proprietà raccomandate quando possibile
4. Ottimizza per Google Rich Snippets
5. Usa URL assoluti per le immagini
6. Segui le best practice di Schema.org

Genera un JSON-LD completo e valido."""
        
        try:
            response = self.client.chat.completions.create(
                model="gpt-4",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2
            )
            
            return response.choices[0].message.content
            
        except Exception as e:
            st.error(f"Errore nella generazione dei dati strutturati: {str(e)}")
            return ""

def main():
    st.title("🔍 Generatore Dati Strutturati SEO")
    st.markdown("*Ottimizza la tua SEO con dati strutturati Schema.org generati automaticamente*")
    
    # Sidebar per configurazione
    with st.sidebar:
        st.header("⚙️ Configurazione")
        
        # Input API Key OpenAI
        api_key = st.text_input(
            "API Key OpenAI",
            type="password",
            help="Inserisci la tua API key di OpenAI per utilizzare l'app"
        )
        
        if not api_key:
            st.warning("⚠️ Inserisci la tua API Key OpenAI per continuare")
            st.stop()
    
    # Inizializza le classi
    scraper = WebScraper()
    schema_analyzer = SchemaOrgAnalyzer()
    generator = StructuredDataGenerator(api_key)
    
    # Tab principale
    tab1, tab2 = st.tabs(["📊 Analisi e Suggerimenti", "🛠️ Generazione Dati Strutturati"])
    
    with tab1:
        st.header("Analisi Sito e Suggerimenti")
        st.markdown("Analizza il tuo sito per ricevere suggerimenti sui migliori dati strutturati da implementare.")
        
        # Input methods
        input_method = st.radio(
            "Scegli il metodo di analisi:",
            ["Sitemap XML", "URL Specifici", "Codice Sorgente"]
        )
        
        if input_method == "Sitemap XML":
            sitemap_url = st.text_input("URL della Sitemap", placeholder="https://esempio.com/sitemap.xml")
            
            if st.button("Analizza Sitemap", type="primary"):
                if sitemap_url:
                    with st.spinner("Analizzando la sitemap..."):
                        urls = scraper.scrape_sitemap(sitemap_url)
                        
                        if urls:
                            st.success(f"Trovati {len(urls)} URL nella sitemap")
                            
                            # Analizza le prime pagine
                            pages_info = []
                            progress_bar = st.progress(0)
                            
                            for i, url in enumerate(urls[:10]):  # Analizza max 10 pagine
                                page_info = scraper.scrape_page(url)
                                pages_info.append(page_info)
                                progress_bar.progress((i + 1) / min(10, len(urls)))
                                time.sleep(0.5)  # Rate limiting
                            
                            # Genera suggerimenti
                            with st.spinner("Generando suggerimenti..."):
                                suggestions = generator.suggest_structured_data(pages_info)
                            
                            # Mostra risultati
                            if suggestions.get('suggestions'):
                                st.subheader("📋 Suggerimenti Dati Strutturati")
                                
                                for suggestion in suggestions['suggestions']:
                                    priority_color = {
                                        'high': '🔴',
                                        'medium': '🟡', 
                                        'low': '🟢'
                                    }.get(suggestion.get('priority', 'medium'), '🟡')
                                    
                                    with st.expander(f"{priority_color} {suggestion['schema_type']} - Priorità: {suggestion.get('priority', 'medium')}"):
                                        st.write(f"**Motivo:** {suggestion['reason']}")
                                        if suggestion.get('pages'):
                                            st.write("**Pagine coinvolte:**")
                                            for page_url in suggestion['pages']:
                                                st.write(f"- {page_url}")
        
        elif input_method == "URL Specifici":
            urls_input = st.text_area(
                "Inserisci gli URL da analizzare (uno per riga)",
                placeholder="https://esempio.com/prodotto1\nhttps://esempio.com/articolo1"
            )
            
            if st.button("Analizza URL", type="primary"):
                if urls_input:
                    urls = [url.strip() for url in urls_input.split('\n') if url.strip()]
                    
                    with st.spinner("Analizzando le pagine..."):
                        pages_info = []
                        progress_bar = st.progress(0)
                        
                        for i, url in enumerate(urls):
                            page_info = scraper.scrape_page(url)
                            pages_info.append(page_info)
                            progress_bar.progress((i + 1) / len(urls))
                            time.sleep(0.5)
                        
                        # Genera suggerimenti
                        suggestions = generator.suggest_structured_data(pages_info)
                        
                        # Mostra risultati (come sopra)
                        if suggestions.get('suggestions'):
                            st.subheader("📋 Suggerimenti Dati Strutturati")
                            
                            for suggestion in suggestions['suggestions']:
                                priority_color = {
                                    'high': '🔴',
                                    'medium': '🟡', 
                                    'low': '🟢'
                                }.get(suggestion.get('priority', 'medium'), '🟡')
                                
                                with st.expander(f"{priority_color} {suggestion['schema_type']} - Priorità: {suggestion.get('priority', 'medium')}"):
                                    st.write(f"**Motivo:** {suggestion['reason']}")
                                    if suggestion.get('pages'):
                                        st.write("**Pagine coinvolte:**")
                                        for page_url in suggestion['pages']:
                                            st.write(f"- {page_url}")
    
    with tab2:
        st.header("Generazione Dati Strutturati")
        st.markdown("Genera dati strutturati personalizzati per le tue pagine.")
        
        # Selezione tipo di schema
        col1, col2 = st.columns([2, 1])
        
        with col1:
            schema_option = st.selectbox(
                "Seleziona il tipo di dati strutturati:",
                list(COMMON_STRUCTURED_DATA.keys()) + ["Altro"]
            )
        
        with col2:
            if schema_option == "Altro":
                custom_schema = st.text_input(
                    "Schema personalizzato",
                    placeholder="es. Recipe, VideoObject"
                )
            else:
                custom_schema = schema_option
        
        # Input pagina
        page_input_method = st.radio(
            "Come vuoi fornire le informazioni della pagina?",
            ["URL", "Codice Sorgente"]
        )
        
        if page_input_method == "URL":
            target_url = st.text_input("URL della pagina", placeholder="https://esempio.com/pagina")
            
            if st.button("Genera Dati Strutturati", type="primary"):
                if target_url and (custom_schema or schema_option != "Altro"):
                    with st.spinner("Analizzando la pagina..."):
                        page_info = scraper.scrape_page(target_url)
                    
                    if 'error' not in page_info:
                        with st.spinner("Generando dati strutturati..."):
                            structured_data = generator.generate_structured_data(
                                page_info, 
                                schema_option if schema_option != "Altro" else custom_schema,
                                custom_schema if schema_option == "Altro" else None
                            )
                        
                        if structured_data:
                            st.success("✅ Dati strutturati generati con successo!")
                            
                            # Mostra il risultato
                            st.subheader("📄 JSON-LD Generato")
                            st.code(structured_data, language="json")
                            
                            # Bottone per copiare
                            if st.button("📋 Copia negli Appunti"):
                                st.write("Copia il codice sopra e incollalo nella sezione `<head>` della tua pagina HTML.")
                            
                            # Istruzioni di implementazione
                            with st.expander("📚 Come implementare"):
                                st.markdown("""
                                **Istruzioni per l'implementazione:**
                                
                                1. Copia il codice JSON-LD generato
                                2. Incollalo nella sezione `<head>` della tua pagina HTML
                                3. Assicurati che sia racchiuso in tag `<script type="application/ld+json">`
                                
                                **Esempio:**
                                ```html
                                <head>
                                    <script type="application/ld+json">
                                    // Il tuo JSON-LD qui
                                    </script>
                                </head>
                                ```
                                
                                **Test e Validazione:**
                                - Usa il [Rich Results Test di Google](https://search.google.com/test/rich-results)
                                - Verifica con [Schema.org Validator](https://validator.schema.org/)
                                """)
        
        else:  # Codice Sorgente
            source_code = st.text_area(
                "Incolla il codice sorgente della pagina",
                height=200,
                placeholder="<html>...</html>"
            )
            
            target_url_manual = st.text_input(
                "URL di riferimento (opzionale)",
                placeholder="https://esempio.com/pagina"
            )
            
            if st.button("Genera da Codice Sorgente", type="primary"):
                if source_code and (custom_schema or schema_option != "Altro"):
                    with st.spinner("Analizzando il codice sorgente..."):
                        # Parse del codice sorgente
                        soup = BeautifulSoup(source_code, 'html.parser')
                        
                        page_info = {
                            'url': target_url_manual or 'https://esempio.com',
                            'title': soup.title.string.strip() if soup.title else '',
                            'meta_description': '',
                            'headings': [],
                            'images': [],
                            'content_type': 'webpage'
                        }
                        
                        # Estrai meta description
                        meta_desc = soup.find('meta', attrs={'name': 'description'})
                        if meta_desc:
                            page_info['meta_description'] = meta_desc.get('content', '')
                        
                        # Estrai headings
                        for i in range(1, 7):
                            headings = soup.find_all(f'h{i}')
                            for h in headings[:3]:
                                page_info['headings'].append({
                                    'level': i,
                                    'text': h.get_text().strip()
                                })
                    
                    with st.spinner("Generando dati strutturati..."):
                        structured_data = generator.generate_structured_data(
                            page_info,
                            schema_option if schema_option != "Altro" else custom_schema,
                            custom_schema if schema_option == "Altro" else None
                        )
                    
                    if structured_data:
                        st.success("✅ Dati strutturati generati con successo!")
                        
                        st.subheader("📄 JSON-LD Generato")
                        st.code(structured_data, language="json")
    
    # Footer
    st.markdown("---")
    st.markdown(
        """
        <div style='text-align: center; color: #666;'>
            Creato con ❤️ per ottimizzare la tua SEO | 
            <a href='https://schema.org/' target='_blank'>Schema.org</a> | 
            <a href='https://developers.google.com/search/docs/appearance/structured-data' target='_blank'>Google Structured Data</a>
        </div>
        """,
        unsafe_allow_html=True
    )

if __name__ == "__main__":
    main()
