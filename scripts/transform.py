"""Classify, then transform, every poop photo that hasn't been handled yet.

Stage 1 (Typesafe / Jev): one request, two Choice questions about
    photos/<name>.jpg — is there poop, and where the most prominent group is
    in the frame (left, middle, right). Saved in classifications/<name>.json.
Stage 2 (gate): no poop means a Bark push and stop.
Stage 3 (renderers): fill prompt/prompt.md with the placement for that
    position (prompt/placement.json) and edit the photo with each renderer in
    RENDERERS (default "openai"): OpenAI writes transformed/<name>.png,
    FLUX on Replicate writes transformed/<name>--flux.png.

Idempotent: a photo is done once every renderer's output exists, or once it
has been rejected. Only missing outputs render.
"""

import base64
import io
import json
import os
import pathlib
import random
import re
import sys
import time
import uuid

import requests
from openai import OpenAI
from PIL import Image, ImageOps

MODEL = os.environ.get("IMAGE_MODEL", "gpt-image-2.5-sunburst")
SRC = pathlib.Path("photos")
OUT = pathlib.Path("transformed")
CLS = pathlib.Path("classifications")
PROMPT = pathlib.Path("prompt")
TITLE = "Monster Poop 💩"
MAX_PER_RUN = 1  # cost guard: newest photo only (one render per renderer)
RENDERERS = [r.strip() for r in os.environ.get("RENDERERS", "openai").split(",") if r.strip()]
SUFFIX = {"openai": "", "flux": "--flux"}  # output filename suffix per renderer
if not RENDERERS or set(RENDERERS) - set(SUFFIX):
    raise SystemExit(f"RENDERERS must be a list of {sorted(SUFFIX)}, got {RENDERERS}")

REPLICATE_KEY = os.environ.get("REPLICATE_API_KEY")
FLUX_MODEL = os.environ.get("FLUX_MODEL", "black-forest-labs/flux-2-max")
RAW = "https://raw.githubusercontent.com/vinceallenvince/nyc-cleanup-crew/main"

TYPESAFE_URL = "https://api.typesafe.ai/v1/systemone"
TYPESAFE_KEY = os.environ.get("TYPESAFE_API_KEY")

# --- What Jev classifies. Option names are what come back. -----------------

QUESTIONS = {
    "poop": {
        "instructions": "Is there any dog poop in `photo`?",
        "criteria": {
            "present": "There is at least one piece of dog poop in the photo.",
            "none": "There is no dog poop in the photo.",
        },
    },
    "position": {
        "instructions": "Where is the most prominent group of dog poop horizontally in the frame of `photo`?",
        "criteria": {
            "left": "In the left third of the frame.",
            "middle": "In the middle third of the frame.",
            "right": "In the right third of the frame.",
        },
    },
}
REJECT = {"none": "No poop detected."}

# ---------------------------------------------------------------------------

openai_client = OpenAI()
OUT.mkdir(exist_ok=True)
CLS.mkdir(exist_ok=True)

TEMPLATE = (PROMPT / "prompt.md").read_text()
PLACEMENT = json.loads((PROMPT / "placement.json").read_text())
if set(re.findall(r"\{\{(\w+)\}\}", TEMPLATE)) != {"PLACEMENT"}:
    raise SystemExit("prompt.md must use exactly one placeholder, {{PLACEMENT}}")
if set(PLACEMENT) != set(QUESTIONS["position"]["criteria"]):
    raise SystemExit("placement.json keys must match the position options")


def output_path(stem: str, renderer: str = "openai") -> pathlib.Path:
    return OUT / f"{stem}{SUFFIX[renderer]}.png"


def is_done(p: pathlib.Path) -> bool:
    if all(output_path(p.stem, r).exists() for r in RENDERERS):
        return True
    cls_file = CLS / f"{p.stem}.json"
    return cls_file.exists() and json.loads(cls_file.read_text()).get("poop") in REJECT


def jpeg_for_typesafe(path: pathlib.Path) -> str:
    """Return base64 JPEG that fits Typesafe's 280–1568px per-side limits."""
    img = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
    img.thumbnail((1568, 1568))
    if min(img.size) < 280:
        scale = 280 / min(img.size)
        img = img.resize((round(img.width * scale), round(img.height * scale)))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return base64.b64encode(buf.getvalue()).decode()


def choice_value(answer):
    """Pull the chosen option name out of an answer."""
    if isinstance(answer, str):
        return answer
    if isinstance(answer, dict):
        for key in ("choice", "answer", "value", "option", "result"):
            if isinstance(answer.get(key), str):
                return answer[key]
    return None


def classify(path: pathlib.Path) -> dict:
    ref = f"{uuid.uuid4()}-photo"
    body = {
        "model": "jev-latest",
        "state": {"photo": ref},
        "assets": {
            ref: {"type": "image", "format": "jpg", "data_base64": jpeg_for_typesafe(path)}
        },
        "questions": {
            name: {"type": "choice", **q} for name, q in QUESTIONS.items()
        },
    }
    r = requests.post(
        TYPESAFE_URL,
        json=body,
        headers={
            "Authorization": f"Bearer {TYPESAFE_KEY}",
            "TypeSafe-Danger-Zone-Images": "true",
        },
        timeout=120,
    )
    if not r.ok:
        raise RuntimeError(f"Typesafe {r.status_code}: {r.text[:500]}")
    answers = r.json().get("answers", {})
    print(f"   typesafe answers: {json.dumps(answers)[:800]}")
    result = {name: choice_value(answers.get(name)) for name in QUESTIONS}
    result["raw"] = answers
    return result


def pick_placement(stem: str, position) -> str:
    """Placement text for the poop's position. Middle picks a side, seeded by
    filename so re-runs match. Unknown position counts as middle."""
    value = PLACEMENT.get(position) or PLACEMENT["middle"]
    return value if isinstance(value, str) else random.Random(stem).choice(value)


def build_prompt(placement: str) -> str:
    prompt = TEMPLATE.replace("{{PLACEMENT}}", placement)
    if "{{" in prompt:
        raise RuntimeError("unfilled placeholder in prompt")
    return prompt


def render_openai(src: pathlib.Path, prompt: str) -> bytes:
    with open(src, "rb") as f:
        out = openai_client.images.edit(model=MODEL, image=f, prompt=prompt)
    return base64.b64decode(out.data[0].b64_json)


def render_flux(src: pathlib.Path, prompt: str) -> bytes:
    """Run FLUX_MODEL on Replicate with the photo's raw GitHub URL as input."""
    if not REPLICATE_KEY:
        raise RuntimeError("REPLICATE_API_KEY is not set")
    auth = {"Authorization": f"Bearer {REPLICATE_KEY}"}
    r = requests.post(
        f"https://api.replicate.com/v1/models/{FLUX_MODEL}/predictions",
        json={"input": {
            "prompt": prompt,
            "input_images": [f"{RAW}/{src.as_posix()}"],
            "aspect_ratio": "match_input_image",
        }},
        headers={**auth, "Prefer": "wait=60"},
        timeout=90,
    )
    if not r.ok:
        raise RuntimeError(f"Replicate {r.status_code}: {r.text[:500]}")
    pred = r.json()
    poll = pred["urls"]["get"]
    deadline = time.time() + 300
    while pred["status"] not in ("succeeded", "failed", "canceled"):
        if time.time() > deadline:
            raise TimeoutError(f"Replicate prediction {pred.get('id')} still {pred['status']}")
        time.sleep(3)
        pred = requests.get(poll, headers=auth, timeout=30).json()
    if pred["status"] != "succeeded":
        raise RuntimeError(f"Replicate {pred['status']}: {pred.get('error')}")
    out = pred["output"]
    img = requests.get(out[0] if isinstance(out, list) else out, timeout=60)
    img.raise_for_status()
    buf = io.BytesIO()
    Image.open(io.BytesIO(img.content)).save(buf, format="PNG")
    return buf.getvalue()


RENDER = {"openai": render_openai, "flux": render_flux}


def set_output(**values) -> None:
    """Hand results to later workflow steps."""
    path = os.environ.get("GITHUB_OUTPUT")
    if not path:
        return
    with open(path, "a") as f:
        for k, v in values.items():
            f.write(f"{k}={str(v).replace(chr(10), ' ')}\n")


def notify_rejected(path: pathlib.Path, title: str) -> None:
    key = os.environ.get("BARK_KEY")
    if not key:
        return
    try:
        r = requests.post(
            f"https://api.day.app/{key}",
            data={
                "title": title,
                "body": "Tap to see the photo.",
                "url": f"{RAW}/{path.as_posix()}",
                "group": "poop",
                "level": "timeSensitive",
            },
            timeout=15,
        )
        print(f"   sent rejection notification ({r.status_code})")
    except Exception as e:
        print(f"   notification failed: {e}")


photos = sorted(SRC.glob("*.jpg"), key=lambda p: p.name, reverse=True)  # newest first
todo = [p for p in photos if p.stat().st_size > 0 and not is_done(p)][:MAX_PER_RUN]

if not todo:
    print("Nothing to do.")
    sys.exit(0)

failed = 0
for src in todo:
    print(f"-> {src.name}")
    try:
        # Stage 1: classify (reuse a saved result if there is one)
        cls_file = CLS / f"{src.stem}.json"
        if cls_file.exists():
            result = json.loads(cls_file.read_text())
        elif TYPESAFE_KEY:
            result = classify(src)
        else:
            result = {"poop": None}

        poop, position = result.get("poop"), result.get("position")
        print(f"   poop: {poop}, position: {position}")

        # Stage 2: gate
        if poop in REJECT:
            cls_file.write_text(json.dumps(result, indent=2))
            print(f"   rejected: {REJECT[poop]}")
            notify_rejected(src, REJECT[poop])
            continue
        if poop is None:
            print("   no classification, transforming with defaults")

        # Stage 3: render with each renderer that hasn't produced output yet
        result["placement"] = pick_placement(src.stem, position)
        cls_file.write_text(json.dumps(result, indent=2))
        prompt = build_prompt(result["placement"])
        made, errors = [], 0
        for renderer in RENDERERS:
            dest = output_path(src.stem, renderer)
            if dest.exists():
                continue
            try:
                dest.write_bytes(RENDER[renderer](src, prompt))
                print(f"   ok ({renderer}): {dest}")
                made.append(dest.as_posix())
            except Exception as e:
                errors += 1
                print(f"   {renderer} failed: {type(e).__name__}: {e}")
        if made:
            set_output(title=TITLE, paths=" ".join(made))
        elif errors:
            raise RuntimeError("every renderer failed")
    except Exception as e:
        failed += 1
        print(f"   failed: {type(e).__name__}: {e}")

sys.exit(1 if failed == len(todo) else 0)
