# TikTok video research pipeline

Python workflow for turning a weak seed term into TikTok-native search terms, collecting a bounded video corpus, recording public metadata, extracting timestamped speech locally, and preparing comparison groups for creative-strategy analysis.

The repository automates collection and evidence preparation. It does **not** claim to measure platform-wide TikTok trends, explain why a video performed well, or replace direct visual analysis. Native MP4 files and a structured handoff can be reviewed separately with a multimodal model.

## Pipeline

```text
weak seed term
    |
    v
two-level search-term discovery
    |
    v
human selection of relevant TikTok-native terms
    |
    v
bounded search-result collection
    |
    +--> canonical URLs and public metadata
    +--> locally downloaded reference videos
    +--> local Faster-Whisper transcripts
    |
    v
deduplicated corpus and engagement snapshot
    |
    +--> top 10 by captured views
    +--> bottom 10 by captured views
    `--> one structured handoff JSON
    |
    v
direct visual audit and creative-strategy interpretation
```

## Active files

| File | Purpose |
| --- | --- |
| `tiktok_search_term_discovery.ipynb` | Expand a seed term through two nested levels of TikTok suggestions. |
| `tiktok_chatgpt_handoff.ipynb` | Select terms, request videos, rank comparison groups and produce the handoff. |
| `tiktok_video_search.py` | Browser collection, metadata extraction, video acquisition and local transcription. |
| `methodology.md` | Contrastive semantic performance-analysis methodology. |
| `thread_analysis_process.md` | Human-readable record of how the analytical process developed. |
| `examples/creepy_tok_100_manifest.csv` | URLs and public metadata from the 100-video proof of concept. |

Downloaded videos, credentials, browser profiles, complete transcripts and raw outputs are deliberately excluded from the repository.

## Installation

The validated workflow was developed on Windows with Microsoft Edge, Python 3.11, an NVIDIA GPU and a locally available Faster-Whisper `large-v3` model.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Microsoft Edge must be installed for the default isolated-session workflow. Chrome can be selected as an alternative with `--browser chrome`.

## Configuration

Paths are relative to the repository by default. The following environment variables are optional:

| Variable | Default | Purpose |
| --- | --- | --- |
| `TIKTOK_RESEARCH_ROOT` | Repository directory | Data and output root. |
| `TIKTOK_ANALYSIS_PYTHON` | Current Python executable | Interpreter used for model subprocesses. |
| `TIKTOK_WHISPER_MODEL` | `large-v3` | Cached model name or local Faster-Whisper model directory. |
| `TIKTOK_WHISPER_DEVICE` | `cuda` | Faster-Whisper device; use `cpu` where required. |
| `TIKTOK_WHISPER_COMPUTE_TYPE` | `float16` | Faster-Whisper compute type; CPU users can try `int8`. |
| `TIKTOK_CUDA_DLL_DIR` | Unset | Optional CUDA/Torch DLL directory prepended to `PATH`. |
| `TIKTOK_EDGE_EXECUTABLE` | Standard Windows Edge location | Explicit Edge executable path. |
| `TIKTOK_VISION_MODEL` | `Qwen/Qwen2.5-VL-7B-Instruct` | Optional legacy local-vision model identifier or path. |

Example local model configuration:

```powershell
$env:TIKTOK_WHISPER_MODEL = "D:\models\faster-whisper\large-v3"
$env:TIKTOK_WHISPER_DEVICE = "cuda"
$env:TIKTOK_WHISPER_COMPUTE_TYPE = "float16"
```

The transcription helper uses `local_files_only=True`; prepare the model locally before requesting transcription.

## Running a study

### 1. Discover search terms

Open `tiktok_search_term_discovery.ipynb` in JupyterLab, set the seed term, and run the notebook. It writes nested JSON and a human-readable CSV under `outputs/`.

The notebook requests TikTok's undocumented web autocomplete endpoint through a visible, persistent Edge session. The endpoint can change without notice. Second-level suggestions remain grouped under every first-level term that generated them, while the compact `layers` summary deduplicates repeated terms. This makes relevance decisions auditable without allowing a flat keyword list to obscure the original search branch.

### 2. Collect videos and prepare the handoff

Open `tiktok_chatgpt_handoff.ipynb` and configure:

```python
SELECTED_SEARCH_TERMS = ["first useful term", "second useful term"]
VIDEOS_PER_TERM = 10
TOP_BOTTOM_N = 10
RUN_COLLECTION = True
RUN_LABEL = "descriptive_run_name"
```

Run the notebook from top to bottom. The isolated Edge session remains open by default so a manual TikTok login can be reused. The workflow does not require automated password submission.

The collector can also be called directly:

```powershell
python tiktok_video_search.py "creepy tok" `
  --related-query "creepy tiktoks" `
  --related-query "creepypasta tok" `
  --limit 20 `
  --output outputs\creepy_tok_first_20.csv `
  --analyze-videos `
  --local-vision-limit 0
```

The local vision pass is disabled by default. The active workflow leaves visual and creative-strategy analysis to direct inspection of selected native videos.

### 3. Review the output

The handoff contains:

- seed and search lineage;
- canonical TikTok URL and video ID;
- search rank and repeated appearances across queries;
- creator, caption, hashtags and publication time;
- views, likes, comments, shares and saves captured at collection time;
- technical media validation;
- transcription status, full recovered speech and timestamped segments;
- top and bottom comparison-group membership.

Engagement values are observations at one collection time. They are useful for defining comparison groups, not evidence that engagement was caused by a particular content feature.

## Proof of concept

The reference run collected 100 unique videos using a seed plus closely related search terms. Search, metadata and detail enrichment took approximately 5 minutes 37 seconds; download took approximately 7 minutes 57 seconds; and local Faster-Whisper processed approximately 120.8 minutes of media in approximately 3 minutes 35 seconds on the development system.

Transcript outcomes were:

- 57 usable transcripts;
- 23 videos with no speech detected;
- 19 videos with no audio stream;
- 1 suspected ASR hallucination.

The public manifest preserves URLs, search appearances, engagement snapshots and technical duration. It excludes captions, transcripts and downloaded third-party media.

## Methodological boundary

The workflow supports creative research rather than statistical trend measurement. Its practical unit of analysis is the operation a video performs on the viewer, not merely its topic. The later analytical stages compare engagement-defined groups, identify enriched semantic structures, map concrete instances to those structures, and validate execution-level claims through direct video inspection.

See `methodology.md` for the complete method and `thread_analysis_process.md` for its development history.

## Responsible use

- Use the collector only where you are authorised to do so and comply with applicable platform rules and law.
- Keep credentials, cookies and browser profiles outside Git.
- Do not redistribute downloaded third-party videos without permission.
- Treat engagement as time-dependent metadata, not a causal explanation.
- Expect browser automation to require maintenance when TikTok changes its interface.

This project is independent and is not affiliated with or endorsed by TikTok.
