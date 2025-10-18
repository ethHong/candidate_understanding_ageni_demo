#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

# --- env load (local first) ---
if [[ -f ".env.local" ]]; then set -a; source .env.local; set +a; fi
if [[ -f ".env" ]]; then set -a; source .env; set +a; fi

PORT="${PORT:-8000}"
API="${API:-http://127.0.0.1:${PORT}}"
PDF="${1:-sample/sample_resume.pdf}"
INTRO="${2:-Targeting Data Analyst roles}"

need() { command -v "$1" >/dev/null 2>&1 || { echo "Missing $1. Try: brew install $1"; exit 1; }; }
need jq
need pdftotext

echo "API=$API"
echo "PDF=$PDF"
echo "INTRO='$INTRO'"

echo "1) Parse PDF with LLM parser (if enabled)..."
curl -s -F "file=@${PDF}" -F "target_intro=${INTRO}" "$API/parse_resume_file" \
| jq '.notes,
     {projects: (.profile_draft.projects[:6] | map({title,company,role,period}))},
     {skills: (.profile_draft.skills[:10] | map({name,depth,last_used,frequency}))}'

echo "2) Start a session from the same PDF text..."
TXT=$(pdftotext -layout "$PDF" - | tr -d '\f')

SID=$(jq -nr --arg rt "$TXT" --arg ti "$INTRO" \
  '{resume_text:$rt, target_intro:$ti}' \
  | curl -s -X POST "$API/session/start" -H "Content-Type: application/json" -d @- \
  | jq -r '.session_id // empty')

if [[ -z "${SID}" ]]; then
  echo "Failed to acquire session_id from /session/start"; exit 1
fi
echo "SID=$SID"

echo "3) Enable LLM for Q&A on this session..."
curl -s -X POST "$API/session/$SID/config?use_llm=true" | jq

echo "4) Show current gaps count..."
curl -s "$API/session/$SID/gaps" | jq '.count'

echo "5) Get next question..."
Q=$(curl -s "$API/session/$SID/next_question")
echo "$Q" | jq
QID=$(echo "$Q" | jq -r '.question.id // .id // empty')
if [[ -z "${QID}" ]]; then
  echo "No questions to ask."
  exit 0
fi

echo
read -r -p "6) Your answer (single line; press Enter to submit): " ANS
[ -z "${ANS:-}" ] && ANS="At LA Clippers (Jun–Sep 2025) I used MS SQL Server daily to analyze ~40M events, built CTE pipelines & Power BI views, impact: +6.8% attach rate, +12% MoM revenue; hands-on 3x/week; last used 2025-09."

echo "Submitting answer..."
curl -s -X POST "$API/session/$SID/answer" -H "Content-Type: application/json" \
  -d "$(jq -n --arg q "$QID" --arg a "$ANS" '{question_id:$q, answer_text:$a}')" \
| jq '{checked, applied_updates, remaining_gaps, notes}'

echo "7) Gaps after answer:"
curl -s "$API/session/$SID/gaps" | jq '.count'

echo "8) Current profile snapshot:"
curl -s "$API/session/$SID/profile" \
| jq '{core: .profile.core,
       skills: (.profile.skills | map({name,mode,last_used,frequency,confidence})),
       projects: (.profile.projects | map({title,company,role,period,impact,actions: ( .actions[:2] )})) }'
