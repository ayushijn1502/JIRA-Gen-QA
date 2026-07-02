# UI Progress And CSV Preview Spec

**Handoff:** For Composer 2 or a fresh implementation, use the **single** canonical document: [`docs/plans/ui-and-test-matrix-csv-implementation-plan.md`](./plans/ui-and-test-matrix-csv-implementation-plan.md) (it includes this spec, appendices with verbatim code, and `docs/test_matrix.md`). The sections below remain for browsing in-repo; they are duplicated in that plan.

## Objective

Update the desktop UI in this repository so the run screen:

1. shows one overall pipeline progress bar instead of an order-flow timeline or one bar per step
2. previews the generated CSV in the same screen before the user downloads it

**Test matrix CSV quality:** matrix rows must have proper, non-empty values in every column (especially `testcase`). Rules live in `docs/test_matrix.md`; the matrix step uses `PromptBuilder.build_test_matrix_prompt()` plus row normalization before writing the CSV (see `autotest_agent/agents/nodes.py`).

This spec is written for the current repository state and should be implementable without additional product clarification.

## Repository Scope

### Primary file

- `gui_app.py`

### Supporting files already involved in the flow

- `main.py`
- `autotest_agent/agents/nodes.py` (matrix CSV write + row normalization)
- `autotest_agent/agents/prompts.py` (`build_test_matrix_prompt`)
- `docs/test_matrix.md` (matrix CSV prompt rules)

### Documentation

- Canonical handoff: [`docs/plans/ui-and-test-matrix-csv-implementation-plan.md`](./plans/ui-and-test-matrix-csv-implementation-plan.md) (single file; includes this narrative and verbatim appendices).

## Current System Context

The GUI is a PySide6 desktop application.

The run flow already provides:

- stage updates through `on_stage`
- CSV-ready notification through `on_matrix_csv`
- a generated CSV file path that the UI can read from disk

The backend callback contract does not need to change for this feature.

## Required UI Changes

### 1. Replace the old progress presentation

The progress area must no longer show:

- a vertical order-style timeline
- connector lines between steps
- one progress bar per step

The progress area must now show:

- one shared progress bar for the full pipeline
- one current stage title
- one current stage description
- one overall percentage label

### 2. Progress behavior

The progress model must remain stage-based, not live within-step progress.

The percentage must be calculated from the current stage index in `PIPELINE_STEPS`.

Expected behavior:

- before the run starts: `0%`
- as each stage is reached: percentage increases based on stage position
- when the pipeline completes: `100%`
- on error: keep the bar at the last reached stage and show the error state in the stage text

The UI must continue using the existing `PIPELINE_STEPS` order in `gui_app.py`.

### 3. Current stage display

Below the shared progress bar, the UI must display:

- the current stage title
- the current stage description
- the overall percentage text

Expected state text behavior:

- idle state: a neutral message like "No run started yet"
- active state: show the matched title and description from `PIPELINE_STEPS`
- done state: show a completion message
- error state: show an error message using the last known failure summary

### 4. CSV preview section

A CSV preview section must appear in the JIRA ticket card, above the action row that contains:

- status text
- `Download CSV`
- `Run pipeline`

The preview section must include:

- a section title
- helper text for empty or reset state
- a scrollable table preview of the generated CSV

### 5. CSV preview behavior

When `_on_csv_ready()` receives a path:

- store the path in `_last_csv_path`
- enable the `Download CSV` button
- read the CSV from disk
- populate the preview table using the CSV headers and rows

The UI must handle these cases gracefully:

- file path missing
- file no longer exists
- CSV cannot be opened
- CSV exists but has no rows
- uneven row lengths

For uneven rows, blank values may be shown in missing cells.

### 6. Reset behavior

When a new run starts in `_on_start()`:

- clear `_last_csv_path`
- disable `Download CSV`
- clear the CSV preview table
- restore the preview helper text
- reset the progress bar to `0%`
- reset the current stage title and description to the idle state

## Non-Goals

This spec does not require:

- backend progress percentages inside individual long-running stages
- new stage callback types
- changes to the CLI output format
- CSV editing in the UI
- pagination for the CSV preview
- new automated tests

## Implementation Notes

### `gui_app.py`

Implementation is expected to be centered in `MainWindow`.

Relevant areas:

- `PIPELINE_STEPS`
- progress card layout
- `_update_pipeline_top_bar()`
- `_apply_pipeline_stage()`
- `_on_csv_ready()`
- `_on_start()`
- `_download_csv()`

Recommended implementation shape:

1. keep the existing top pipeline bar widget
2. replace the old step timeline widgets with one current-stage summary block
3. add a CSV preview widget in the ticket section
4. add a helper method to clear the preview state
5. add a helper method to load and render CSV data from disk

### `main.py`

No functional change is required unless a small status-text adjustment is needed.

### `autotest_agent/agents/nodes.py`

- `matrix_csv` must continue to call `on_matrix_csv` with the absolute CSV path after write.
- After the LLM returns `TestMatrixDocument`, normalize each row (strip whitespace, ensure non-empty fields, sensible fallback `testcase` with ticket id) before writing CSV so exported files and the GUI preview stay consistent.

## Acceptance Criteria

This change is complete only if all of the following are true:

1. The progress section shows one overall progress bar only.
2. The old vertical timeline or per-step progress cards are no longer visible.
3. The current stage title, description, and percentage update as the pipeline advances.
4. The percentage reaches `100%` on successful completion.
5. The CSV preview appears automatically after the matrix CSV is generated.
6. The CSV preview appears before the `Download CSV` button in the layout.
7. The CSV preview content matches the generated CSV file.
8. Starting a new run clears the old CSV preview and disables download until a new CSV is available.
9. The existing `Download CSV` action still saves the same CSV shown in the preview.

## Manual Validation

Use this checklist after implementation:

1. Launch the GUI from the repository.
2. Confirm the progress area shows only one shared progress bar.
3. Start a run and confirm the percentage changes as stages are reached.
4. Confirm the stage title and description change with the active stage.
5. Confirm the CSV preview appears once the matrix CSV is created.
6. Confirm the preview still allows the CSV to be downloaded.
7. Start another run and confirm the old preview is cleared before new output arrives.
8. Trigger or observe an error path and confirm the UI keeps the last known percentage while showing an error message.

## Developer Handoff

If another developer implements this spec, they should be able to complete the work by primarily editing `gui_app.py` and then validating the flow manually through the desktop app.
