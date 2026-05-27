# Mutual Intent And Proxy Intro Flow

## Goal

Turn candidate detail into a one-time "express interest" action, then move all ongoing progress into a unified relationships record list. Chat opens only after both sides agree.

## Product Rules

1. Candidate detail only triggers intent.
2. Candidate detail never opens chat directly.
3. Relationship progress lives in a unified list, not on the candidate CTA.
4. The receiving side sees a matchmaker recommendation, not "someone proactively clicked you".
5. Chat is available only after bilateral acceptance.

## User Flow

### Requester side

1. User opens a candidate detail page.
2. User clicks `愿意认识`.
3. System records a proxy-intro request.
4. Page confirms submission with lightweight feedback and directs the user to the relationships page for progress.
5. Further updates are read from the relationships page.

### Candidate side

1. Candidate receives a matchmaker recommendation entry.
2. Candidate can choose `愿意认识` or `暂不考虑`.
3. Candidate never sees whether the request was user-initiated or system-initiated.

### Mutual accept

1. If both sides accept, the relationship becomes chat-eligible.
2. Relationships page exposes the chat entry point.
3. Candidate detail page remains informational; it does not become the process center.

## State Model

### Detail page CTA

- `idle`: `愿意认识`
- `submitted`: one-time confirmation only; no long-lived state UX here

### Relationship record states

- `pending_outreach`: submitted, waiting to be delivered
- `awaiting_reply`: delivered, waiting for the other side
- `accepted`: other side accepted; ready for handoff / chat eligibility
- `declined`: other side declined
- `timed_out`: no reply within reply window
- `closed`: flow completed or manually closed

### Chat eligibility

- Chat is allowed only when the corresponding proxy-intro case has reached an accepted / handoff-complete state and a relation/chat record exists.

## Existing System Capabilities To Reuse

- `proxy_intro` case lifecycle in matchmaking system
- recommendation action and conversion view plumbing
- relationships page relation/timeline loading
- chat/ledger access control

## Implementation Plan

### Phase 1

1. Replace candidate-detail direct-chat CTA with `愿意认识`.
2. Submit a formal proxy-intro request instead of opening chat.
3. Add a lightweight success hint: "已提交，可在关系里查看进度".
4. Add a "牵线中" section to relationships page using existing relation/conversion signals.

### Phase 2

1. Surface inbound proxy-intro items with `愿意认识 / 暂不考虑`.
2. Unify the status mapping for requester and candidate views.
3. Make relationships page the single source of truth for progress.

### Phase 3

1. Gate chat opening by bilateral acceptance only.
2. Remove any remaining candidate-detail code paths that can open chat directly.
3. Add decline/timeout/cooling copy to relationship records.

## Frontend Responsibilities

### Candidate detail page

- show profile
- submit interest
- never own the long-running state machine

### Relationships page

- show active chats
- show pending proxy-intro records
- show final handoff states

### Recommendation inbox

- keep recommendation browsing
- later expose candidate-side accept/decline where applicable

## Backend Responsibilities

### Proxy intro request

- create or reuse a proxy-intro case
- record `request_proxy_intro`
- keep the receiving side anonymized behind a matchmaker recommendation

### Reply

- record `accepted` or `declined`
- update recommendation conversion views and relationship state revisions

### Handoff

- once accepted, hand off to relation/chat creation
- expose chat only after handoff succeeds

## Acceptance Criteria

1. Candidate detail page no longer says `开始聊天`.
2. Clicking `愿意认识` does not open chat.
3. After clicking, user is told to check relationships for progress.
4. Relationships page shows pending intro progress separately from active chats.
5. Chat entry remains available only from relationship/chat records, not directly from candidate detail.
