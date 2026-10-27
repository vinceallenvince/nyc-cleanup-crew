# nyc-cleanup-crew

**Monster Poop:** snap some dog poop on a NYC sidewalk. A minute later it's back on your phone, under investigation by two pigeons in hazmat vests, one in a gas mask. A public-awareness nudge for dog owners to clean up.

Forked from [walk-and-hack](https://github.com/vinceallenvince/walk-and-hack).

## How it works

1. **Post:** The **Post Poop** iOS Shortcut commits the photo to `photos/poop-<timestamp>.jpg` through the GitHub Contents API.
2. **Classify:** The push triggers a GitHub Action. [Typesafe](https://docs.typesafe.ai/images) (Jev) answers three questions: is there poop, where the most prominent group sits in the frame (left, middle, right), and day or night.
3. **Gate:** No poop gets a "No poop detected." push, and the run stops. More than one is fine: the prompt focuses on the most prominent group.
4. **Scene:** `prompt/scenes.json` picks a scene from Jev's answers, plus that scene's placement for the position. The gas-mask pigeon goes between the poop and the nearer frame edge; the curious pigeon and the equipment take the open side. Middle is the accident scene: the gas-mask pigeon has retreated to the top of the equipment case, its mask and a loose feather left on the ground, and the curious pigeon looks up at it.
5. **Transform:** OpenAI's image edit (and optionally FLUX) renders `prompt/base.md` with the scene from `prompt/scenes/` filled in, plus a floodlight from `prompt/lighting.json` at night.
6. **Deliver:** The result is committed to `transformed/`, and a [Bark](https://github.com/Finb/Bark) push opens it when tapped.
7. **Browse:** Everything appears in the [gallery](https://vinceallenvince.github.io/nyc-cleanup-crew/) (GitHub Pages, `index.html`).

## Repo layout

| Path | What it is |
|---|---|
| `photos/` | Originals, posted by the Shortcut |
| `classifications/` | Jev's answers and the chosen placement, one JSON per photo |
| `transformed/` | Results (PNG). `<name>--flux.png` is the FLUX render. |
| `prompt/base.md` | Shared prompt, with `{{SCENE}}` and `{{LIGHTING}}` placeholders |
| `prompt/scenes/<scene>.md` | One scene's roles and poses, with a `{{PLACEMENT}}` placeholder |
| `prompt/scenes.json` | When each scene runs (`when`: Jev answers; one `default`) and its placement text per position |
| `prompt/lighting.json` | Lighting paragraph for `day` (empty) and `night` (floodlight) |
| `scripts/transform.py` | Classify → gate → place → transform |
| `.github/workflows/transform.yml` | Runs the script on every push to `photos/`, then commits and notifies |
| `index.html` | The gallery |

## Setup

Repository secrets (Settings → Secrets and variables → Actions):

| Secret | Used for |
|---|---|
| `OPENAI_API_KEY` | Image edit |
| `TYPESAFE_API_KEY` | Classification |
| `BARK_KEY` | Push notifications (the device key only, not the URL) |
| `REPLICATE_API_KEY` | FLUX renders on Replicate |

GitHub Pages: Settings → Pages → Deploy from branch → `main` / root.

## iOS Shortcut

Duplicate **Post Pigeon** (see the [walk-and-hack README](https://github.com/vinceallenvince/walk-and-hack#ios-shortcut-setup)) and rename it **Post Poop**. Then:

- **Token:** give your fine-grained token access to `nyc-cleanup-crew` too (Contents → Read and write), or make a new one.
- **Delete** the Choose from Menu step (step 6) and its branches. There are no themes.
- **Text (step 7):** `photos/poop-`**Formatted Date**`.jpg`
- **URL (step 8):** `https://api.github.com/repos/vinceallenvince/nyc-cleanup-crew/contents/`**Text**
- **Request body message:** `Add poop`
- **Notification:** `💩 Posted`

## Tweaks

- **Regenerate:** delete its PNG in `transformed/` and run the workflow (Actions → Run workflow).
- **Force a rejected photo through:** delete its JSON in `classifications/` and run the workflow.
- **Compare renderers:** set the repo variable `RENDERERS` to `openai,flux`, or type it into Run workflow. `FLUX_MODEL` picks the FLUX.2 model (default `black-forest-labs/flux-2-max`).
- **Cost guard:** each run handles only the newest unprocessed photo (`MAX_PER_RUN = 1`), with one render per renderer.
