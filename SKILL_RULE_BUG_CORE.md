## RULE 0 — TOOL LOCK FIRST

Before any audit or implementation:

LOCK tools first.

Default state:

FORBIDDEN

search
grep
regex

pattern search
symbol search

find symbol
find references

go to definition
go to references

code index lookup
symbol index lookup

reference lookup

workspace index query

class lookup
function lookup
method lookup

import lookup

identifier lookup

cross reference

dependency lookup

semantic search

callback hunting

signal hunting

runtime hunting

repository exploration

workspace exploration

folder exploration

directory exploration

auto locate

auto discovery

ANY TOOL THAT LOCATES CODE BY NAME

ANY TOOL THAT USES SYMBOL INDEX

ANY TOOL THAT USES REFERENCE INDEX



## RULE 1 — FLOW FIRST

Không sửa code trước khi biết:

Feature
↓
Flow
↓
State
↓
Runtime
↓
Save
↓
UI

Nếu chưa vẽ được Flow:

STOP.

---

## RULE 2 — ONE AUTHORITY

Một nhiệm vụ chỉ có một chủ sở hữu.

Ví dụ:

Prompt Build
→ Compiler

Button State
→ Control Authority

Save Analysis
→ Save Layer

Không duplicate.

---

## RULE 3 — RUNTIME IS TRUTH

Report có thể sai.

Audit có thể sai.

AI có thể sai.

Runtime là sự thật duy nhất.

Runtime FAIL

>

Report PASS

---

## RULE 4 — DISABLE BEFORE DELETE

Không xóa trực tiếp.

Build New
↓
Test New
↓
Audit New
↓
Disable Old
↓
Runtime Validation
↓
Delete Old
↓
Residue Audit

---

## RULE 5 — FEATURE MODULE

Mỗi feature phải độc lập.

Feature
├─ UI
├─ State
├─ Runtime
├─ Flow
└─ Manifest

Không trộn nhiều feature trong cùng block.

---

## RULE 6 — FLOW MAP REQUIRED

Mỗi feature phải có:

feature_flow.md

Ví dụ:

Button
↓
Runtime
↓
Worker
↓
Save
↓
State
↓
UI

---

## RULE 7 — MANIFEST REQUIRED

Mỗi feature phải có:

manifest.md

Khai báo:

Entry Point

Dependencies

Owned State

Owned UI

Owned Runtime

---

## RULE 8 — STATE IS SOURCE OF TRUTH

UI không giữ dữ liệu.

Runtime không giữ dữ liệu.

State mới là nguồn dữ liệu.

---

## RULE 9 — BUILD BEFORE DELETE

Build New
↓
Test New
↓
Audit New
↓
Delete Old

Không làm ngược.

---

## RULE 10 — TEST FLOW, NOT METHOD

Không test:

Method tồn tại

Phải test:

Button
↓
Runtime
↓
Save
↓
State
↓
UI

---

## RULE 11 - FIX BEFORE REFACTOR

Không refactor kiến trúc khi feature chính chưa hoạt động.

Fix runtime trước.
Refactor sau.

---

## RULE 12 — CALLBACK CHAIN COMPLETE
Mọi queue phải audit đủ:
Start → Worker → Finish → Advance → Next
Không build queue nếu chưa có đủ callback.

---

## RULE 13 — AI SCOPE LIMIT

AI chỉ làm 1 nhiệm vụ / 1 layer mỗi lần.

Rule xác định scope.
↓
AI thực thi.
↓
Rule validate kết quả.

Không giao toàn bộ bài toán cho AI.

---

## RULE 14 — BUILD THE CORE FIRST

Mọi feature phải xây theo thứ tự:

Core Runtime
↓
Runtime Validation
↓
Queue / Callback
↓
State
↓
UI
↓
Progress
↓
Status
↓
Refactor

---

## RULE 17 — REPORT LOCATION

Audit reports:

logs/reports/

Runtime logs:

logs/runtime/

Temporary step reports:

FORBIDDEN

Only one final report per phase.

---

## RULE 18 — Feature Contract

Mỗi feature lớn phải có:

FEATURE_CONTRACT.md

AI không được dựa vào trí nhớ chat.

AI không được dựa vào report phase trước.

Contract là nguồn sự thật duy nhất của feature.

---

## RULE 19 — LOG BEFORE CODE

Nếu runtime log đã chứng minh được flow:

Ưu tiên đọc log trước.

Xác định ownership từ log.

Chỉ đọc block code liên quan sau khi đã biết bug nằm ở đâu.

Không search toàn project trước.

Không audit toàn project trước.

---

# FAILURE PATTERNS

F001 — UI State Drift

UI state ≠ Runtime state

---

F002 — Hidden Dependency

Xóa A làm B chết.

---

F003 — Duplicate Authority

Một việc có nhiều chủ.

---

F004 — Single File Monster

File quá lớn.

Audit khó.

Xóa khó.

---

F005 — Ghost Component

UI còn.

Runtime mất.

Hoặc ngược lại.

---

F006 — Queue Callback Break

Scene 1 chạy.

Scene 2 không chạy.

Flow bị đứt.

---

F007 — Restore Drift

Restore xong.

Mọi report cũ mất hiệu lực.

---

F008 — Report Reality Mismatch

Report PASS.

Runtime FAIL.

Tin Runtime.

---

F009 — Fake Completion

Code tồn tại.

Feature chưa chạy.

---

F010 — AI Can Do All Illusion

Đừng giao toàn bộ bài toán cho AI.

Rule
↓
AI
↓
Rule

---

# APP STRUCTURE

app/

features/
├─ feature_a/
│ ├─ ui.py
│ ├─ state.py
│ ├─ runtime.py
│ ├─ manifest.md
│ └─ flow.md
│
├─ feature_b/
│ ├─ ui.py
│ ├─ state.py
│ ├─ runtime.py
│ ├─ manifest.md
│ └─ flow.md

core/
├─ compiler/
├─ save/
├─ state/
└─ runtime/

docs/
├─ RULE_APP_BUILD.md
├─ SKILL_APP_EVOLUTION_CORE.md
└─ flows/

# GOLDEN QUESTION

Đừng hỏi:

"Code đúng chưa?"

Hãy hỏi:

"Flow này chạy từ đầu đến cuối như thế nào?"
