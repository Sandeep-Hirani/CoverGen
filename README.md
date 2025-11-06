# CoverGen

Automate your cover letter workflow by pulling job descriptions from the web, blending them with your CV, asking an LLM to draft a personalised letter body, and compiling the result to PDF through LaTeX.

## Features
- Fetch job descriptions from URLs or local files.
- Combine the posting with your CV text and optional tweaks (role, tone, extra instructions).
- Ask a configurable LLM (OpenAI, Together, or OpenRouter) for a LaTeX-formatted letter body tailored to the role.
- Inject the response into a configurable LaTeX template and compile to PDF.
- Snapshot the job description alongside the generated assets for traceability.

## Project Layout
```
covergen/
    cli.py             # Typer CLI entry point
    config.py          # Pydantic settings (API keys, paths, engines)
    cv_loader.py       # Reads your CV text from disk
    job_fetcher.py     # Pulls job descriptions from URLs or files
    latex.py           # Renders the template and compiles PDFs
    llm.py             # Thin wrapper over OpenAI / Together / OpenRouter clients
    pipeline.py        # Orchestrates the full workflow
    prompting.py       # Crafts prompts for the LLM
templates/
    cover_letter.tex.j2
```

## Setup
1. **Python environment**
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -e .
   ```

2. **Environment variables**
   Copy `.env.sample` to `.env` and customise the values:
   ```dotenv
   LLM_PROVIDER=openai
   OPENAI_API_KEY=sk-...
   TOGETHER_API_KEY=your-together-api-key
   OPENROUTER_API_KEY=your-openrouter-api-key
   LLM_MODEL=gpt-4-turbo
   LLM_TEMPERATURE=0.2

   CV_PATH=data/cv.txt
   LATEX_TEMPLATE=templates/cover_letter.tex.j2
   LATEX_ENGINE=xelatex
   OUTPUT_DIR=output

   DEFAULT_SENDER_NAME=Jane Doe
   DEFAULT_SENDER_ADDRESS=123 Main Street|San Francisco, CA
   # Recipient name and company are derived from the job description; use CLI flags to override

   DEFAULT_OPENING=Dear Hiring Manager
   DEFAULT_CLOSING=Sincerely,
   DEFAULT_TONE=professional
   ```
   Address lists use `|` as a separator (e.g. `Line 1|Line 2|Country`). Set at least one provider key (`OPENAI_API_KEY`, `TOGETHER_API_KEY`, or `OPENROUTER_API_KEY`) matching `LLM_PROVIDER`. When omitted, the recipient name and company are derived automatically from the job posting metadata.

3. **Prepare your CV text**
   Copy `data/cv.sample.txt` to `data/cv.txt` (ignored by git) and replace the placeholder content with a clean, plain-text version of your CV. Use blank lines to separate sections and bullet points to help the LLM.

4. **LaTeX toolchain**
   Install a LaTeX engine (`xelatex`, `pdflatex`, etc.) accessible on your `$PATH`. On macOS you can use MacTeX, on Ubuntu install `texlive-full` or a slimmer variant.

## Usage
With the defaults configured, generating a tailored cover letter requires only the job description source:
```bash
covergen generate "https://example.com/job123"
```
The CLI pulls identity details from configuration, automatically derives the recipient name and company, and fills in the rest.

Override any detail on demand:
```bash
covergen generate job_postings/backend-role.html \
  --role "Senior Backend Engineer" \
  --tone "enthusiastic" \
  --instructions "Highlight distributed systems experience." \
  --sender-address "123 Main Street" --sender-address "San Francisco, CA"
```

The command writes:
- `output/<stem>.tex` – fully rendered LaTeX letter
- `output/<stem>.pdf` – compiled PDF (skip with `--skip-pdf`)
- `output/<stem>.job.txt` – job description snapshot

Display current settings:
```bash
covergen show-settings
```

## Notes
- LinkedIn and other authenticated sources may require you to download the job description HTML manually; pass the saved file path to `covergen generate`.
- The LLM client uses chat completions. Switch models via `LLM_MODEL` and adjust `LLM_PROVIDER` / API keys as needed.
- To use Together.ai, set `LLM_PROVIDER=together`, provide `TOGETHER_API_KEY`, and choose a supported `LLM_MODEL` such as `togethercomputer/llama-3.1-8b-instruct`.
- To use OpenRouter, set `LLM_PROVIDER=openrouter`, provide `OPENROUTER_API_KEY`, and choose a model available on the platform (for example, `anthropic/claude-3.5-sonnet`).
- Failed LaTeX compilations will surface the engine output. Inspect the `.log` file generated next to the `.tex` if this happens.

## Next Ideas
- Add providers beyond the current OpenAI/Together/OpenRouter options (e.g., Anthropic, local models).
- Implement browser automation for sites that need authentication or dynamic rendering.
- Maintain a library of role-specific prompt presets.
