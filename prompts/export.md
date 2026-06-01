EXPORT PATCH RULES

You are modifying an existing grouped export system.

Goals:
- preserve existing export behavior
- preserve grouped export structure
- preserve folder naming
- preserve script.txt format

Allowed:
- small export logic additions
- logging additions
- path handling
- metadata improvements

Do NOT:
- rewrite export architecture
- rewrite semantic matching
- modify UI layout
- add new abstractions
- refactor unrelated functions

Patch workflow:
1. identify affected export function
2. explain minimal change
3. return raw code only

Export structure:

script_001/
  script.txt
  scene_014.mp4
  scene_015.mp4

script.txt format:

Line 1:
<narration text>

Matched scenes:
14
15
16

Logging rules:
- exporting script_001
- adding scene_014.mp4
- completed script_001 export

Token rules:
- avoid full-file rewrites
- avoid long explanations
- prefer additive edits