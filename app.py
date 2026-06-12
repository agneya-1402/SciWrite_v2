import os
import time
import json
import zipfile
import re
import logging
import matplotlib
from datetime import datetime
from flask import Flask, render_template, request, session, jsonify, Response, send_from_directory, redirect, url_for, stream_with_context
from dotenv import load_dotenv
import google as genai
import requests
import numpy as np
import matplotlib.pyplot as plt
import bibtexparser
from bibtexparser.bparser import BibTexParser
from bibtexparser.customization import author

# Set Matplotlib backend to 'Agg' for headless environments
matplotlib.use('Agg')

load_dotenv()

# --- Flask App Initialization ---
app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'dev-secret-key-for-flask-sessions')


# --- Configure Logging ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
app.logger.setLevel(logging.INFO)

# --- Gemini API Configuration ---
try:
    # The new SDK automatically picks up GEMINI_API_KEY from os.environ,
    # but passing it explicitly via the Client guarantees initialization.
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY environment variable is missing.")
        
    # Initialize the modern GenAI Client
    ai_client = genai.Client(api_key=api_key)
    
    # We store the string name; the client will handle generation calls
    GEMINI_MODEL_NAME = 'gemini-2.5-flash-lite'
    app.logger.info("Gemini API Client configured successfully.")
except Exception as e:
    app.logger.error(f"Error configuring Gemini: {e}")
    ai_client = None
    GEMINI_MODEL_NAME = None

# --- Directory Setup ---
# Use /tmp for serverless environments as it's writable and ephemeral
GENERATED_DIR = os.path.join('/tmp', 'generated')
UPLOADS_DIR = os.path.join('/tmp', 'uploads')
os.makedirs(GENERATED_DIR, exist_ok=True)
os.makedirs(UPLOADS_DIR, exist_ok=True)
app.logger.info(f"Generated files directory: {GENERATED_DIR}")
app.logger.info(f"Uploaded files directory: {UPLOADS_DIR}")

# ==============================================================================
# PRESERVED BACKEND LOGIC (Refactored from Streamlit)
# ==============================================================================

def fetch_arxiv_literature(keywords, max_results=5):
    """Fetches literature from arXiv based on keywords."""
    app.logger.info(f"Fetching arXiv literature for keywords: {keywords}")
    try:
        query = "+AND+".join([f'all:"{k.strip()}"' for k in keywords.split(',')])
        url = f"http://export.arxiv.org/api/query?search_query={query}&start=0&max_results={max_results}&sortBy=relevance&sortOrder=descending"
        response = requests.get(url)
        response.raise_for_status()
        
        feed = response.text
        papers = []
        for entry in feed.split('<entry>')[1:]:
            paper_title = entry.split('<title>')[1].split('</title>')[0].strip().replace('\n', ' ')
            summary = entry.split('<summary>')[1].split('</summary>')[0].strip().replace('\n', ' ')
            papers.append(f"Title: {paper_title}\nSummary: {summary}")
        app.logger.info(f"Successfully fetched {len(papers)} papers from arXiv.")
        return "\n\n---\n\n".join(papers)
    except Exception as e:
        app.logger.error(f"Error fetching arXiv literature: {e}")
        return f"Error fetching arXiv literature: {e}"

def call_gemini_with_retry(prompt, max_retries=3):
    """Calls the Gemini API with a retry mechanism."""
    if not ai_client or not GEMINI_MODEL_NAME:
        app.logger.error("Gemini API not configured. Cannot call API.")
        return "Error: Gemini API not configured. Please set the GEMINI_API_KEY."
    
    app.logger.info("Calling Gemini API...")
    for attempt in range(max_retries):
        try:
            # Modern SDK uses client.models.generate_content
            response = ai_client.models.generate_content(
                model=GEMINI_MODEL_NAME, 
                contents=prompt
            )
            app.logger.info(f"Gemini API call successful on attempt {attempt + 1}.")
            return response.text
        except Exception as e:
            app.logger.warning(f"Gemini API call failed on attempt {attempt + 1}: {e}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
            else:
                app.logger.error(f"Gemini API call failed after {max_retries} attempts: {e}")
                return f"Error calling Gemini API after {max_retries} attempts: {e}"

def generate_section_prompt(section_title, context):
    """Generates a standardized prompt for a paper section."""
    return f"""
You are an expert academic writer. Generate the '{section_title}' section of a research paper.

**Paper Title:** {context.get('title', 'N/A')}
**Keywords:** {context.get('keywords', 'N/A')}
**Venue:** {context.get('venue', 'A general academic journal')}
**Core Ideas & Goals:** {context.get('abstract_goals', 'N/A')}
**Background/Context:** {context.get('background', 'N/A')}
**Methodology:** {context.get('methodology', 'N/A')}
**Results:** {context.get('results', 'N/A')}
**Additional Notes:** {context.get('extra_notes', 'N/A')}
**Relevant Literature:**
{context.get('arxiv_literature', 'No literature fetched.')}

**Instructions:**
- Write a comprehensive, well-structured, and publication-ready '{section_title}' section.
- The tone should be formal and academic.
- Ensure the content is coherent with the provided context.
- Do NOT include the section title in the output. Just provide the text.
- Use LaTeX for citations (e.g., \\cite{{key}}) and other formatting where appropriate.
"""

def generate_academic_chart(chart_description, session_id):
    """Generates and saves a simple academic-style chart."""
    app.logger.info(f"Generating chart for description: {chart_description}")
    try:
        plt.style.use('dark_background')
        fig, ax = plt.subplots(figsize=(8, 5))
        
        # Generate some plausible random data for a bar chart
        labels = [f'Group {chr(65+i)}' for i in range(4)]
        values = np.random.rand(4) * 100
        errors = np.random.rand(4) * 10
        
        ax.bar(labels, values, yerr=errors, capsize=5, color='#5B8DF5', alpha=0.8)
        
        ax.set_ylabel('Metric Value')
        ax.set_title(chart_description[:80], fontsize=12) # Truncate title
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.grid(axis='y', linestyle='--', alpha=0.2)
        plt.tight_layout()
        
        chart_filename = f"chart_{session_id}.png"
        chart_path = os.path.join(GENERATED_DIR, chart_filename)
        plt.savefig(chart_path, dpi=150)
        plt.close(fig)
        app.logger.info(f"Chart saved to {chart_path}")
        return chart_filename
    except Exception as e:
        app.logger.error(f"Error generating chart: {e}")
        return None

def render_latex(context):
    """
    Renders the complete LaTeX document from generated sections using a robust
    templating method that avoids Python string escape conflicts.
    """
    app.logger.info("Rendering LaTeX document.")
    
    def bibtex_customization(record):
        # Only use customizations known to be in older versions
        record = author(record)
        return record

    bib_database = None
    if context.get('bibtex_str'):
        try:
            parser = BibTexParser(common_strings=True)
            parser.customization = bibtex_customization
            parser.ignore_errors = True
            bib_database = bibtexparser.loads(context['bibtex_str'], parser=parser)
            app.logger.info("BibTeX parsed successfully.")
        except Exception as e:
            app.logger.warning(f"Error parsing BibTeX: {e}")
            bib_database = None # Failed to parse

    # Create a simple list of authors, ensuring LaTeX newlines are properly escaped
    authors_list = [f"{a['name']} \\\\ {a['affiliation']}" for a in context.get('authors', [])]
    authors_latex = " \\and ".join(authors_list)

    # Build figure includes
    figures_latex = ""
    if context.get('figure_files'):
        for i, fig_info in enumerate(context.get('figure_files', [])):
            # Use a raw f-string (rf) to handle paths and commands safely
            figures_latex += rf"""
\begin{{figure}}[h!]
    \centering
    \includegraphics[width=0.8\textwidth]{{{fig_info['filename']}}}
    \caption{{{fig_info['caption']}}}
    \label{{fig:fig{i+1}}}
\end{{figure}}
"""

    # Build chart includes
    charts_latex = ""
    if context.get('chart_files'):
        for i, chart_info in enumerate(context.get('chart_files', [])):
            charts_latex += rf"""
\begin{{figure}}[h!]
    \centering
    \includegraphics[width=0.8\textwidth]{{{chart_info['filename']}}}
    \caption{{{chart_info['caption']}}}
    \label{{fig:chart{i+1}}}
\end{{figure}}
"""

    # Prepare bibliography line
    bib_line = ''
    if bib_database:
        bib_filename = context.get("bib_filename", "references")
        bib_line = f"\\bibliography{{{bib_filename}}}"

    # Use a raw string for the main template to prevent unicode escape errors
    template = r"""
\documentclass{article}
\usepackage[utf8]{inputenc}
\usepackage{graphicx}
\usepackage{amsmath}
\usepackage{authblk}
\usepackage[margin=1in]{geometry}

\title{__TITLE__}
\author{__AUTHORS__}
\date{\today}

\begin{document}

\maketitle

\begin{abstract}
__ABSTRACT__
\end{abstract}

\section*{Keywords}
__KEYWORDS__

\section{Introduction}
__INTRODUCTION__

\section{Related Work}
__RELATED_WORK__

\section{Methodology}
__METHODOLOGY__
__FIGURES__
__CHARTS__

\section{Results}
__RESULTS__

\section{Discussion}
__DISCUSSION__

\section{Conclusion}
__CONCLUSION__

__BIBLIOGRAPHY__
\bibliographystyle{plain}

\end{document}
"""

    # Use simple .replace() for robust substitution
    filled_template = template \
        .replace('__TITLE__', context.get('title', 'Untitled Paper')) \
        .replace('__AUTHORS__', authors_latex) \
        .replace('__ABSTRACT__', context.get('sections', {}).get('Abstract', '')) \
        .replace('__KEYWORDS__', context.get('keywords', '')) \
        .replace('__INTRODUCTION__', context.get('sections', {}).get('Introduction', '')) \
        .replace('__RELATED_WORK__', context.get('sections', {}).get('Related Work', '')) \
        .replace('__METHODOLOGY__', context.get('sections', {}).get('Methodology', '')) \
        .replace('__FIGURES__', figures_latex) \
        .replace('__CHARTS__', charts_latex) \
        .replace('__RESULTS__', context.get('sections', {}).get('Results', '')) \
        .replace('__DISCUSSION__', context.get('sections', {}).get('Discussion', '')) \
        .replace('__CONCLUSION__', context.get('sections', {}).get('Conclusion', '')) \
        .replace('__BIBLIOGRAPHY__', bib_line)
    
    app.logger.info("LaTeX document rendered.")
    return filled_template, bib_database

def generate_overleaf_zip(latex_source, bib_database, bib_filename, figure_files, chart_files, session_id):
    """Generates a ZIP file compatible with Overleaf."""
    app.logger.info(f"Generating Overleaf ZIP for session {session_id}.")
    zip_filename = f"sciwrite_overleaf_{session_id}.zip"
    zip_path = os.path.join(GENERATED_DIR, zip_filename)

    try:
        with zipfile.ZipFile(zip_path, 'w') as zf:
            # Write main LaTeX file
            zf.writestr("main.tex", latex_source)
            app.logger.info("Added main.tex to ZIP.")

            # Write BibTeX file
            if bib_database:
                bib_path = f"{bib_filename}.bib"
                zf.writestr(bib_path, bibtexparser.dumps(bib_database))
                app.logger.info(f"Added {bib_path} to ZIP.")

            # Add uploaded figures
            for fig_info in figure_files:
                zf.write(fig_info['path'], fig_info['filename'])
                app.logger.info(f"Added figure {fig_info['filename']} to ZIP.")
            
            # Add generated charts
            for chart_info in chart_files:
                zf.write(chart_info['path'], chart_info['filename'])
                app.logger.info(f"Added chart {chart_info['filename']} to ZIP.")
        app.logger.info(f"ZIP file created successfully at {zip_path}")
        return zip_filename
    except Exception as e:
        app.logger.error(f"Error creating ZIP file: {e}")
        return None

# ==============================================================================
# FLASK ROUTES
# ==============================================================================

@app.before_request
def ensure_session_id():
    if 'session_id' not in session:
        session['session_id'] = os.urandom(8).hex()
        app.logger.info(f"New session ID created: {session['session_id']}")

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/generate')
def generate_page():
    return render_template('generate.html')

@app.route('/results')
def results_page():
    session_id = session.get('session_id')
    data_path = os.path.join(GENERATED_DIR, f"data_{session_id}.json") if session_id else None
    
    if not data_path or not os.path.exists(data_path):
        app.logger.warning(f"Attempted to access /results without generation data on disk for session {session_id}. Redirecting to /generate.")
        return redirect(url_for('generate_page'))
        
    try:
        with open(data_path, 'r') as f:
            generation_data = json.load(f)
    except Exception as e:
        app.logger.error(f"Error loading generation data file: {e}")
        return redirect(url_for('generate_page'))
        
    app.logger.info(f"Rendering results page for session {session_id}.")
    return render_template('results.html', data=generation_data)

@app.route('/api/generate', methods=['POST'])
def api_generate():
    
    def generate_stream():
        start_time = time.time()
        session_id = session['session_id']
        app.logger.info(f"Starting generation stream for session {session_id}.")

        # --- 1. Clean up old files ---
        yield "event: status\ndata: Initializing and cleaning workspace...\n\n"
        app.logger.info(f"Cleaning up old files for session {session_id} in {GENERATED_DIR} and {UPLOADS_DIR}.")
        for d in [GENERATED_DIR, UPLOADS_DIR]:
            for f in os.listdir(d):
                if f.startswith(f"chart_{session_id}") or f.startswith(f"upload_{session_id}") or f.startswith(f"sciwrite_overleaf_{session_id}") or f.startswith(f"data_{session_id}"):
                    try:
                        os.remove(os.path.join(d, f))
                        app.logger.debug(f"Removed old file: {f}")
                    except OSError as e:
                        app.logger.warning(f"Could not remove old file {f}: {e}")

        # --- 2. Parse Form Data ---
        form_data = request.form.to_dict()
        app.logger.info("Form data received and parsed.")
        
        # Parse authors table
        authors = []
        author_keys = [k for k in form_data if k.startswith('authors[')]
        if author_keys:
            num_authors = max([int(re.search(r'\[(\d+)\]', k).group(1)) for k in author_keys]) + 1
            for i in range(num_authors):
                authors.append({
                    'name': form_data.get(f'authors[{i}][name]', ''),
                    'affiliation': form_data.get(f'authors[{i}][affiliation]', '')
                })
        
        context = {
            'title': form_data.get('title'),
            'keywords': form_data.get('keywords'),
            'authors': authors,
            'abstract_goals': form_data.get('abstract_goals'),
            'background': form_data.get('background'),
            'methodology': form_data.get('methodology'),
            'results': form_data.get('results'),
            'extra_notes': form_data.get('extra_notes'),
            'bibtex_str': form_data.get('bibtex'),
            'venue': form_data.get('venue', 'Journal of Modern AI Research'),
            'pages': form_data.get('pages', 8),
            'layout': form_data.get('layout', 'Two-Column'),
            'sections': {},
            'figure_files': [],
            'chart_files': [],
            'word_counts': {},
            'bib_filename': 'references'
        }
        app.logger.debug(f"Generation context initialized: {context.keys()}")

        # --- 3. Handle File Uploads ---
        figure_files = request.files.getlist('figures')
        if figure_files and figure_files[0].filename: # Check if any files were actually uploaded
            app.logger.info(f"Processing {len(figure_files)} uploaded figures.")
            for i, file in enumerate(figure_files):
                if file and file.filename:
                    filename = f"upload_{session_id}_{i}_{file.filename}"
                    filepath = os.path.join(UPLOADS_DIR, filename)
                    file.save(filepath)
                    context['figure_files'].append({
                        'path': filepath,
                        'filename': filename,
                        'caption': form_data.get(f'figure_captions[{i}]', 'No caption provided.')
                    })
                    app.logger.info(f"Saved uploaded figure: {filename}")
        else:
            app.logger.info("No figures uploaded.")


        # --- 4. Generation Steps ---
        generation_steps = [
            ("Fetching arXiv Literature", "arxiv_literature", lambda: fetch_arxiv_literature(context['keywords'])),
            ("Generating Charts", "charts", None), # Special handling
            ("Generating Abstract", "Abstract", lambda: call_gemini_with_retry(generate_section_prompt("Abstract", context))),
            ("Generating Introduction", "Introduction", lambda: call_gemini_with_retry(generate_section_prompt("Introduction", context))),
            ("Generating Related Work", "Related Work", lambda: call_gemini_with_retry(generate_section_prompt("Related Work", context))),
            ("Generating Methodology", "Methodology", lambda: call_gemini_with_retry(generate_section_prompt("Methodology", context))),
            ("Generating Results", "Results", lambda: call_gemini_with_retry(generate_section_prompt("Results", context))),
            ("Generating Discussion", "Discussion", lambda: call_gemini_with_retry(generate_section_prompt("Discussion", context))),
            ("Generating Conclusion", "Conclusion", lambda: call_gemini_with_retry(generate_section_prompt("Conclusion", context))),
        ]

        total_steps = len(generation_steps) + 2 # + LaTeX and ZIP
        for i, (step_name, context_key, action) in enumerate(generation_steps):
            progress = int(((i + 1) / total_steps) * 100)
            elapsed = time.time() - start_time
            yield f"event: progress\ndata: {json.dumps({'progress': progress, 'status': step_name, 'elapsed': elapsed})}\n\n"
            app.logger.info(f"Generation step: {step_name} (Progress: {progress}%)")

            if context_key == "charts":
                chart_captions = [v for k, v in form_data.items() if k.startswith('chart_captions')]
                if chart_captions:
                    app.logger.info(f"Generating {len(chart_captions)} charts.")
                    for j, caption in enumerate(chart_captions):
                        chart_filename = generate_academic_chart(caption, f"{session_id}_{j}")
                        if chart_filename:
                            context['chart_files'].append({
                                'path': os.path.join(GENERATED_DIR, chart_filename),
                                'filename': chart_filename,
                                'caption': caption
                            })
                else:
                    app.logger.info("No charts requested for generation.")
            else:
                result = action()
                if context_key == "arxiv_literature":
                    context[context_key] = result
                else:
                    context['sections'][context_key] = result
                    context['word_counts'][context_key] = len(result.split())
                app.logger.debug(f"Completed '{context_key}' section.")

        # --- 5. Build LaTeX and ZIP ---
        yield f"event: progress\ndata: {json.dumps({'progress': 95, 'status': 'Building LaTeX', 'elapsed': time.time() - start_time})}\n\n"
        latex_source, bib_database = render_latex(context)
        context['latex_source'] = latex_source
        
        yield f"event: progress\ndata: {json.dumps({'progress': 98, 'status': 'Packaging ZIP for Overleaf', 'elapsed': time.time() - start_time})}\n\n"
        zip_filename = generate_overleaf_zip(
            latex_source, bib_database, context['bib_filename'], 
            context['figure_files'], context['chart_files'], session_id
        )
        
        # --- 6. Finalize and Store in Session ---
        end_time = time.time()
        total_words = sum(context['word_counts'].values())
        
        final_data = {
            'title': context['title'],
            'sections': context['sections'],
            'word_counts': context['word_counts'],
            'total_words': total_words,
            'estimated_pages': round(total_words / 500, 1),
            'generation_time': round(end_time - start_time, 2),
            'latex_source': latex_source,
            'zip_filename': zip_filename,
            'tex_filename': f"sciwrite_paper_{session_id}.tex",
            'timestamp': datetime.utcnow().isoformat()
        }
        # Write the data safely to disk instead of the session cookie
        data_path = os.path.join(GENERATED_DIR, f"data_{session_id}.json")
        with open(data_path, 'w') as f:
            json.dump(final_data, f)
            
        app.logger.info(f"Generation completed for session {session_id}. Final data saved to disk.")
        
        yield f"event: complete\ndata: {json.dumps({'status': 'complete'})}\n\n"

    return Response(stream_with_context(generate_stream()), mimetype='text/event-stream')

@app.route('/api/download-tex')
def download_tex():
    session_id = session.get('session_id')
    data_path = os.path.join(GENERATED_DIR, f"data_{session_id}.json") if session_id else None
    
    if not data_path or not os.path.exists(data_path):
        app.logger.warning(f"Download request for .tex failed: No data found on disk for session {session_id}.")
        return "No LaTeX source found.", 404
    
    with open(data_path, 'r') as f:
        data = json.load(f)
    
    app.logger.info(f"Serving .tex file for session {session_id}.")
    return Response(
        data['latex_source'],
        mimetype="application/x-latex",
        headers={"Content-disposition": f"attachment; filename={data.get('tex_filename', 'paper.tex')}"}
    )

@app.route('/api/download-zip')
def download_zip():
    session_id = session.get('session_id')
    data_path = os.path.join(GENERATED_DIR, f"data_{session_id}.json") if session_id else None
    
    if not data_path or not os.path.exists(data_path):
        app.logger.warning(f"Download request for .zip failed: No data found on disk for session {session_id}.")
        return "No ZIP file found.", 404
        
    with open(data_path, 'r') as f:
        data = json.load(f)
    
    zip_path = os.path.join(GENERATED_DIR, data['zip_filename'])
    if not os.path.exists(zip_path):
        app.logger.error(f"ZIP file not found on disk: {zip_path} for session {session_id}.")
        return "ZIP file not found on server.", 404

    app.logger.info(f"Serving .zip file {data['zip_filename']} for session {session_id}.")
    return send_from_directory(GENERATED_DIR, data['zip_filename'], as_attachment=True)

# ==============================================================================
# MAIN ENTRY POINT
# ==============================================================================

if __name__ == '__main__':
    app.run(debug=True, port=5001)
