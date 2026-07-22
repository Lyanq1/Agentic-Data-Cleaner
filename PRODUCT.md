# Product

## Register

product

## Platform

web

## Users

Primary users are data engineers and data analysts who upload datasets, inspect profiles, watch pipeline runs, resolve HITL checkpoints, and download cleaned output. Secondary users are domain experts who clarify requirements and validation choices without living in the technical details of every run.

## Product Purpose

Agentic Data Cleaner is a web console for controlled, agent-assisted data cleaning. Users keep the existing flow: upload a file, review statistical and semantic profiles, run the cleaning pipeline with human-in-the-loop checkpoints when needed, then inspect results and export. Success means two things equally: the operator always knows whether a run is executing or waiting for them, and the profile/EDA surfaces are clear enough to decide what to do next. Mass ingestion exists but is not a design priority.

## Positioning

This is a UI upgrade of the current product, not a new workflow. Every screen should reinforce that you can inspect data quality, run agentic cleaning with human checkpoints, and leave with output you trust, without changing the upload → profile → pipeline → HITL → result path.

## Brand Personality

Calm, precise, trustworthy. Voice is factual and ops-oriented: short labels, concrete status, no “AI magic” marketing tone. The interface should feel like a professional console that stays out of the way of the task.

## Anti-references

AI SaaS marketing chrome: purple/violet brand accents, glow effects, glassmorphism, and gradient-led decoration. Do not look like a generic generative-AI landing or demo skin.

## Design Principles

1. **Preserve the job, upgrade the clarity.** Keep the current flow; improve scanability, hierarchy, and trust, not the product shape.
2. **State before decoration.** Running vs needs-review vs failed must be obvious in seconds; visual flourish never competes with status.
3. **Inspectability builds trust.** Profile, plans, logs, and validation results are first-class, not secondary chrome around a “success” moment.
4. **HITL stays close to the decision.** Approve, modify, and reject sit with the content being reviewed, not buried under decorative panels.
5. **Calm ops console.** Density and borders do the work; restrained accent and semantic state colors only where they carry meaning.

## Accessibility & Inclusion

Target WCAG AA contrast for text and controls. Honor `prefers-reduced-motion` by dropping non-essential motion (decorative pulse, long choreography) while keeping essential loading feedback.
