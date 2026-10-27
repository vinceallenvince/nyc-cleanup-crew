# CLAUDE.md

Guidance for coding agents working in this repo. See `README.md` for what the app does. Forked from `vinceallenvince/walk-and-hack`; same plumbing, different job.

## Ownership and style

- The owner is Vince. He's experienced, prefers tight and punchy prose, and often works from his phone.
- Keep answers and commit messages short.
- Edits often get pasted into github.com on mobile. Prefer small, self-contained changes, and say exactly which file and line changed.

## Architecture in one breath

iOS Shortcut ("Post Poop") → GitHub Contents API → `photos/poop-yyyyMMdd-HHmmss.jpg` → push triggers `.github/workflows/transform.yml` → `scripts/transform.py`:

1. Classify with Typesafe/Jev: `poop` (present, none) `position` of the most prominent group (left, middle, right), and `light` (day, night).
2. Gate: no poop sends a Bark push and stops. Multiple poops are fine; the prompt targets the most prominent group.
3. Pick the placement paragraph for the position from `prompt/placement.json` (middle: the accident scene, mirrored by a seeded choice; unknown: left or right).
4. Fill `{{PLACEMENT}}` and `{{LIGHTING}}` (from `prompt/lighting.json`: floodlight at night, empty by day) in `prompt/prompt.md` and run each renderer.
5. Write `transformed/<stem>.png` (FLUX: `<stem>--flux.png`).

The workflow then commits, pushes, and sends the success push through Bark. `index.html`, served by GitHub Pages, lists `transformed/` through the GitHub API.

## Key facts

- **No creative content in Python.** The prompt and placement text live in `prompt/`.
- **Placement rule:** the gas-mask pigeon goes between the poop and the nearer frame edge; the curious pigeon and equipment take the open side. Middle is the accident scene: it overrides the prompt's pose and gas-mask rules.
- **Secrets:** `OPENAI_API_KEY`, `TYPESAFE_API_KEY`, `BARK_KEY`, `REPLICATE_API_KEY`. Never print secrets. Action logs are public.
- **Models:** image edit uses `IMAGE_MODEL` (workflow, currently `gpt-image-2.5-sunburst`). FLUX uses `FLUX_MODEL` on Replicate (default `black-forest-labs/flux-2-max`, FLUX.2 only). `RENDERERS` (default `openai`) picks which run. Classification uses `jev-latest`.
- **Typesafe image API:** every request needs `TypeSafe-Danger-Zone-Images: true`. Images must be PNG or JPEG, 280–1568 px per side; `jpeg_for_typesafe()` handles this. Docs: https://docs.typesafe.ai/images
- **Bark:** POST to `https://api.day.app/<BARK_KEY>` with `title`, `body`, `url`, `group`, `level=timeSensitive`.
- **Idempotency:** a photo is done once every renderer's output exists, or once its classification has `poop: none`. To regenerate, delete the PNG. To force a rejected photo through, delete the JSON.
- **Cost guard:** `MAX_PER_RUN = 1`. Don't raise it without asking.
- **No loops:** bot commits use `GITHUB_TOKEN`, so they don't retrigger the workflow. The workflow does `git pull --rebase` before pushing.
- **Hardcoded repo path:** `vinceallenvince/nyc-cleanup-crew` appears in `index.html`, `scripts/transform.py`, the workflow, and the iOS Shortcut.

## Working on it

- **Syntax checks:** `python3 -m py_compile scripts/transform.py` and `python3 -c "import yaml; yaml.safe_load(open('.github/workflows/transform.yml'))"`.
- **Prompt files are creative direction owned by Vince.** Keep his wording; change structure only when asked.
- **Don't** let prompts change the scene, enlarge, move, or add poop. "Preserve the original photo" is the top rule.
