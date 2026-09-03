# TikTok Performance and Semantic-Structure Methodology

Revision 2 — canonical project methodology.

## Purpose

This document is a runbook for analysing TikTok video performance and semantic structure from collected JSON, JSONL, CSV, or notebook-derived data.

The primary goal is to identify semantic forms, content structures, and reusable generative rules associated with top-performing videos, while preserving the limits of the evidence. Structured data is the scalable primary layer. Direct video inspection is a later audit layer used only to validate or refine claims about execution.

The main object of analysis is not topic alone. It is the **semantic operation**: what the video makes the viewer notice, infer, question, reclassify, anticipate, or replay.

## Run Depth and Proportionality

Choose the analysis depth before beginning. Do not execute every possible stage merely because it appears in this runbook.

### Baseline Run

- evidence, schema, duplicate, and acquisition-bias audit
- engagement ranking and explicit group definition
- traceable semantic representation
- one transparent clustering or similarity pass
- compact multi-axis coding where supported by evidence
- target-versus-comparison contrast
- cautious generative-rule hypotheses

### Extended Run

Add only when the result is likely to change or strengthen a creative decision:

- instance-level clustering
- alternative representations or embedding models
- enrichment and stability analysis
- temporal-structure testing
- deeper counterexample analysis

### Direct-Video Audit

Add when execution-level claims matter or structured evidence is insufficient:

- representative top and bottom performers
- cluster or operation exemplars
- counterexamples
- ambiguous or visually dependent records

Stop when additional analysis is no longer producing materially new or more reliable generative rules. Record the selected run depth in the final report.

## Inputs

One or more of the following:

- `.jsonl`, `.json`, or `.csv` data files
- notebooks containing relevant structured outputs
- locally archived video files for optional direct audit

Individual records may contain:

- video ID, URL, and filename
- search term and acquisition metadata
- caption and hashtags
- transcript and transcript timestamps
- hook, spoken premise, visual premise, and on-screen text
- narrative or loop structure
- affective register and distinctive features
- creator metadata
- views, likes, comments, shares, and saves
- publication timestamp and collection timestamp
- analysis provenance and confidence information

## Evidence and Language Rules

- Do not infer causality from view counts.
- Do not treat cluster membership as proof of performance.
- Keep engagement metrics out of the semantic feature space used for clustering.
- Separate strict invariants from dominant patterns and weaker tendencies.
- Use **all** only for 100% of the relevant group.
- Use **most** only for more than 50% of the relevant group.
- Use **enriched** for a feature that is overrepresented in one group but not exclusive to it.
- Use **unique** only when the feature is absent from the comparison group.
- Use **suppressed** only for content that is consistently absent, withheld, minimised, or displaced relative to the expected form. State the basis.
- Do not claim direct visual or audio evidence unless the relevant media was actually inspected or analysed.
- Clearly label visual fields that are machine-generated, transcript-derived, generic placeholders, or not run.
- Preserve source field and video ID for every content-level claim wherever practical.
- Distinguish observed patterns, inferred rules, and speculative production advice.
- Where a claim depends on transcript quality, visual summaries, model outputs, or incomplete fields, state that dependency.

Preferred performance language:

- associated with
- overrepresented
- concentrated
- consistent with
- not sufficient alone
- weakly supported
- exploratory

Avoid causal language such as "caused performance" or "explains performance" unless causal evidence genuinely exists.

## Data-Quality Tier

Before drawing semantic conclusions, classify the corpus.

| Tier | Available Evidence | Supported Analysis |
|---|---|---|
| A | Transcript, caption, hook or on-screen text, grounded visual/content fields, and usable provenance | Full JSON-first semantic analysis, target contrast, instance clustering, and tentative generative rules |
| B | Transcript plus caption/hashtags, but weak or generic visual fields | Semantic clustering and contrast; generative rules need stronger caveats |
| C | Captions and hashtags only | Topic, format, and surface hook analysis only |
| D | Bare metadata and engagement only | Engagement distribution and sampling only |

Expected analytical capacity:

- Tier A: high for structured semantic analysis; execution-level claims still require selective video inspection
- Tier B: moderate to high for language-led forms; weak for visually driven forms
- Tier C: limited to topic, surface framing, format cues, and explicit hooks
- Tier D: limited to engagement description and sampling

Do not assign general percentage coverage to these tiers without benchmarking. A percentage such as “75-85% from JSON” may be reported retrospectively as an estimated **contribution share**: the proportion of useful findings actually produced in a particular analysis that came from structured data. It must not be presented as the proportion of everything theoretically knowable about the videos.

### Mixed Evidence Within a Corpus

A corpus-level tier is only a summary. Individual videos and fields may occupy different tiers. Create an evidence mask for every record containing, where available:

- field present or absent
- source: platform metadata, transcript model, visual model, direct inspection, or manual annotation
- grounded, inferred, or placeholder status
- confidence or quality flag
- timestamp availability

Do not let a corpus-level label conceal weak evidence for particular videos or claims.

## Corpus Bias and Confounds

Treat the corpus as a conditioned sample, not as TikTok broadly.

Record and preserve:

- search terms used
- search rank or retrieval order
- collection date and time
- publication date and video age at collection
- region, account context, or scraper context if available
- creator identity and creator reach proxies
- duplicate, repost, or recurring-series indicators

Important confounds:

- older videos have had more time to accumulate views
- creator reach may dominate content effects
- search position may condition what was collected
- collection from one search term creates topic bias
- platform recommendation history is unobserved
- watch time, retention, completion rate, and traffic source are usually absent

Raw view count may define analytical groups. It cannot by itself explain why a video performed.

## Procedure

### 1. Inspect the Available Files

- List the relevant files.
- Identify record counts and unique video counts.
- Detect duplicate video IDs.
- Inspect schemas and available columns.
- Identify content-bearing, engagement, acquisition, technical, and provenance fields.
- Record mismatched schemas or ambiguous field meanings before analysis.
- Identify the data-quality tier for the corpus.

### 2. Audit Duplicates and Series Effects

Check for:

- duplicate video IDs
- identical or near-identical captions
- identical or near-identical transcripts
- reposted videos
- the same video in multiple searches
- recurring creator formats
- multi-part series that should be analysed both individually and as a series

Report whether duplicates are removed, merged, or retained. Do not silently let near-duplicates dominate clustering or central-instance lists.

### 3. Summarise the Corpus

- Report total unique videos.
- Calculate missingness for important fields.
- Summarise views and other engagement measures using minimum, maximum, mean, median, quartiles, and extreme values.
- Rank videos by captured view count.
- Tabulate or plot view counts in descending order when useful.
- Identify candidate top and bottom comparison groups.

View counts are snapshots taken at collection time and must be labelled accordingly.

### 4. Define Engagement Groups

- Use raw view counts unless another measure is explicitly requested.
- Inspect the distribution for elbows, knees, and extreme outliers.
- Report ambiguity when the data does not support a natural threshold.
- Permit a manually specified target-group size.
- Use top 10 only when instructed or when it is an explicitly documented exploratory default.
- Define the target group as the selected top group.
- Define the comparison group as the remaining videos.
- Define a same-sized bottom group when a direct top-versus-bottom comparison is useful.

These groups are analytical contrasts, not claims that view count is an objective measure of creative quality.

### 5. Identify Content-Bearing Fields

Prioritise:

- transcript
- transcript timestamps
- caption
- spoken premise
- hook
- on-screen text
- visual premise
- distinctive features
- narrative or loop structure
- affective register
- hashtags, with generic genre and distribution tags downweighted

Exclude from semantic clustering or analyse separately:

- views, likes, comments, shares, and saves
- creator handle
- search rank
- acquisition and technical metadata
- analysis provenance

Generic terms such as `scary`, `creepy`, `horror`, `fyp`, and other broad distribution tags should not dominate the semantic representation.

### 6. Build a Traceable Semantic Text Field

Construct a traceable semantic representation from selected content-bearing fields. A single combined string may be used as a baseline, but field length and repetition must not silently determine similarity.

Requirements:

- preserve original field boundaries and source text
- retain video IDs for every extracted phrase and cluster assignment
- remove or downweight generic tags and repeated boilerplate
- do not silently convert missing visual evidence into textual assumptions
- keep a separate copy of the unmodified source text for audit
- record which fields contributed to each combined text
- normalise or cap field contributions so long transcripts do not automatically overwhelm short hooks or captions
- keep generic hashtags separate or assign them a lower weight
- distinguish grounded visual descriptions from inferred or placeholder visual text

Where practical, construct separate views before combining them:

```text
caption representation
transcript representation
hook and on-screen-text representation
grounded visual-description representation
        -> weighted or late combination
```

Record the weighting or combination rule. If one flat string is used for simplicity, state that choice and its likely bias.

### 7. Cluster the Full Corpus Semantically

Run at least one reproducible computational pass, using a method appropriate to corpus size and data quality:

- TF-IDF for a transparent lexical baseline
- sentence embeddings for semantic similarity when available
- dimensionality reduction when it aids clustering or inspection
- several plausible cluster counts rather than one arbitrary value
- silhouette score, inertia, BIC, stability checks, or another suitable diagnostic

Do not force a taxonomy when the evidence does not form stable or interpretable clusters.

Translate the computational output into a human-readable taxonomy containing:

- cluster name and description
- cluster size
- central or representative videos
- representative phrases or instances
- video IDs
- engagement summary by cluster
- counterexamples or boundary cases

### 8. Perform Multi-Axis Semantic Coding

After clustering, code each video across multiple axes as part of the baseline run when the available evidence supports it. This is strategically important because the strongest performance-relevant structure may cut across topic clusters.

Use multi-label coding where appropriate. Use `unknown` or `insufficient evidence` rather than forcing a label. Define a compact codebook before coding and preserve any changes to that codebook.

| Axis | Examples |
|---|---|
| Topic/domain | paranormal, creature, crime, fiction, fandom, ritual, skit, analogue, liminal |
| Format/truth-status | evidence claim, narrated story, analysis, joke, short film, edit, prompt, pseudo-documentary |
| Semantic operation | inspection, anomaly detection, identity instability, reclassification, threat inference, evidence accumulation, suppressed reveal, replay invitation |
| Hook mechanism | question, warning, instruction, evidence claim, direct address, contradiction, list/ranking |
| Resolution structure | resolved, unresolved, looped, withheld, twist, escalation |
| Viewer task | notice a detail, decide if real, reinterpret the scene, complete missing information, compare before/after, anticipate danger |

Topic clusters answer "what is it about?". Semantic-operation coding answers "what does it make the viewer do?".

### 9. Cross Semantic Structure With Performance

Report:

- distribution of top, comparison, and bottom videos across clusters
- cluster-level median, mean, and range of views
- whether top or bottom videos are concentrated
- whether any cluster is enriched among top videos
- whether an operation cuts across clusters
- important counterexamples

For enrichment, report where practical:

- baseline prevalence in the full corpus
- prevalence in the target group
- prevalence in the bottom group
- enrichment ratio
- top and bottom counts
- Fisher exact, binomial, permutation, or bootstrap test where useful

Prioritise counts, prevalence differences, enrichment ratios, effect sizes, examples, and counterexamples. Use significance tests only when they answer a specific uncertainty. Label post-hoc tests as exploratory, disclose multiple testing where relevant, and do not treat non-significance in a small target group as proof of no creative signal.

The result describes association and concentration. It does not by itself establish a performance mechanism.

### 10. Contrast Target and Comparison Groups

For the target group, identify:

- strict unique features
- enriched features
- dominant patterns
- absent or suppressed elements
- repeated semantic operations
- recurring content structures

Explicitly distinguish:

- features found only in the target group
- features more common in the target group
- features appearing in both groups but used differently

When a strict "only in target" question produces little signal, run the relaxed version:

```text
What is enriched, intensified, more central, differently sequenced, or more consistently coupled in the target group?
```

### 11. Extract Semantic Nodes

Create a compact set of semantic nodes that describes the target group's operative space. For each node provide:

- node name
- operational definition
- evidence basis
- target video IDs containing it
- comparison video IDs containing it
- classification as unique, enriched, common, or weak
- whether the node is topic-based, format-based, or operation-based

Prefer nodes that describe cognitive or narrative operations when the evidence supports them, such as inspection, anomaly detection, recognition, evidence accumulation, reclassification, identity instability, withheld confirmation, or unresolved implication.

### 12. Identify Central Instances

For each major node, list up to 20 central instances. An instance may be:

- a transcript phrase
- a caption fragment
- a hook
- a premise
- a repeated object or action
- a narrative move
- an on-screen text fragment

Each instance must cite its video ID and source field.

"Central" must refer to an explicit method, such as:

- proximity to a semantic cluster centroid
- TF-IDF contribution
- embedding centrality
- graph centrality
- recurrence across target videos
- manually selected qualitative centrality, clearly labelled as qualitative

### 13. Cluster the Instances

Extract content instances across videos and cluster them separately.

Report:

- the revised node structure
- bridges between nodes
- nodes that collapsed together
- newly visible distinctions
- changes from the earlier video-level node list
- what the instance-level pass reveals that was not already explicit

Skip this step when the corpus or transcript quality is too weak to support it. Document the reason.

### 14. Test Temporal and Narrative Structure

Look for recurrent ordering such as:

```text
opening hook -> ordinary setup -> anomaly -> evidence fragment -> reclassification -> unresolved implication -> replay prompt
```

Report whether a temporal sequence genuinely emerges.

State the evidence basis:

- timestamped transcript
- explicit hook/end fields
- direct video inspection
- caption-only inference

If order is inferred from captions or untimed text rather than direct video inspection or timestamped evidence, state that limitation.

### 15. Infer Generative Rules

Infer reusable rules only after corpus-level clustering and contrastive analysis.

For every proposed rule, separate:

1. observed pattern
2. inferred generative rule
3. speculative production implication
4. counterexamples
5. evidence strength: strong, moderate, weak, or speculative

Example rule:

```text
ordinary scene -> attention command -> anomalous detail -> evidence fragment -> reclassification -> unresolved implication
```

Rules may be broad, cluster-specific, or weak. Do not present a weak rule as a general law.

### 16. Conduct an Optional Direct-Video Audit

Use direct video inspection selectively after the structured-data analysis.

Choose videos that can test or refine the proposed rules:

- representative top performers
- representative bottom performers
- cluster centroids
- semantic-operation exemplars
- counterexamples
- ambiguous records with weak JSON evidence

Validate execution-level claims about:

- pacing and reveal timing
- framing and shot grammar
- motion and visual restraint
- text placement and sequencing
- audio use, only if audio is actually analysed
- loop mechanics and replay prompts

Report exactly what direct inspection added, contradicted, or left unresolved relative to the structured-data analysis.

### 17. Use Blind or Delayed Performance Review Where Practical

To reduce confirmation bias:

- create semantic clusters and labels before inspecting engagement groups where practical
- then cross the resulting labels with top, middle, and bottom performance bands
- avoid rewriting labels only to make top videos appear coherent
- preserve counterexamples and null results
- create a metric-stripped semantic working table when practical, keeping engagement data in a separate table joined later by video ID
- record when analysts or models first had access to engagement labels

This does not need to be perfect blinding, but the order of analysis should be recorded.

### 18. Produce the Final Report

Include:

- corpus and data-quality summary
- acquisition bias and confound summary
- engagement-distribution summary
- semantic-cluster taxonomy
- multi-axis coding summary
- top/bottom concentration analysis
- target-group differentiators
- semantic nodes and central instances
- instance-clustering findings where available
- temporal or narrative structure
- candidate generative rules
- counterexamples and limitations
- evidence ledger
- recommended next sample, audit, or collection step

The evidence ledger should make each important conclusion auditable:

| Finding or proposed rule | Supporting and contradicting videos | Evidence source | Evidence coverage | Confidence | Direct-video audit needed |
|---|---|---|---|---|---|
| Example finding | Video IDs | Caption, transcript, grounded visual field, or direct inspection | Count and proportion | Strong, moderate, weak, or speculative | Yes or no |

Evidence coverage refers to the records that can actually support or challenge the claim, not merely the total corpus size.

## Failure and No-Conclusion Conditions

Say "no reliable conclusion" or narrow the claim when:

- clusters are unstable across plausible parameters
- content fields are generic-only or mostly missing
- transcript coverage is too low for semantic claims
- visual fields are placeholders or unverified
- the target group is too small for the requested generalisation
- near-duplicates dominate the target group
- engagement differences are confounded by age, creator reach, or collection bias
- a claimed feature appears just as often in the bottom or comparison group
- a temporal claim depends only on untimed captions

Failure to find a clean signal is a valid result.

## Scalable Workflow

```text
Search-term discovery
    -> TikTok collection
        -> metadata + captions + transcripts
            -> corpus cleaning and evidence audit
                -> corpus tier + per-record evidence masks
                    -> semantic representation
                        -> corpus clustering
                            -> multi-axis semantic coding
                                -> engagement-group contrast
                                    -> semantic nodes and generative-rule hypotheses
                                        -> selective direct-video audit
                                            -> creative-strategy report
```

JSON and transcript analysis form the scalable layer. Direct video analysis is a selective audit layer. The two layers answer different questions and should not be collapsed into one another.

## Primary Guardrail

Never collapse "top videos belong to this cluster" into "this cluster causes high performance".

First test whether top videos are concentrated. Then test whether the same pattern is absent, weaker, or differently expressed in the comparison and bottom groups. Finally, look for cross-cluster semantic operations that distinguish the target group while preserving counterexamples.

## Core Analytical Move

Do not rely on one flat semantic cluster taxonomy as the main explanation. After clustering, perform a second multi-label coding pass that identifies cross-cluster operations.

The critical pattern may not be:

```text
top videos are about X
```

It may instead be:

```text
top videos make the viewer perform Y
```

## Project-Specific Prior Hypothesis

The initial `creepy tok` corpus produced the following candidate operation:

```text
ordinary scene -> anomaly -> evidence fragment -> reclassification -> unresolved implication
```

This is a prior finding, not part of the general method and not a default coding category. It must be re-tested on each new corpus rather than assumed. Preserve evidence for alternative sequences and null results.

## Stopping Record

The run-depth rules appear near the beginning of this document. At the end of an analysis, record:

- which run depth was used
- which optional stages were added and why
- what the last additional stage changed
- why the analysis stopped
- which unresolved question would justify further work
