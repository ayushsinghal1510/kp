# posta

Post-session hook for Voxio. Two routes :

| Route | Purpose |
| --- | --- |
| `POST /session` | Decrypts a JWE header token , pulls the session from `chat.voxio.in` , writes a session doc and back-links it onto the student and scenario docs |
| `POST /get-results` | Scores a consultation transcript against its scenario with Gemini and returns `score` + `overall_feedback` |

## Running

```bash
cd vps/posta && uv run posta        # * must be run from this directory , config.yml is read by relative path
```

Requires a `.env` in this directory with `MONGO_URL` , `JWE_SECRET` and `GEMINI_API_KEY`.

## `POST /get-results`

Request :

```json
{
  "scenario_id": "68f3c1e9b4a2d5e7f8a91b2c",
  "transcription": "...",
  "session_id": "sess-abc-123",
  "user_id": "68f3c1e9b4a2d5e7f8a91b30"
}
```

Response :

```json
{
  "score": 74,
  "overall_feedback": "You opened well by establishing the duration ..."
}
```

`scenario_id` accepts **either** the Mongo `ObjectId` of a scenario doc **or** a short scenario code
such as `9C2F7X` — the frontend sends the latter. `_id` is tried first , then the code fields
`scenarioCode` / `ScenarioId` / `scenarioId` / `scenario_code`.

The scenario's prompt , movements , difficulty and feedback questions form the marking rubric. Both
schemas present in the collection are read , camelCase first :

| Rubric | Live (Node app) | `vps/server` |
| --- | --- | --- |
| prompt | `scenarioPrompt` | `scenario_prompt` |
| questions | `aiQuestions` (newline-separated string) | `questions_for_feedback` (list) |
| difficulty | `difficulty` | `difficulty_status` |
| movements | `animationTriggers` | `movements` |

`transcription` accepts **either** a plain string **or** a conversation-history list of
`{'role' , 'content'}` objects — the shape `chat.voxio.in` returns in
`diagnosis_conversation_history`.

When `get-results.persist-to-session` is true in `config.yml` , the score and feedback are also
written onto the session doc matching `session_id`.

### Status codes

| Code | Meaning |
| --- | --- |
| `200` | Assessed. A `score` of `0` with an explanatory message means no consultation was recorded |
| `400` | A required field is missing from the body |
| `404` | No scenario matched that `scenario_id` , by either `_id` or scenario code |
| `422` | The scenario exists but has no prompt to assess against |

### curl — conversation-history transcript

```bash
curl -s -X POST http://localhost:8000/get-results \
  -H 'Content-Type: application/json' \
  -d '{
    "scenario_id": "000000000000000000000abc",
    "session_id": "sess-abc-123",
    "user_id": "student-42",
    "transcription": [
      {"role": "user", "content": "Good morning Mr Sharma, what brings you in today?"},
      {"role": "assistant", "content": "My right shoulder has been aching for about three months."},
      {"role": "user", "content": "Did it start after any injury or fall?"},
      {"role": "assistant", "content": "No, no injury, it just crept up on me."},
      {"role": "user", "content": "Anything that makes it worse? How are you sleeping?"},
      {"role": "assistant", "content": "Reaching overhead to write on the board. It wakes me if I lie on that side."},
      {"role": "user", "content": "Can you lift your arm out to the side for me?"},
      {"role": "assistant", "content": "It hurts partway up, then eases near the top."},
      {"role": "user", "content": "That painful arc with your night pain points to a rotator cuff impingement rather than a frozen shoulder. Physiotherapy should settle it and you can keep teaching."},
      {"role": "assistant", "content": "That is a relief, thank you doctor."}
    ]
  }' | python -m json.tool
```

### curl — plain string transcript

```bash
curl -s -X POST http://localhost:8000/get-results \
  -H 'Content-Type: application/json' \
  -d '{
    "scenario_id": "000000000000000000000abc",
    "session_id": "sess-abc-124",
    "user_id": "student-42",
    "transcription": "Doctor: how long has it hurt? Patient: three months, no injury. Doctor: any night pain? Patient: yes it wakes me. Doctor: lift your arm sideways. Patient: hurts partway up. Doctor: rotator cuff impingement, physio will help."
  }' | python -m json.tool
```

### curl — from a file

Keeps long transcripts out of your shell history , and avoids quoting problems :

```bash
curl -s -X POST http://localhost:8000/get-results \
  -H 'Content-Type: application/json' \
  -d @payload.json | python -m json.tool
```

### curl — error cases

```bash
# * 400 — missing required fields
curl -i -s -X POST http://localhost:8000/get-results \
  -H 'Content-Type: application/json' \
  -d '{"scenario_id" : "000000000000000000000abc"}'

# * 400 — scenario_id is not an ObjectId
curl -i -s -X POST http://localhost:8000/get-results \
  -H 'Content-Type: application/json' \
  -d '{"scenario_id":"not-an-oid","session_id":"s","user_id":"u","transcription":"x"}'

# * 404 — no such scenario
curl -i -s -X POST http://localhost:8000/get-results \
  -H 'Content-Type: application/json' \
  -d '{"scenario_id":"0000000000000000deadbeef","session_id":"s","user_id":"u","transcription":"x"}'
```

### Deployed host

Swap the host for the deployed instance , keeping the path the same :

```bash
curl -s -X POST http://34.226.139.184:7860/get-results \
  -H 'Content-Type: application/json' \
  -d @payload.json | python -m json.tool
```

# ! `uvicorn` binds port 8000 in `main()` , so if that host serves posta on 7860 the mapping is done
# ! outside the app (reverse proxy or container port publish) — check before assuming the port.

## `POST /session`

Takes the JWE in a `token` header , not a body :

```bash
curl -s -X POST http://localhost:8000/session \
  -H 'token: <jwe-token>'
```
