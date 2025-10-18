#!/usr/bin/env bash
# Simple end-to-end smoke test against a running server:
# - parse a PDF (optional)
# - start a session
# - enable LLM
# - fetch next question
# - answer with patches (ownership/collaboration/period/team/tech)
# - fetch a profile snapshot

set -euo pipefail

API="${API:-http://127.0.0.1:8000}"
PDF="${1:-sample/sample_resume.pdf}"
INTRO="${2:-Targeting Data Analyst roles}"

need() { command -v "$1" >/dev/null 2>&1 || { echo "Missing '$1'"; exit 1; }; }
need jq
need pdftotext
need curl

echo "[test] API=$API"
echo "[test] PDF=$PDF"
echo "[test] INTRO='$INTRO'"

# 1) Optionally parse the resume (useful to verify parsers run)
echo "[1] parse_resume_file (optional)"
curl -s -F "file=@${PDF}" -F "target_intro=${INTRO}" "$API/parse_resume_file" \
| jq '.notes // empty'

# 2) Start a new session using the PDF text
echo "[2] session/start"
TXT=$(pdftotext -layout "$PDF" - | tr -d '\f')
SID=$(jq -nr --arg rt "$TXT" --arg ti "$INTRO" \
  '{resume_text:$rt, target_intro:$ti}' \
  | curl -s -X POST "$API/session/start" -H "Content-Type: application/json" -d @- \
  | jq -r '.session_id')
echo "[info] SID=$SID"

# 3) Enable LLM for this session
echo "[3] use_llm=true"
curl -s -X POST "$API/session/$SID/config?use_llm=true" | jq .

# 4) Show current gap count
echo "[4] gaps count"
curl -s "$API/session/$SID/gaps" | jq '.count'

# 5) Fetch the next question (and extract QID/TARGET)
echo "[5] next_question"
QJSON="$(curl -s "$API/session/$SID/next_question")"
echo "$QJSON" | jq .
QID="$(echo "$QJSON" | jq -r '.question.id')"
TARGET="$(echo "$QJSON" | jq -r '.question.target')"
echo "[info] QID=$QID"
echo "[info] TARGET=$TARGET"

# 6) Answer with a patch list (adjust values if needed)
echo "[6] answer (patches)"
PATCHES="$(jq -n --arg tgt "$TARGET" '[
  {"path":("projects["+$tgt+"].ownership"), "value":"Owned MS SQL ingestion, PySpark pipelines, regression model, and Power BI modeling"},
  {"path":("projects["+$tgt+"].collaboration"), "value":"Partnered with retail ops & IT/BI on metrics and rollout"},
  {"path":("projects["+$tgt+"].period"), "value":"2025-06..2025-09"},
  {"path":("projects["+$tgt+"].team_size"), "value":4},
  {"path":("projects["+$tgt+"].tech"), "value":["MS SQL Server","PySpark","Power BI"]}
]')"

curl -s -X POST "$API/session/$SID/answer" \
  -H "Content-Type: application/json" \
  -d "$(jq -n --arg q "$QID" --arg a "$PATCHES" '{question_id:$q, answer_text:$a}')" \
| jq '{checked, applied_updates, remaining_gaps, notes}'

# 7) Show a targeted project snapshot to verify fields applied
echo "[7] profile snapshot"
curl -s "$API/session/$SID/profile" \
| jq --arg t "$TARGET" '
  first(.profile.projects[] | select(.title==$t))
  | {title, ownership, team_size, stack, period, impact, attributes}
'

echo "[done] ✅"
