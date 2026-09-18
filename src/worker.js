import { APP_VERSION, calculateDslq, validateDslq } from "../public/scoring.js";

const JSON_HEADERS = {
  "content-type": "application/json; charset=utf-8",
  "cache-control": "no-store",
  "x-content-type-options": "nosniff",
};

function json(data, status = 200) {
  return new Response(JSON.stringify(data), { status, headers: JSON_HEADERS });
}

function isUuid(value) {
  return typeof value === "string"
    && /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(value);
}

function safeDemographics(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) return {};
  const allowed = ["dog_name", "dog_age_years", "dog_age_months", "dog_lives_with_you", "dog_sex", "dog_neuter_status", "dog_breed", "dog_weight", "dogs_in_household", "other_animals", "other_animals_text"];
  return Object.fromEntries(allowed.filter((key) => value[key] !== undefined).map((key) => [key, typeof value[key] === "string" ? value[key].slice(0, 250) : value[key]]));
}

async function saveSession(request, env) {
  const contentLength = Number(request.headers.get("content-length") || 0);
  if (contentLength > 128_000) return json({ error: "Слишком большой запрос." }, 413);
  let payload;
  try {
    payload = await request.json();
  } catch {
    return json({ error: "Некорректный JSON." }, 400);
  }
  if (payload?.consent !== true) return json({ error: "Для сохранения требуется согласие." }, 400);
  if (!isUuid(payload.sessionId)) return json({ error: "Некорректный идентификатор сессии." }, 400);
  if (!validateDslq(payload.dogSex, payload.behaviorAnswers, payload.healthDurations)) return json({ error: "Ответы неполные или некорректные." }, 400);

  const demographics = safeDemographics(payload.dogDemographics);
  const result = calculateDslq(payload.dogSex, payload.behaviorAnswers, payload.healthDurations);
  const selectedHealthCodes = Object.entries(payload.healthDurations).filter(([, value]) => value !== -1).map(([code]) => Number(code));
  const generalHealth = { Dog_Symptoms: selectedHealthCodes, gh_durations: payload.healthDurations };
  const query = env.DB.prepare(`
    INSERT OR IGNORE INTO dslq_sessions (
      session_id, app_version, consented_dog, dog_sex,
      dslq_chronic_score, interpretation_band, health_flag, visual_scale_pos,
      item_scores_json, behavior_answers_json, general_health_answers_json,
      research_choices_json, dog_demographics_json
    ) VALUES (?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
  `).bind(
    payload.sessionId,
    APP_VERSION,
    payload.dogSex,
    result.total,
    result.band,
    result.health,
    result.scalePos,
    JSON.stringify(result.itemScores),
    JSON.stringify(payload.behaviorAnswers),
    JSON.stringify(generalHealth),
    JSON.stringify({ share_questionnaire_data: true, language: "ru" }),
    JSON.stringify(demographics),
  );

  try {
    const saved = await query.run();
    return json({ saved: true, duplicate: saved.meta?.changes === 0, result });
  } catch {
    return json({ error: "Не удалось сохранить исследовательскую копию. Результат остаётся доступен." }, 503);
  }
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname === "/api/health" && request.method === "GET") {
      try {
        await env.DB.prepare("SELECT 1").first();
        return json({ ok: true, database: true, version: APP_VERSION });
      } catch {
        return json({ ok: false, database: false, version: APP_VERSION }, 503);
      }
    }
    if (url.pathname === "/api/sessions" && request.method === "POST") return saveSession(request, env);
    if (url.pathname.startsWith("/api/")) return json({ error: "Не найдено." }, 404);
    return env.ASSETS.fetch(request);
  },
};
