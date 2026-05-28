# Mutual Intent And Proxy Intro Flow

## 1. Goal

Build a complete "愿意认识" flow with one hard rule:

1. Candidate detail is only for expressing intent.
2. Ongoing progress lives in records / relationships.
3. Chat opens only after bilateral willingness is confirmed.
4. The receiving side sees a matchmaker recommendation, not "someone proactively clicked you".

This document defines the full landing plan, not just the first clickable button.

## 2. Plain-Language Product Summary

The product should behave like this:

1. A user sees a candidate and clicks `愿意认识`.
2. The system records "A is willing to know B".
3. B later receives a matchmaker recommendation for A, without seeing whether A initiated first.
4. B can choose `愿意认识` or `暂不考虑`.
5. Only when both sides are willing does the system unlock chat.
6. Users check status in `关系页`, not on the candidate detail button.

## 3. Current Status

### 3.1 Already Landed

1. Candidate detail no longer uses `开始聊天`; primary action is `愿意认识`.
2. Candidate detail success feedback points users to `关系页`.
3. Relationships page already has a `牵线中` section.
4. Recommendation inbox -> candidate detail -> `愿意认识` is supported.
5. Discovery / matchmaker-chat recommendation -> candidate detail -> `愿意认识` is also supported.
6. The discovery path now creates formal recommendation context before recording the interest action.

### 3.2 Not Fully Landed Yet

1. The receiving side's full accept / decline product flow is not complete.
2. Bilateral acceptance -> chat unlock is not fully closed as a single product flow.
3. Relationships page is not yet the final single source of truth for all intro records.
4. User-facing stage copy is not fully normalized.
5. Edge cases such as withdraw, timeout, duplicate requests, and closure are not fully productized.

## 4. Scope Boundaries

### 4.1 Candidate Detail Page

Allowed:

1. Show profile.
2. Show why this person is recommended.
3. Submit `愿意认识`.
4. Show one-time submission confirmation.

Not allowed:

1. Direct chat entry.
2. Long-running status management.
3. Multi-step process controls.

### 4.2 Relationships Page

Must become the process center for:

1. `牵线中`
2. `等待对方回应`
3. `双方已愿意`
4. `已开聊`
5. `未达成 / 已结束`

### 4.3 Recommendation Inbox

Must become the receiving side's intake surface for:

1. New matchmaker recommendations.
2. Accept / decline decisions.
3. Recommendation-origin-neutral presentation.

## 5. Canonical User Flow

### 5.1 Requester Side

1. A opens candidate detail.
2. A clicks `愿意认识`.
3. System creates or reuses a formal intro record.
4. System records A's willingness.
5. Detail page shows lightweight confirmation only.
6. A later checks `关系页` for progress.

### 5.2 Receiver Side

1. B receives a matchmaker recommendation card.
2. B opens the candidate detail or recommendation entry.
3. B chooses `愿意认识` or `暂不考虑`.
4. B never sees "A clicked you first".

### 5.3 Bilateral Match

1. If A is willing and B is willing, the pair becomes chat-eligible.
2. System creates the relation / chat handoff.
3. Chat entry appears from `关系页`, not from candidate detail.

### 5.4 Negative Outcomes

1. If B declines, A sees a closed / not matched outcome.
2. If B does not reply in time, A sees timeout.
3. If the candidate becomes unavailable, the intro record closes cleanly.

## 6. State Machine

### 6.1 Internal Conceptual States

Use these as the product-level state model:

1. `intent_submitted`
2. `pending_delivery`
3. `awaiting_reply`
4. `bilateral_accept_ready`
5. `chat_opened`
6. `declined`
7. `timed_out`
8. `closed`

### 6.2 User-Facing Stage Labels

Do not expose raw backend names directly. Normalize to:

1. `已提交`
2. `等待对方看到`
3. `等待对方决定`
4. `双方都有意愿`
5. `可以聊天了`
6. `对方暂不考虑`
7. `已超时`
8. `已结束`

### 6.3 CTA Rules

Candidate detail:

1. `idle` -> `愿意认识`
2. `submitting` -> `发送中`
3. `success` -> `已提交，可在关系里查看进度`

Relationships page:

1. Pending intro records show stage and next step.
2. Chat button appears only after bilateral acceptance and handoff completion.

Recommendation inbox:

1. Receiver can choose `愿意认识`
2. Receiver can choose `暂不考虑`

## 7. UX Rules

### 7.1 Detail Page

1. Keep the button simple.
2. Do not pin long-lived state on this button.
3. Do not switch the button into a process dashboard.

### 7.2 Relationships Page

1. Be the primary place to track intro progress.
2. Group active chat separately from intro-in-progress.
3. Show human-readable stage, not implementation jargon.

### 7.3 Receiver Presentation

1. Receiver sees "红娘推荐了这位".
2. Receiver does not see "someone proactively clicked you".
3. Product copy should preserve dignity and avoid exposing initiation asymmetry.

## 8. Backend Flow Design

### 8.1 Standard Recommendation Path

When detail opens from recommendation inbox:

1. Frontend already has `subscriptionId`.
2. Clicking `愿意认识` records recommendation action directly.
3. Status moves into intro-in-progress states.

### 8.2 Discovery / Matchmaker-Chat Path

When detail opens from discovery chat:

1. Frontend has `sessionId` and `candidateId`.
2. Backend loads the latest search run from the discovery session.
3. Backend validates the candidate is from that search run.
4. Backend creates a formal recommendation subscription if needed.
5. Backend directly upserts the selected candidate as a formal recommendation row.
6. Backend records the `direct_greet` / intent action.
7. The pair now enters the same downstream recommendation / relationship pipeline as standard recommendation flows.

### 8.3 Bilateral Acceptance Path

Needed final behavior:

1. A willing alone is not enough for chat.
2. B's accept action must be stored against the same pair / relation.
3. Once both sides are willing, system creates relation / chat handoff.
4. Only then does chat become visible.

## 9. Required System Responsibilities

### 9.1 Frontend

Candidate detail:

1. Submit willingness.
2. Never open chat directly.

Relationships page:

1. Show intro progress.
2. Show chat only when eligible.

Recommendation inbox:

1. Show inbound recommendations.
2. Support receiver-side accept / decline.

### 9.2 Gateway / API

Need stable API surfaces for:

1. `POST /v1/recommendation/actions`
2. `POST /v1/discovery/sessions/{session_id}/candidates/{candidate_id}/express-interest`
3. Receiver-side accept / decline API
4. Relationship / intro status read API
5. Chat eligibility read API

### 9.3 Recommendation / Matchmaking Domain

Need to guarantee:

1. Formal intro record exists for every submitted intent.
2. Source-neutral receiver presentation.
3. Bilateral state can be computed consistently.
4. Handoff to relation/chat is idempotent.

## 10. Remaining Tasks

### 10.1 Product Tasks

1. Finalize user-facing stage labels.
2. Finalize receiver-side copy.
3. Finalize timeout / decline / closure copy.

### 10.2 Frontend Tasks

1. Make `关系页` the single intro-progress center.
2. Add receiver-side accept / decline UI in recommendation inbox.
3. Add "双方都有意愿" and "可以聊天了" states.
4. Remove any remaining direct-chat shortcuts from non-relationship surfaces.

### 10.3 Backend Tasks

1. Unify requester-side and receiver-side willingness into one bilateral state model.
2. Add receiver-side accept / decline write path if missing.
3. Add final chat handoff trigger after bilateral acceptance.
4. Ensure relation / chat creation is idempotent.
5. Expose normalized status reads for frontend.

### 10.4 Data / State Tasks

1. Normalize recommendation state -> relationship intro state mapping.
2. Track bilateral willingness explicitly or deterministically derive it.
3. Add timeout handling.
4. Add closure reasons.

### 10.5 Edge-Case Tasks

1. Duplicate click on `愿意认识`
2. Candidate no longer available
3. Re-open after previous decline
4. Timeout after no reply
5. Manual close by ops / matchmaker
6. Relation exists but chat handoff failed

## 11. Recommended Delivery Order

### Phase A: Lock The Rules

1. Freeze canonical state machine.
2. Freeze user-facing stage labels.
3. Freeze chat eligibility rule.

### Phase B: Complete Receiver Flow

1. Add receiver-side accept / decline UI.
2. Store receiver decision.
3. Keep presentation source-neutral.

### Phase C: Complete Bilateral Handoff

1. Detect bilateral willingness.
2. Create relation / chat handoff.
3. Expose chat only after handoff success.

### Phase D: Complete Relationship Center

1. Move all intro progress into `关系页`.
2. Show pending, accepted, closed, timeout, and chat-ready records clearly.

### Phase E: Close Edge Cases

1. Timeout
2. Decline
3. Candidate unavailable
4. Duplicate submit
5. Manual closure

## 12. Acceptance Criteria

This initiative is only considered complete when all of the following are true:

1. Candidate detail never opens chat directly.
2. Clicking `愿意认识` always creates or reuses a formal intro record.
3. Discovery and recommendation entry paths behave consistently after submission.
4. Receiver can accept or decline without seeing who initiated first.
5. Chat is unavailable until bilateral willingness is achieved.
6. Relationships page is the primary place to view intro progress.
7. Timeout / decline / closure states are visible and understandable.
8. Duplicate actions are safe and idempotent.

## 13. Current Implementation Notes

As of now, the system has completed the first milestone:

1. Submit willingness from candidate detail.
2. Support both recommendation-entry and discovery-entry initiation.
3. Move users toward `关系页` instead of direct chat.

The next real milestone is:

1. Finish the receiver-side decision flow.
2. Finish bilateral acceptance -> chat handoff.
3. Finish relationships page as the single process center.
