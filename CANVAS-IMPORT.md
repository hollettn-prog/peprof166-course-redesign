# Repeatable Canvas page export

Edit canvas/pages files and course-map.json, then run:

```sh
python3 scripts/canvas_workflow.py validate .
python3 scripts/canvas_workflow.py build .
```

The GitHub build workflow performs the same validation and creates an artifact containing the .imscc and validation report. Download and extract the artifact; the inner .imscc is the Canvas package.

This is a page-only Canvas Common Cartridge. It preserves explicit module/page titles and order, uses stable IDs, checks local links and archive references, and marks imported pages unpublished. It does not contain instructor keys, native assignments, discussions, quizzes, SCORM packages, rubrics, grades or submissions.

Use a confirmed empty sandbox for whole-package rehearsal. Settings > Import Course Content > Canvas Course Export Package can import the inner .imscc. Inspect warnings, page conversion, module order, saved HTML and target-course native/media links before publication. Never import the whole package over an established course without checking for duplicate items. Stable IDs do not guarantee duplicate-free repeated imports.

For existing courses, use course-map.json source_url to open the exact existing page and update only its HTML body, preserving current titles, publication, access and grading settings. Keep native assessment tools unchanged. Verify after Save. Public hosted practice previews do not record Canvas grades or completion.
