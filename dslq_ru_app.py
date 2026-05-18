"""
dslq_ru_app.py
==============

Опросник уровня стресса у собак (DSLQ) — русскоязычное Streamlit-приложение.

Administers the questionnaire, computes the chronic stress score, and optionally
persists records to Supabase (`dslq_sessions` for research data, `dslq_contacts`
for future-contact details). Supabase diagnostics are stored in `st.session_state`
and shown on the Result / Completion screens so errors do not disappear on rerun.

Input files (relative paths)
----------------------------
Place CSVs next to this script or in a sibling `Source/` folder:

- `DSLQ_App_Copy.csv`
- `DSLQ_App_BehaviorItems.csv`
- `DSLQ_App_OptionalModules.csv`
- `DSLQ_App_ResponseOptions.csv`
- `DSLQ_App_ScoringConfig.csv`

Output
------
- Supabase (default): REST inserts; no local files unless using local storage mode.
- Local fallback: `dslq_sessions/<session_id>.json` under the data directory.

Run
---
From this folder (`DSLQ_RU_App`):

    streamlit run dslq_ru_app.py
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import streamlit as st

# ─────────────────────────────────────────────
# 0. PAGE CONFIG
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="Dog Stress Level Questionnaire",
    page_icon="🐾",
    layout="centered",
)

# ─────────────────────────────────────────────
# 1. VISUAL STYLE  (mirrors PPS visual language)
# ─────────────────────────────────────────────
st.markdown(
    """
<style>
html, body, [data-testid="stAppViewContainer"] {
    font-family: "Inter", "Helvetica Neue", Arial, sans-serif;
    background-color: #F7F8FA;
    color: #1C1C1E;
}
.dslq-card {
    background: #FFFFFF;
    border-radius: 14px;
    padding: 24px 28px;
    margin-bottom: 16px;
    box-shadow: 0 2px 10px rgba(0,0,0,0.07);
}
.dslq-section-label {
    font-size: 0.75rem;
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: #8E8E93;
    margin-bottom: 6px;
}
.dslq-question {
    font-size: 1.02rem;
    font-weight: 500;
    line-height: 1.6;
    color: #1C1C1E;
}
.band-normal   { background:#D1FAE5; color:#065F46; padding:4px 14px; border-radius:20px; font-weight:700; font-size:0.9rem; display:inline-block; }
.band-elevated { background:#FEF3C7; color:#92400E; padding:4px 14px; border-radius:20px; font-weight:700; font-size:0.9rem; display:inline-block; }
.band-high     { background:#FEE2E2; color:#991B1B; padding:4px 14px; border-radius:20px; font-weight:700; font-size:0.9rem; display:inline-block; }
.band-ultra    { background:#7C3AED; color:#FFFFFF;  padding:4px 14px; border-radius:20px; font-weight:700; font-size:0.9rem; display:inline-block; }
.health-chronic  { background:#FFF7ED; color:#C2410C; padding:4px 14px; border-radius:20px; font-weight:600; font-size:0.85rem; display:inline-block; }
.health-neutral  { background:#F0FDF4; color:#166534; padding:4px 14px; border-radius:20px; font-weight:600; font-size:0.85rem; display:inline-block; }
.health-info     { background:#EFF6FF; color:#1D4ED8; padding:4px 14px; border-radius:20px; font-weight:600; font-size:0.85rem; display:inline-block; }
.disclaimer { font-size:0.78rem; color:#8E8E93; line-height:1.5; margin-top:8px; }
.result-note { font-size:1rem; color:#3A3A3C; line-height:1.55; margin-top:12px; }
.result-note p { margin:0 0 8px 0; }
.progress-label { font-size:0.8rem; color:#8E8E93; margin-bottom:2px; }
</style>
""",
    unsafe_allow_html=True,
)

# ─────────────────────────────────────────────
# 2. DATA LOADING  (from CSV files)
# ─────────────────────────────────────────────

CSV_NAMES = {
    "copy": "DSLQ_App_Copy.csv",
    "behavior": "DSLQ_App_BehaviorItems.csv",
    "optional": "DSLQ_App_OptionalModules.csv",
    "options": "DSLQ_App_ResponseOptions.csv",
    "config": "DSLQ_App_ScoringConfig.csv",
}

# Search order: script dir, script/Source, cwd, cwd/Source, one level up, one level up/Source
_ROOT = Path(__file__).resolve().parent
_BASE_CANDIDATES = [
    _ROOT,
    _ROOT / "Source",
    Path.cwd(),
    Path.cwd() / "Source",
    _ROOT.parent,
    _ROOT.parent / "Source",
]


def _read_csv(path: Path) -> pd.DataFrame:
    """Read CSV with encoding fallback (utf-8 → utf-8-sig → cp1252 → latin1)."""
    last_err: Exception = RuntimeError("No encodings tried")
    for enc in ("utf-8", "utf-8-sig", "cp1252", "latin1"):
        try:
            return pd.read_csv(path, encoding=enc)
        except Exception as e:
            last_err = e
    raise last_err


@st.cache_data(show_spinner=False)
def find_data_dir() -> Path:
    """Search for CSV files across candidate directories."""
    for base in _BASE_CANDIDATES:
        if all((base / name).is_file() for name in CSV_NAMES.values()):
            return base
    raise FileNotFoundError(
        "Could not find required DSLQ CSV files. "
        "Place them next to the script or in a Source/ subfolder."
    )


@st.cache_data(show_spinner=False)
def load_all_csvs() -> Dict[str, pd.DataFrame]:
    base = find_data_dir()
    return {key: _read_csv(base / name) for key, name in CSV_NAMES.items()}


@st.cache_data(show_spinner=False)
def build_copy_map(_df: pd.DataFrame) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for _, row in _df.iterrows():
        key = str(row["key"]).strip()
        text = str(row["text"]) if pd.notna(row["text"]) else ""
        # Fix encoding artefacts from any source encoding
        text = text.replace("\ufffd", "'").replace("\u2019", "'")
        out[key] = text
    return out


def c_get(key: str, default: str = "") -> str:
    """Copy lookup with non-empty fallback (returns default if value is blank)."""
    val = COPY.get(key, "")
    return val if val and val.strip() else default


@st.cache_data(show_spinner=False)
def build_option_sets(_df: pd.DataFrame) -> Dict[str, List[Tuple[int, str]]]:
    out: Dict[str, List[Tuple[int, str]]] = {}
    for option_set, grp in _df.groupby("option_set", sort=False):
        out[str(option_set)] = [
            (int(r["value"]), str(r["label"]))
            for _, r in grp.sort_values("value").iterrows()
        ]
    return out


@st.cache_data(show_spinner=False)
def build_scoring_thresholds(_df: pd.DataFrame) -> Dict[str, float]:
    sub = _df[_df["module"] == "dslq_chronic"]
    numeric_params = {
        "band_normal_upper",
        "band_elevated_upper",
        "band_high_upper",
        "max_observed",
        "mean",
        "sd",
        "median",
        "p75",
        "p90",
        "reference_sample_n",
    }
    out: Dict[str, float] = {}
    for _, row in sub.iterrows():
        p = str(row["parameter"])
        if p in numeric_params:
            try:
                out[p] = float(row["value"])
            except (TypeError, ValueError):
                pass
    return out


# Load everything once
_DATA = load_all_csvs()
COPY = build_copy_map(_DATA["copy"])
OPT_SETS = build_option_sets(_DATA["options"])
THRESHOLDS = build_scoring_thresholds(_DATA["config"])
BEHAVIOR_DF = _DATA["behavior"].sort_values("question_number").reset_index(drop=True)
OPTIONAL_DF = _DATA["optional"]


def c(key: str, default: str = "") -> str:
    """Copy lookup — returns default if key missing OR value is empty."""
    return c_get(key, default)


def opt(option_set: str) -> List[Tuple[int, str]]:
    return OPT_SETS[option_set]


def thr(param: str, default: float = 0.0) -> float:
    return THRESHOLDS.get(param, default)


# ─────────────────────────────────────────────
# 3. CANONICAL KEYS  (Doc6 table)
# ─────────────────────────────────────────────

CANONICAL_KEY_BY_QNUM: Dict[int, str] = {
    1: "Stereotypic",
    2: "Panting",
    3: "Dog_Play_FamHum",
    4: "Trembling",
    5: "Concentration",
    6: "Itching",
    7: "Improper_Urination",
    8: "Improper_Defecation",
    9: "Restless",
    10: "Dog_Play_Dogs",
    11: "Anxiety",
    12: "Air_Biting",
    13: "Excitement",
    14: "Mounting",
    15: "Aggressiveness",
    16: "Dog_Play_General",
    17: "Appetite_Loss",
    18: "Shadow_Hunting",
    19: "Leash_Biting",
    20: "Chewing",
    21: "Dog_New_Places",
    22: "Vocalization",
    23: "Grass_Eating",
    24: "Sound_Sensitivity",
    25: "Freezing",
    26: "Strange_Behavior",
    27: "Contact_Refuses",
    28: "Destroying",
    29: "Shaking",
    30: "Head_Away",
    31: "Dog_New_Dogs",
    32: "Yawning",
    33: "Licking",
    34: "Salivation",
    35: "Depression",
    36: "Sleep_Poorly",
    37: "Dog_New_Objects",
}

PROTECTIVE_KEYS = frozenset(
    {
        "Dog_Play_FamHum",
        "Dog_Play_Dogs",
        "Dog_Play_General",
        "Dog_New_Places",
        "Dog_New_Dogs",
        "Dog_New_Objects",
    }
)

# GH options without "Other" and "No, nothing like this".
# Sex-specific items (5, 6) are filtered at runtime based on dog_sex.
GH_OPTIONS_ALL: List[Tuple[int, str]] = [
    (1, "Качество шерсти ухудшилось (тусклая, выцветшая, выпадает, перхоть и т.п.)"),
    (2, "Собака значительно потеряла вес"),
    (3, "Появился неприятный запах тела или из пасти"),
    (4, "Появились проблемы с желудком/кишечником (запор, диарея, рвота и т.п.)"),
    (5, "Необычное поведение во время течки или изменения частоты течки"),  # females only
    (
        6,
        "Заметное возбуждение без присутствия сук в течке или их запаха",
    ),  # males only
]


def get_gh_options(dog_sex: str) -> List[Tuple[int, str]]:
    """Return GH options filtered by dog sex.

    "Предпочитаю не отвечать" / unknown -> show both sex-specific questions.
    """
    sex = dog_sex.lower() if dog_sex else ""
    known_female = sex in ("female", "f", "сука", "женский")
    known_male = sex in ("male", "m", "кобель", "мужской")
    unknown = not (known_female or known_male)
    result = []
    for code, lbl in GH_OPTIONS_ALL:
        if code == 5 and not (known_female or unknown):
            continue
        if code == 6 and not (known_male or unknown):
            continue
        result.append((code, lbl))
    return result


GH_LENGTH_OPTIONS: List[Tuple[int, str]] = [
    (1, "Меньше недели назад"),
    (2, "Меньше месяца назад"),
    (3, "Больше месяца назад"),
    (4, "Бывает по-разному / другое"),
]


def _normalize_gh_duration(duration_code: int) -> int:
    """Map 'It varies / Other' (4) to the same interpretation as 'Less than a week' (1)."""
    if int(duration_code) == 4:
        return 1
    return int(duration_code)


def _is_valid_email_simple(email: str) -> bool:
    """Practical email check without heavy regex (no spaces; local@domain with dot in domain)."""
    e = str(email or "")
    if not e or e.strip() != e:
        return False
    if " " in e:
        return False
    if "@" not in e:
        return False
    local, domain = e.split("@", 1)
    if not local or not domain:
        return False
    if "." not in domain:
        return False
    if domain.startswith(".") or domain.endswith(".") or ".." in domain:
        return False
    return True


# ─────────────────────────────────────────────
# 4. SCORING ENGINE  (Doc4 + Doc6)
# ─────────────────────────────────────────────

FW_WEIGHT: Dict[int, float] = {
    1: 1.0,
    2: 1.0,
    3: 2.0,
    4: 2.0,
    5: 3.0,
    6: 3.0,
    7: 3.0,
    8: 0.0,
    9: 1.0,
}


def _max_f(f_code: int) -> float:
    if f_code in (1, 2, 3):
        return float(f_code)
    if f_code == 4:
        return 1.0
    return 0.0


def score_symptom(main: Any, f_val: Any, fw_val: Any, l_val: Any) -> float:
    try:
        m = int(main)
    except Exception:
        return 0.0
    if m != 1:
        return 0.0
    try:
        l = int(l_val)
    except Exception:
        return 0.0
    if l != 2:
        return 0.0
    mf = _max_f(int(f_val)) if f_val is not None else 1.0
    w = FW_WEIGHT.get(int(fw_val) if fw_val is not None else 9, 1.0)
    return (mf * w) / 9.0


def score_protective(val: Any) -> float:
    try:
        return 1.0 if int(val) == 2 else 0.0
    except Exception:
        return 0.0


def interpret_band(score: float) -> str:
    """Correct <= boundaries (Doc4 v1 sigma thresholds)."""
    if score > thr("max_observed", 10.11):
        return "ultra_high"
    if score > thr("band_elevated_upper", 7.98):
        return "high"
    if score > thr("band_normal_upper", 5.60):
        return "elevated"
    return "normal"


def health_flag(answers: Dict[str, Any]) -> str:
    """Derive health flag from per-item gh_durations (new flow).

    Returns:
        'none'     – no health signs selected
        'reported' – at least one sign selected
        'chronic'  – at least one sign has duration code 3 (Over a month ago)
    """
    # gh_durations: {code: duration_int} where -1 means No (not selected)
    gh = answers.get("gh_durations") or {}
    positive_durs = []
    for _, v in gh.items():
        try:
            dur = int(v)
        except (TypeError, ValueError):
            continue
        if dur != -1:
            positive_durs.append(dur)

    if not positive_durs:
        return "none"
    if any(d == 3 for d in positive_durs):
        return "chronic"
    return "reported"


@dataclass
class ScoreResult:
    total: float
    band: str
    scale_pos: float
    item_scores: Dict[str, float]
    health: str  # "none" | "reported" | "chronic"


def compute_score(answers: Dict[str, Any]) -> ScoreResult:
    item_scores: Dict[str, float] = {}
    total = 0.0
    for _, row in BEHAVIOR_DF.iterrows():
        qn = int(row["question_number"])
        base = CANONICAL_KEY_BY_QNUM[qn]
        rtype = str(row["response_type"])
        if rtype == "binary_protective":
            s = score_protective(answers.get(base))
        else:
            s = score_symptom(
                answers.get(f"{base}_Main"),
                answers.get(f"{base}_f"),
                answers.get(f"{base}_f_w"),
                answers.get(f"{base}_l"),
            )
        item_scores[base] = s
        total += s

    band = interpret_band(total)
    max_obs = thr("max_observed", 10.11)
    scale_pos = 1.0 if total > max_obs else max(0.0, min(total / max_obs, 1.0))

    return ScoreResult(
        total=round(total, 4),
        band=band,
        scale_pos=scale_pos,
        item_scores=item_scores,
        health=health_flag(answers),
    )


# ─────────────────────────────────────────────
# 5. STORAGE  (pluggable)
# ─────────────────────────────────────────────

STORAGE_MODE = "supabase"  # "none" | "local" | "supabase"
APP_VERSION = "ru-v1"
DEFAULT_SESSIONS_TABLE = "dslq_ru_sessions"
DEFAULT_CONTACTS_TABLE = "dslq_ru_contacts"

# Human optional fields that belong only on the contact screen (not stored in human_demographics).
HUMAN_DEMO_EXCLUDED_FIELD_KEYS = frozenset(
    {
        "contact_name",
        "contact_email",
        "first_name",
        "last_name",
        "surname",
        "human_first_name",
        "human_last_name",
        "participant_name",
        "owner_name",
        "human_name",
        "corvallis_distance",  # legacy; not in human demographics; ignore if present in CSV
    }
)


def _human_demo_for_export(human_demo: Dict[str, Any]) -> Dict[str, Any]:
    """Strip contact/name fields so human_demographics never duplicates contact data."""
    return {k: v for k, v in human_demo.items() if k not in HUMAN_DEMO_EXCLUDED_FIELD_KEYS}


def _set_supabase_diag(error: Optional[str], traceback_text: Optional[str]) -> None:
    """Persist Supabase diagnostics in session state for later screens."""
    if error:
        st.session_state["supabase_error"] = str(error)
    else:
        st.session_state["supabase_error"] = None
    if traceback_text:
        st.session_state["supabase_traceback"] = str(traceback_text)
    else:
        st.session_state["supabase_traceback"] = None


def _set_supabase_contact_diag(error: Optional[str], traceback_text: Optional[str]) -> None:
    """Persist Supabase contact-table diagnostics in session state."""
    if error:
        st.session_state["supabase_contact_error"] = str(error)
    else:
        st.session_state["supabase_contact_error"] = None
    if traceback_text:
        st.session_state["supabase_contact_traceback"] = str(traceback_text)
    else:
        st.session_state["supabase_contact_traceback"] = None


def _supabase_insert(payload: Dict[str, Any]) -> bool:
    """Insert one session record into Supabase. Returns True on success.

    Important: we do NOT call st.error() here, because Streamlit reruns can
    immediately navigate away. Instead, diagnostics are saved in session state
    and rendered on the result/completion screens.
    """
    try:
        import urllib.error
        import urllib.request

        secrets = st.secrets["supabase"]
        table = secrets.get("sessions_table", DEFAULT_SESSIONS_TABLE)
        url = secrets["url"].rstrip("/") + f"/rest/v1/{table}"
        key = secrets["key"]
        raw = payload.get("raw_answers_json", {})
        # Contact data lives only in table `dslq_contacts`; do not store contact_details here.
        record = {
            "session_id": payload.get("session_id"),
            "app_version": payload.get("app_version"),
            "dslq_chronic_score": payload.get("dslq_chronic_score"),
            "interpretation_band": payload.get("interpretation_band"),
            "health_flag": payload.get("health_flag"),
            "visual_scale_pos": payload.get("visual_scale_pos"),
            "item_scores": payload.get("item_scores"),
            "behavior_answers": raw.get("behavior_answers"),
            "general_health_answers": raw.get("general_health_answers"),
            "research_choices": payload.get("research_choices"),
            "dog_demographics": payload.get("dog_demographics"),
            "human_demographics": payload.get("human_demographics"),
            "consented_dog": bool(
                (payload.get("research_choices") or {}).get("share_questionnaire_data")
            ),
            "consented_demo": bool(
                (payload.get("research_choices") or {}).get("share_demographic_data")
            ),
        }
        data = json.dumps(record, ensure_ascii=False, default=str).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "apikey": key,
                "Authorization": f"Bearer {key}",
                "Prefer": "return=minimal",
            },
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            ok = resp.status in (200, 201)
            if ok:
                _set_supabase_diag(None, None)
            else:
                _set_supabase_diag(
                    f"Supabase insert failed (HTTP {resp.status}).",
                    None,
                )
            return ok
    except urllib.error.HTTPError as e:
        body_text = ""
        try:
            body_bytes = e.read()
            body_text = body_bytes.decode("utf-8", errors="replace") if body_bytes else ""
        except Exception:
            body_text = ""

        detail = body_text.strip() if body_text.strip() else "(empty response body)"
        _set_supabase_diag(
            f"Supabase insert failed: HTTP {e.code} {e.reason}. Response: {detail}",
            None,
        )
        return False
    except Exception as e:
        import traceback

        _set_supabase_diag(
            f"Supabase insert failed: {e}",
            traceback.format_exc(),
        )
        return False


def persist_session(payload: Dict[str, Any]) -> Optional[Path]:
    if STORAGE_MODE == "none":
        return None
    if STORAGE_MODE == "supabase":
        st.session_state["supabase_insert_ok"] = _supabase_insert(payload)
        return None  # no local path for supabase mode
    # local fallback
    try:
        base = find_data_dir() / "dslq_sessions"
        base.mkdir(exist_ok=True)
        out = base / f"{payload['session_id']}.json"
        out.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return out
    except Exception:
        return None


def _supabase_insert_contact(payload: Dict[str, Any]) -> bool:
    """Insert one contact record into Supabase table `dslq_contacts`.

    This is independent from research consent and must only contain contact data.
    """
    try:
        import urllib.error
        import urllib.request

        secrets = st.secrets["supabase"]
        table = secrets.get("contacts_table", DEFAULT_CONTACTS_TABLE)
        url = secrets["url"].rstrip("/") + f"/rest/v1/{table}"
        key = secrets["key"]

        contact = payload.get("contact_details") or {}
        record = {
            "session_id": payload.get("session_id"),
            "created_at": payload.get("created_at"),
            "name": contact.get("contact_name") or None,
            "email": contact.get("contact_email") or None,
            "consented_future_contact": bool((payload.get("research_choices") or {}).get("future_contact")),
            "app_version": payload.get("app_version"),
        }

        data = json.dumps(record, ensure_ascii=False, default=str).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "apikey": key,
                "Authorization": f"Bearer {key}",
                "Prefer": "return=minimal",
            },
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            ok = resp.status in (200, 201)
            if ok:
                _set_supabase_contact_diag(None, None)
            else:
                _set_supabase_contact_diag(
                    f"Supabase contact insert failed (HTTP {resp.status}).",
                    None,
                )
            return ok
    except urllib.error.HTTPError as e:
        body_text = ""
        try:
            body_bytes = e.read()
            body_text = body_bytes.decode("utf-8", errors="replace") if body_bytes else ""
        except Exception:
            body_text = ""

        detail = body_text.strip() if body_text.strip() else "(empty response body)"
        _set_supabase_contact_diag(
            f"Supabase contact insert failed: HTTP {e.code} {e.reason}. Response: {detail}",
            None,
        )
        return False
    except Exception as e:
        import traceback

        _set_supabase_contact_diag(
            f"Supabase contact insert failed: {e}",
            traceback.format_exc(),
        )
        return False


def persist_contact(payload: Dict[str, Any]) -> None:
    """Persist contact details to Supabase if eligible.

    Rules:
    - Save to `dslq_contacts` if future_contact == True and email is non-empty.
    - Must work independently from research consent.
    """
    if STORAGE_MODE != "supabase":
        st.session_state["supabase_contact_insert_ok"] = None
        _set_supabase_contact_diag(None, None)
        return

    contact = payload.get("contact_details") or {}
    wants = bool((payload.get("research_choices") or {}).get("future_contact"))
    email = str(contact.get("contact_email") or "").strip()

    if wants and email:
        st.session_state["supabase_contact_insert_ok"] = _supabase_insert_contact(payload)
    else:
        st.session_state["supabase_contact_insert_ok"] = None
        _set_supabase_contact_diag(None, None)


def build_export(
    result: ScoreResult,
    answers: Dict[str, Any],
    dog_demo: Dict,
    human_demo: Dict,
    contact: Dict,
    choices: Dict,
) -> Dict[str, Any]:
    # Keys that belong to general health (excluded from behavior_answers)
    gh_keys = {
        "Dog_Symptoms",
        "Dog_Symptoms_Length",
        "Dog_Symptoms_Other_Text",
        "gh_durations",
    }
    return {
        "session_id": st.session_state.get("session_id", str(uuid.uuid4())),
        "app_version": APP_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "dslq_chronic_score": result.total,
        "interpretation_band": result.band,
        "health_flag": result.health,
        "visual_scale_pos": result.scale_pos,
        "item_scores": result.item_scores,
        "raw_answers_json": {
            "behavior_answers": {k: v for k, v in answers.items() if k not in gh_keys},
            "general_health_answers": {
                "Dog_Symptoms": answers.get("Dog_Symptoms"),
                "gh_durations": answers.get("gh_durations"),
                "Dog_Symptoms_Other_Text": answers.get("Dog_Symptoms_Other_Text"),
            },
        },
        "research_choices": choices,
        "dog_demographics": dog_demo,
        "human_demographics": _human_demo_for_export(human_demo),
        # Kept for contact insert + local JSON; not written to Supabase dslq_sessions.
        "contact_details": contact,
    }


# ─────────────────────────────────────────────
# 6. SESSION STATE
# ─────────────────────────────────────────────


def init_state() -> None:
    defaults = {
        "page": "intro",
        "item_index": 0,
        "answers": {},
        "score_result": None,
        "dog_demo": {},
        "human_demo": {},
        "contact": {},
        "choices": {
            "share_questionnaire_data": False,
            "share_demographic_data": False,
            "future_contact": False,
        },
        "export_blob": None,
        "saved_path": None,
        "session_id": str(uuid.uuid4()),  # stable for entire session
        "dog_sex": "",  # set on sex_select screen
        # gh_selected removed — gh_durations is the single source of truth for health answers
        "gh_item_index": 0,  # which GH item we're asking duration for
        "gh_durations": {},  # code -> duration int
        # Supabase diagnostics (persist across screen transitions)
        "supabase_error": None,
        "supabase_traceback": None,
        "supabase_insert_ok": None,
        # Supabase diagnostics for contact table
        "supabase_contact_error": None,
        "supabase_contact_traceback": None,
        "supabase_contact_insert_ok": None,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


init_state()


def go(page: str) -> None:
    st.session_state["page"] = page
    st.rerun()


# ─────────────────────────────────────────────
# 7. SCALE RENDERING  (pure HTML, no Altair dep)
# ─────────────────────────────────────────────


def render_scale(score: float, scale_pos: float) -> None:
    max_obs = thr("max_observed", 10.11)
    n_upper = thr("band_normal_upper", 5.60)
    e_upper = thr("band_elevated_upper", 7.98)
    p_n = n_upper / max_obs * 100
    p_e = e_upper / max_obs * 100
    pos = scale_pos * 100

    html = f"""
    <div style="margin:14px 0 6px 0;">
      <div style="position:relative; height:52px;">
        <div style="display:flex; width:100%; height:18px; border-radius:999px;
                    overflow:hidden; box-shadow:inset 0 1px 3px rgba(0,0,0,.12);">
          <div style="width:{p_n:.2f}%; background:#86EFAC;"></div>
          <div style="width:{p_e-p_n:.2f}%; background:#FDE68A;"></div>
          <div style="width:{100-p_e:.2f}%; background:#FCA5A5;"></div>
        </div>
        <div style="position:absolute; left:calc({pos:.2f}% - 14px); top:-8px;
                    font-size:30px; line-height:1; filter:drop-shadow(0 1px 2px rgba(0,0,0,.25));">
          🐾
        </div>
      </div>
      <div style="display:flex; justify-content:space-between;
                  font-size:0.78rem; color:#6B7280; margin-top:4px;">
        <span>Норма</span>
        <span>Повышенный</span>
        <span>Высокий</span>
      </div>
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)


def render_supabase_diagnostics() -> None:
    """Render stored Supabase diagnostics (if any) on stable screens."""
    # Show session and contact errors separately (success on one must not hide failure on the other).
    err = st.session_state.get("supabase_error")
    tb = st.session_state.get("supabase_traceback")

    if err or tb:
        st.markdown("---")
        st.markdown("### Диагностика Supabase")
        if err:
            st.error(err)
        if tb:
            st.code(tb)

    contact_err = st.session_state.get("supabase_contact_error")
    contact_tb = st.session_state.get("supabase_contact_traceback")

    if contact_err or contact_tb:
        st.markdown("---")
        st.markdown("### Диагностика Supabase для контактов")
        if contact_err:
            st.error(contact_err)
        if contact_tb:
            st.code(contact_tb)


# ─────────────────────────────────────────────
# 8. SCREENS
# ─────────────────────────────────────────────


def screen_intro() -> None:
    st.markdown(f"## {c('screen_intro_title', 'Dog Stress Level Questionnaire')}")
    st.markdown(c("screen_intro_body"))
    st.info(f"⏱ {c('screen_intro_time')}")
    st.markdown(f"**{c('screen_intro_single_dog')}**")
    st.warning(f"ℹ️ {c('screen_intro_yes_hint')}")

    if st.button("Начать опросник ->", type="primary", use_container_width=True):
        st.session_state["item_index"] = 0
        go("sex_select")


def screen_sex_select() -> None:
    st.markdown(
        '<p class="dslq-question">Пол вашей собаки?</p>',
        unsafe_allow_html=True,
    )

    sex_options = ["Мужской", "Женский", "Не знаю / предпочитаю не отвечать"]
    sex = st.radio(
        "Пол вашей собаки?",
        options=sex_options,
        index=sex_options.index(st.session_state["dog_sex"])
        if st.session_state["dog_sex"] in sex_options
        else None,
        horizontal=True,
        key="sex_radio",
        label_visibility="collapsed",
    )

    st.markdown("")
    if st.button(
        "Начать опросник ->", type="primary", key="sex_next", disabled=(sex is None)
    ):
        st.session_state["dog_sex"] = sex if sex else ""
        go("questionnaire")


def screen_questionnaire() -> None:
    total = len(BEHAVIOR_DF)
    idx = int(st.session_state["item_index"])

    if idx >= total:
        go("general_health")
        return

    row = BEHAVIOR_DF.iloc[idx]
    qn = int(row["question_number"])
    base = CANONICAL_KEY_BY_QNUM[qn]
    rtype = str(row["response_type"])
    ans = st.session_state["answers"]

    # Progress (behaviour questions 1–37; total depends on dog sex for GH module)
    dog_sex_ = st.session_state.get("dog_sex", "")
    total_all = 37 + len(get_gh_options(dog_sex_))
    st.progress((idx + 1) / total_all)
    st.markdown(
        f'<p class="progress-label">Вопрос {idx + 1} из {total_all}</p>',
        unsafe_allow_html=True,
    )

    # Question card
    st.markdown(
        f'<div class="dslq-card">'
        f'<p class="dslq-section-label">Вопрос {qn}</p>'
        f'<p class="dslq-question">{str(row["question_text"])}</p>'
        f"</div>",
        unsafe_allow_html=True,
    )

    yn_codes = [code for code, _ in opt("yes_no")]

    # ── Main Yes/No radio (no form — live rerender needed for sub-questions) ──
    if rtype == "binary_protective":
        cur = ans.get(base)
        prot_default = (
            yn_codes.index(int(cur)) if cur is not None and int(cur) in yn_codes else None
        )
        choice = st.radio(
            "Выберите один вариант:",
            options=yn_codes,
            format_func=lambda v: "Да" if v == 1 else "Нет",
            index=prot_default,
            horizontal=True,
            key=f"prot_{idx}",
        )
        f_val = fw_val = l_val = None

    else:  # symptom_block
        cur_main = ans.get(f"{base}_Main")
        main_default = (
            yn_codes.index(int(cur_main))
            if cur_main is not None and int(cur_main) in yn_codes
            else None
        )
        choice = st.radio(
            "Выберите один вариант:",
            options=yn_codes,
            format_func=lambda v: "Да" if v == 1 else "Нет",
            index=main_default,
            horizontal=True,
            key=f"main_{idx}",
        )

        f_val = fw_val = l_val = None
        if choice == 1:
            st.markdown("---")
            f_options = opt("f_followup")
            fw_options = opt("fw_followup")
            l_options = opt("l_followup")

            cur_f = ans.get(f"{base}_f", f_options[0][0])
            cur_fw = ans.get(f"{base}_f_w", fw_options[0][0])
            cur_l = ans.get(f"{base}_l", l_options[1][0])  # default: >2 weeks

            f_codes = [code for code, _ in f_options]
            fw_codes = [code for code, _ in fw_options]
            l_codes = [code for code, _ in l_options]

            # f=4 (context-only) excluded — scoring uses frequency, not context
            f_codes_display = [c_ for c_ in f_codes if c_ != 4]
            cur_f_disp = cur_f if cur_f in f_codes_display else f_codes_display[0]
            f_val = st.radio(
                "Как часто это происходит в течение дня?",
                options=f_codes_display,
                format_func=lambda v: dict(f_options)[v],
                index=f_codes_display.index(cur_f_disp),
                horizontal=False,
                key=f"f_{idx}",
            )
            fw_val = st.radio(
                "В течение скольких дней в неделю это обычно происходит?",
                options=fw_codes,
                format_func=lambda v: dict(fw_options)[v],
                index=fw_codes.index(cur_fw) if cur_fw in fw_codes else 0,
                horizontal=False,
                key=f"fw_{idx}",
            )
            l_val = st.radio(
                "Когда вы впервые это заметили?",
                options=l_codes,
                format_func=lambda v: dict(l_options)[v],
                index=l_codes.index(cur_l) if cur_l in l_codes else 1,
                horizontal=False,
                key=f"l_{idx}",
            )

    # ── Navigation buttons ───────────────────────────────────────────────────
    st.markdown("")
    col_back, col_next = st.columns([1, 2])
    back = col_back.button("<- Назад", disabled=(idx == 0), key=f"back_{idx}")
    nxt = col_next.button("Продолжить ->", type="primary", key=f"next_{idx}")

    if back:
        st.session_state["item_index"] = max(0, idx - 1)
        st.rerun()

    if nxt:
        if choice is None:
            st.warning("Пожалуйста, выберите ответ, прежде чем продолжить.")
            st.stop()
        if rtype == "binary_protective":
            ans[base] = int(choice)
        else:
            ans[f"{base}_Main"] = int(choice)
            if choice == 1:
                ans[f"{base}_f"] = int(f_val)
                ans[f"{base}_f_w"] = int(fw_val)
                ans[f"{base}_l"] = int(l_val)
            else:
                for suf in ("_f", "_f_w", "_l"):
                    ans.pop(f"{base}{suf}", None)
        st.session_state["answers"] = ans
        st.session_state["item_index"] = idx + 1
        st.rerun()


def screen_general_health() -> None:
    """Q41: one sign per screen, Yes/No + if Yes immediately ask duration."""
    dog_sex = st.session_state.get("dog_sex", "")
    gh_opts = get_gh_options(dog_sex)
    total = len(gh_opts)
    gh_idx = int(st.session_state.get("gh_item_index", 0))
    durations = st.session_state.get("gh_durations", {})
    ans = st.session_state["answers"]

    # All signs done — save and move on
    if gh_idx >= total:
        selected_codes = [
            code for code, _ in gh_opts if durations.get(code) is not None and durations[code] != -1
        ]
        ans["Dog_Symptoms"] = selected_codes
        ans["gh_durations"] = {str(c_): v for c_, v in durations.items() if v != -1}
        st.session_state["answers"] = ans
        st.session_state["score_result"] = compute_score(ans)
        go("sharing")
        return

    code, symptom_lbl = gh_opts[gh_idx]
    yn_codes = [code_ for code_, _ in opt("yes_no")]

    # Progress (health questions 38..N out of 37+total total)
    total_all = 37 + total  # total = actual number of GH items for this dog's sex
    q_num_display = 37 + gh_idx + 1
    st.progress(min(q_num_display / total_all, 1.0))
    st.markdown(
        f'<p class="progress-label">Вопрос {q_num_display} из {total_all}</p>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<p class="dslq-section-label">Замечали ли вы у вашей собаки в последнее время следующие перемены:</p>'
        f'<p class="dslq-question">{symptom_lbl}</p>',
        unsafe_allow_html=True,
    )

    # Restore previous answer
    prev = durations.get(code)
    if prev is None:
        yn_idx = None
    elif prev == -1:
        yn_idx = yn_codes.index(2) if 2 in yn_codes else None  # No
    else:
        yn_idx = yn_codes.index(1) if 1 in yn_codes else None  # Yes

    choice = st.radio(
        "Выберите один вариант:",
        options=yn_codes,
        format_func=lambda v: "Да" if v == 1 else "Нет",
        index=yn_idx,
        horizontal=True,
        key=f"gh_yn_{gh_idx}",
    )

    dur_val = None
    if choice == 1:
        st.markdown("---")
        l_codes = [c_ for c_, _ in GH_LENGTH_OPTIONS]
        cur_dur = prev if (prev is not None and prev != -1) else None
        l_idx = l_codes.index(int(cur_dur)) if cur_dur and int(cur_dur) in l_codes else None
        dur_val = st.radio(
            "Когда вы впервые это заметили?",
            options=l_codes,
            format_func=lambda v: dict(GH_LENGTH_OPTIONS)[v],
            index=l_idx,
            horizontal=False,
            key=f"gh_dur_{gh_idx}",
        )

    st.markdown("")
    col_back, col_next = st.columns([1, 2])
    back = col_back.button("<- Назад", key=f"gh_back_{gh_idx}", disabled=(gh_idx == 0))
    nxt = col_next.button("Продолжить ->", type="primary", key=f"gh_next_{gh_idx}")

    if back:
        st.session_state["gh_item_index"] = max(0, gh_idx - 1)
        st.rerun()

    if nxt:
        if choice is None:
            st.warning("Пожалуйста, выберите ответ, прежде чем продолжить.")
            st.stop()
        if choice == 1:
            if dur_val is None:
                st.warning("Пожалуйста, укажите, когда вы впервые заметили этот признак.")
                st.stop()
            durations[code] = _normalize_gh_duration(int(dur_val))
        else:
            durations[code] = -1  # No
        st.session_state["gh_durations"] = durations
        st.session_state["gh_item_index"] = gh_idx + 1
        st.rerun()


def screen_gh_duration() -> None:
    """Redirect — merged into screen_general_health."""
    go("general_health")


BAND_CSS = {
    "normal": "band-normal",
    "elevated": "band-elevated",
    "high": "band-high",
    "ultra_high": "band-ultra",
}
BAND_LABEL = {
    "normal": "Норма",
    "elevated": "Повышенный",
    "high": "Высокий",
    "ultra_high": "Крайне высокий",
}
BAND_COPY_KEY = {
    "normal": "result_band_normal",
    "elevated": "result_band_elevated",
    "high": "result_band_high",
    "ultra_high": "result_band_ultra_high",
}


def screen_result() -> None:
    result: ScoreResult = st.session_state["score_result"] or compute_score(
        st.session_state["answers"]
    )
    st.session_state["score_result"] = result

    st.markdown(f"## {c('result_title', 'Результат скрининга хронического стресса')}")

    col1, col2 = st.columns([1, 2])
    with col1:
        st.metric(c("result_score_label", "Балл"), f"{result.total:.2f}")
    with col2:
        css = BAND_CSS[result.band]
        lbl = BAND_LABEL[result.band]
        st.markdown(f'<br><span class="{css}">{lbl}</span>', unsafe_allow_html=True)

    st.markdown("**Шкала уровня стресса**")
    render_scale(result.total, result.scale_pos)
    if result.band == "ultra_high":
        st.warning(
            "Балл вашей собаки превышает максимальное значение, наблюдавшееся в текущей выборке."
        )

    st.markdown("---")
    st.markdown("**Что это значит?**")
    st.markdown(c(BAND_COPY_KEY[result.band]))

    # Health module — readable list + wording based on gh_durations (stored in answers).
    GH_CODE_LABEL = {
        1: "изменения шерсти/кожи",
        2: "потеря веса",
        3: "изменения запаха тела или из пасти",
        4: "желудочно-кишечные признаки",
        5: "изменения, связанные с репродуктивной системой",
        6: "изменения, связанные с репродуктивной системой",
    }
    gh_durations = st.session_state.get("answers", {}).get("gh_durations", {})
    reported: Dict[int, int] = {}
    for k, v in (gh_durations or {}).items():
        try:
            reported[int(k)] = int(v)
        except (ValueError, TypeError):
            pass
    positive = {code: dur for code, dur in reported.items() if dur != -1}

    if positive:
        def _labels_for(codes: List[int]) -> str:
            """Deduplicated label list for a subset of codes."""
            seen: List[str] = []
            for code in sorted(codes):
                lbl = GH_CODE_LABEL.get(code, "")
                if lbl and lbl not in seen:
                    seen.append(lbl)
            return ", ".join(seen)

        # Three duration bands (stored codes): 3 = over a month; 2 = less than a month;
        # 1 = less than a week (code 4 "It varies / Other" is normalized to 1 before save).
        chronic_codes = [c for c, d in positive.items() if d == 3]
        within_month_codes = [c for c, d in positive.items() if d == 2]
        week_or_varies_codes = [c for c, d in positive.items() if d == 1]

        st.markdown("---")
        st.markdown("**Признаки, связанные со здоровьем**")

        st.markdown(
            "Некоторые отмеченные вами признаки здоровья могут быть связаны с хроническим стрессом: "
            "они могут как отражать его, так и усиливать."
        )

        if chronic_codes:
            chronic_list = _labels_for(chronic_codes)
            st.markdown(
                f"**Присутствуют больше месяца:** {chronic_list}. "
                "Эти признаки сохраняются относительно долго и могут быть сильнее связаны с хроническим стрессом. "
                "Если вы еще этого не сделали, может быть важно обратиться к ветеринарному врачу и специалисту по поведению или благополучию собак."
            )

        if within_month_codes:
            month_list = _labels_for(within_month_codes)
            st.markdown(
                f"**Впервые замечены меньше месяца назад:** {month_list}. "
                "Эти признаки могут быть как проявлениями хронического стресса, так и факторами, которые ему способствуют. "
                "Если ветеринарный врач не нашел медицинскую причину, консультация со специалистом по поведению или благополучию собак тоже может быть полезна."
            )

        if week_or_varies_codes:
            week_list = _labels_for(week_or_varies_codes)
            st.markdown(
                f"**Впервые замечены за последнюю неделю или появляются нерегулярно:** {week_list}. "
                "Эти признаки могут быть недавними или непостоянными, но все равно могут иметь значение. "
                "Если они повторяются, сохраняются или становятся заметнее, стоит обратиться за профессиональной консультацией."
            )

    # Render Supabase diagnostics here (stable screen)
    render_supabase_diagnostics()

    st.markdown(
        f'<div class="result-note"><p><em>{c("result_disclaimer", "Этот инструмент предназначен для скрининга и не является клиническим диагнозом.")}</em></p></div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        """
        <div class="result-note">
            <p><em>Dog Stress Level Questionnaire был разработан и валидирован Alice Tananaeva в Human-Animal Interaction Lab, Oregon State University.</em></p>
            <p><strong>Узнать больше или обсудить сотрудничество:</strong><br>
            <a href="https://www.alicetananaeva.com" target="_blank">www.alicetananaeva.com</a><br>
            <a href="https://thehumananimalbond.com/" target="_blank">thehumananimalbond.com</a></p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    col_back, col_next = st.columns([1, 2])
    if col_back.button("<- Назад", key="result_back"):
        choices = st.session_state.get("choices", {})
        if choices.get("share_questionnaire_data") or choices.get("share_demographic_data"):
            go("demographics")
        else:
            go("contact")
    if col_next.button("Продолжить ->", type="primary", key="result_next"):
        go("completion")


def screen_sharing() -> None:
    st.markdown(f"## {c('save_data_title', 'Хотите поделиться данными для исследования?')}")
    st.markdown(
        c(
            "save_data_body",
            "Передача данных необязательна. Вы получите результат независимо от того, решите ли вы чем-то поделиться.",
        )
    )
    st.markdown(
        '<div class="dslq-card">'
        f"<b>{c('consent_optional_title', 'Согласие на использование данных в исследовании')}</b><br><br>"
        + c(
            "consent_optional_body",
            "Вы не обязаны делиться ответами, чтобы получить результат.",
        )
        + "</div>",
        unsafe_allow_html=True,
    )

    with st.form("sharing_form"):
        share_q = st.checkbox(
            c("save_data_dog_checkbox"),
            value=st.session_state["choices"]["share_questionnaire_data"],
        )
        share_d = st.checkbox(
            c("save_data_human_checkbox"),
            value=st.session_state["choices"]["share_demographic_data"],
        )
        col_back, col_cont = st.columns([1, 2])
        back = col_back.form_submit_button("<- Назад")
        cont = col_cont.form_submit_button("Продолжить ->", type="primary")

    if back:
        # Land on the last GH item; if gh_item_index stays >= total, general_health immediately
        # re-routes to sharing and Back appears broken.
        dog_sex_back = st.session_state.get("dog_sex", "")
        total_gh = len(get_gh_options(dog_sex_back))
        st.session_state["gh_item_index"] = max(0, total_gh - 1)
        go("general_health")
    if cont:
        st.session_state["choices"]["share_questionnaire_data"] = share_q
        st.session_state["choices"]["share_demographic_data"] = share_d
        go("contact")


def screen_demographics() -> None:
    choices = st.session_state["choices"]
    share_q = choices["share_questionnaire_data"]
    share_d = choices["share_demographic_data"]
    dog_demo = st.session_state["dog_demo"]
    hum_demo = st.session_state["human_demo"]
    contact = st.session_state["contact"]

    with st.form("demo_form"):
        if share_q:
            st.markdown(f"### {c('dog_demo_title', 'Информация о собаке')}")
            dog_rows = OPTIONAL_DF[
                OPTIONAL_DF["section"] == "dog_demographics_optional"
            ].sort_values("display_order")
            for _, f in dog_rows.iterrows():
                fk = str(f["field_key"])
                qtxt = str(f["question_text"])
                rtype = str(f["response_type"])
                if rtype == "text":
                    dog_demo[fk] = st.text_input(
                        qtxt, value=dog_demo.get(fk, ""), key=f"dd_{fk}"
                    )
                elif rtype == "number":
                    dog_demo[fk] = st.number_input(
                        qtxt,
                        min_value=0,
                        step=1,
                        value=int(dog_demo.get(fk, 0)),
                        key=f"dd_{fk}",
                    )
                elif rtype == "single_select":
                    opts = [o.strip() for o in str(f["options_pipe_delimited"]).split("|")]
                    cur = dog_demo.get(fk, opts[0])
                    dog_demo[fk] = st.selectbox(
                        qtxt,
                        options=opts,
                        index=opts.index(cur) if cur in opts else 0,
                        key=f"dd_{fk}",
                    )
                elif rtype == "single_select_plus_text":
                    opts = [o.strip() for o in str(f["options_pipe_delimited"]).split("|")]
                    cur = dog_demo.get(fk, opts[0])
                    sel = st.selectbox(
                        qtxt,
                        options=opts,
                        index=opts.index(cur) if cur in opts else 0,
                        key=f"dd_{fk}_sel",
                    )
                    extra = st.text_input(
                        "Подробности (если применимо):",
                        value=dog_demo.get(f"{fk}_txt", ""),
                        key=f"dd_{fk}_txt",
                    )
                    dog_demo[fk] = sel
                    dog_demo[f"{fk}_txt"] = extra

        if share_d:
            st.markdown(f"### {c('human_demo_title', 'Информация о человеке')}")
            # future_contact is collected on the contact screen (choices), not in human_demo.
            fut_yes = bool(choices.get("future_contact"))
            act_yes = hum_demo.get("human_dog_activity") in ("Yes", "Да")
            hum_rows = OPTIONAL_DF[
                OPTIONAL_DF["section"] == "human_demographics_optional"
            ].sort_values("display_order")

            for _, f in hum_rows.iterrows():
                fk = str(f["field_key"])
                qtxt = str(f["question_text"])
                rtype = str(f["response_type"])
                show_if = str(f["show_if"]) if pd.notna(f.get("show_if")) else ""

                # Names / contact identity belong only on the contact screen.
                if fk in HUMAN_DEMO_EXCLUDED_FIELD_KEYS:
                    continue

                if "future_contact = Yes" in show_if and not fut_yes:
                    continue
                if "human_dog_activity = Yes" in show_if and not act_yes:
                    continue

                if rtype == "single_select":
                    if fk == "future_contact":
                        continue
                    opts = [o.strip() for o in str(f["options_pipe_delimited"]).split("|")]
                    cur = hum_demo.get(fk, opts[0])
                    val = st.selectbox(
                        qtxt,
                        options=opts,
                        index=opts.index(cur) if cur in opts else 0,
                        key=f"hd_{fk}",
                    )
                    hum_demo[fk] = val
                    if fk == "human_dog_activity":
                        act_yes = val in ("Yes", "Да")
                elif rtype == "multi_select":
                    opts = [o.strip() for o in str(f["options_pipe_delimited"]).split("|")]
                    hum_demo[fk] = st.multiselect(
                        qtxt,
                        options=opts,
                        default=hum_demo.get(fk, []),
                        key=f"hd_{fk}",
                        placeholder="Выберите из списка",
                    )
                elif rtype == "single_select_plus_multiselect":
                    opts = [o.strip() for o in str(f["options_pipe_delimited"]).split("|")]
                    cur = hum_demo.get(fk, opts[0])
                    val = st.selectbox(
                        qtxt,
                        options=opts,
                        index=opts.index(cur) if cur in opts else 0,
                        key=f"hd_{fk}",
                    )
                    hum_demo[fk] = val
                    if fk == "human_dog_activity":
                        act_yes = val in ("Yes", "Да")
                elif rtype in ("text", "email"):
                    hum_demo[fk] = st.text_input(
                        qtxt, value=hum_demo.get(fk, ""), key=f"hd_{fk}"
                    )

        col_back, col_finish = st.columns([1, 2])
        back = col_back.form_submit_button("<- Назад")
        finish = col_finish.form_submit_button("Продолжить ->", type="primary")

    if back:
        go("contact")
    if finish:
        st.session_state["dog_demo"] = dog_demo
        st.session_state["human_demo"] = hum_demo
        st.session_state["contact"] = contact
        st.session_state["choices"] = choices
        _wrap_up()


def _wrap_up() -> None:
    """Build export, save if consented, then show result."""
    result = st.session_state["score_result"]
    choices = st.session_state["choices"]
    blob = build_export(
        result,
        st.session_state["answers"],
        st.session_state["dog_demo"],
        st.session_state["human_demo"],
        st.session_state["contact"],
        choices,
    )
    st.session_state["export_blob"] = blob
    if choices["share_questionnaire_data"] or choices["share_demographic_data"]:
        saved = persist_session(blob)
        st.session_state["saved_path"] = str(saved) if saved else None

    # Contact saving must be independent from research consent.
    persist_contact(blob)
    go("result")


def screen_contact() -> None:
    contact = st.session_state.get("contact", {})
    choices = st.session_state["choices"]

    st.markdown(f"## {c('future_contact_title', 'Хотите узнавать о будущих исследованиях?')}")
    st.markdown(
        c(
            "future_contact_body",
            "Если вы выберете «да», мы попросим ваши контактные данные и будем использовать их только для сообщений о будущих исследованиях.",
        )
    )

    contact_options = ["Нет", "Да"]
    current_contact = contact.get("future_contact", "Нет")
    if current_contact == "No":
        current_contact = "Нет"
    elif current_contact == "Yes":
        current_contact = "Да"
    wants_contact = st.radio(
        "Выберите один вариант:",
        options=contact_options,
        index=contact_options.index(current_contact),
        horizontal=True,
        key="contact_radio",
    )

    name_val = contact.get("contact_name", "")
    email_val = contact.get("contact_email", "")
    if wants_contact == "Да":
        st.markdown("---")
        name_val = st.text_input(
            c("future_contact_name_label", "Ваше имя"),
            value=contact.get("contact_name", ""),
            key="contact_name_inp",
        )
        email_val = st.text_input(
            c("future_contact_email_label", "Ваш адрес электронной почты"),
            value=contact.get("contact_email", ""),
            key="contact_email_inp",
        )

    st.markdown("")
    col_back, col_next = st.columns([1, 2])
    back = col_back.button("<- Назад", key="contact_back")
    nxt = col_next.button("Продолжить ->", type="primary", key="contact_next")

    if back:
        go("sharing")
    if nxt:
        if wants_contact == "Да":
            if not str(email_val or "").strip():
                st.error("Пожалуйста, укажите адрес электронной почты для будущей связи.")
                st.stop()
            if not _is_valid_email_simple(email_val):
                st.error(
                    "Пожалуйста, укажите корректный email-адрес (например, test@example.com). "
                    "Пробелы не допускаются."
                )
                st.stop()
        choices["future_contact"] = wants_contact == "Да"
        contact["future_contact"] = wants_contact
        contact["contact_name"] = name_val
        contact["contact_email"] = email_val
        st.session_state["contact"] = contact
        st.session_state["choices"] = choices
        share_q = choices.get("share_questionnaire_data", False)
        share_d = choices.get("share_demographic_data", False)
        if share_q or share_d:
            go("demographics")
        else:
            _wrap_up()


def screen_completion() -> None:
    choices = st.session_state["choices"]
    saved_path = st.session_state.get("saved_path")
    export_blob = st.session_state.get("export_blob")
    saved_data = choices.get("share_questionnaire_data") or choices.get("share_demographic_data")
    wants_contact = bool(choices.get("future_contact") and st.session_state["contact"].get("contact_email"))
    contact_saved = st.session_state.get("supabase_contact_insert_ok") is True

    st.markdown("## 🐾 Спасибо!")

    if saved_data and contact_saved:
        st.success(
            "Спасибо за заполнение опросника. Анкетные и демографические данные, "
            "которыми вы согласились поделиться, были сохранены для исследования."
        )
        st.success(
            "Ваши контактные данные были сохранены отдельно для сообщений о будущих исследованиях."
        )
    elif contact_saved and not saved_data:
        st.success(
            "Спасибо за заполнение опросника. Ваши контактные данные были сохранены "
            "отдельно для сообщений о будущих исследованиях. Анкетные или демографические "
            "данные для исследования не сохранялись."
        )
    elif saved_data:
        st.success(
            c("completion_research_saved")
        )
    else:
        st.info(
            c("completion_nothing_saved")
        )

    # Also render Supabase diagnostics here (another stable screen)
    render_supabase_diagnostics()

    st.markdown("---")
    if st.button("Начать заново", use_container_width=True):
        for k in list(st.session_state.keys()):
            del st.session_state[k]
        st.rerun()


PAGES = {
    "intro": screen_intro,
    "sex_select": screen_sex_select,
    "questionnaire": screen_questionnaire,
    "general_health": screen_general_health,
    "gh_duration": screen_gh_duration,
    "sharing": screen_sharing,
    "demographics": screen_demographics,
    "result": screen_result,
    "contact": screen_contact,
    "completion": screen_completion,
}

page = st.session_state.get("page", "intro")
PAGES.get(page, screen_intro)()
