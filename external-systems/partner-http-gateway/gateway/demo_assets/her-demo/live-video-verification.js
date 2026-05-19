      import {
        FaceLandmarker,
        FilesetResolver,
      } from "/demo/assets/mediapipe/vision_bundle.mjs";

      const DEMO_ACTION_POOL = ["blink", "open_mouth", "turn_left"];
      const MODEL_ASSET_PATH =
        "/demo/assets/mediapipe/models/face_landmarker.task";
      const WASM_ROOT = "/demo/assets/mediapipe/wasm";
      const AUTO_SUBMIT_DELAY_MS = 800;
      const SPOKEN_PROMPT_MIN_MS = 2400;
      const DEFAULT_CANVAS_WIDTH = 960;
      const DEFAULT_CANVAS_HEIGHT = 720;

      const ACTION_LABELS = {
        blink: "眨眼",
        open_mouth: "张嘴",
        turn_left: "向左转头",
        turn_right: "向右转头",
        nod_up: "抬头",
      };

      const elements = {
        apiKey: document.getElementById("api-key"),
        userId: document.getElementById("user-id"),
        profileId: document.getElementById("profile-id"),
        openCamera: document.getElementById("open-camera"),
        startFlow: document.getElementById("start-flow"),
        stopFlow: document.getElementById("stop-flow"),
        manualSubmit: document.getElementById("manual-submit"),
        preview: document.getElementById("preview"),
        overlay: document.getElementById("overlay"),
        engineStatus: document.getElementById("engine-status"),
        faceStatus: document.getElementById("face-status"),
        flowStatus: document.getElementById("flow-status"),
        recordStatus: document.getElementById("record-status"),
        challengePhrase: document.getElementById("challenge-phrase"),
        challengeToken: document.getElementById("challenge-token"),
        challengeActions: document.getElementById("challenge-actions"),
        challengeMeta: document.getElementById("challenge-meta"),
        actionList: document.getElementById("action-list"),
        eventLog: document.getElementById("event-log"),
        resultJson: document.getElementById("result-json"),
        submissionBadge: document.getElementById("submission-badge"),
        submissionId: document.getElementById("submission-id"),
        submissionStatusText: document.getElementById("submission-status-text"),
        submissionProvider: document.getElementById("submission-provider"),
        submissionRecommendation: document.getElementById("submission-recommendation"),
        metricBlink: document.getElementById("metric-blink"),
        metricMouth: document.getElementById("metric-mouth"),
        metricTurn: document.getElementById("metric-turn"),
        stageStep: document.getElementById("stage-step"),
        stagePrompt: document.getElementById("stage-prompt"),
        stagePromptNote: document.getElementById("stage-prompt-note"),
      };

      const state = {
        detector: null,
        detectorPromise: null,
        stream: null,
        canvasStream: null,
        recordingStream: null,
        recorder: null,
        recorderChunks: [],
        lastRecordedBlob: null,
        requiredActions: [...DEMO_ACTION_POOL],
        actionState: {},
        actionEvents: [],
        latestMetrics: {
          blink: 0,
          open_mouth: 0,
          turn_left: 0,
        },
        challenge: null,
        running: false,
        submitting: false,
        rafId: 0,
        lastVideoTime: -1,
        logs: [],
        faceCountMax: 0,
        baselineTurnSamples: [],
        baselineTurnOffset: 0,
        autoSubmitTimer: 0,
        recordingCanvas: document.createElement("canvas"),
        recordingContext: null,
        currentActionIndex: 0,
        recordingStartedPerfMs: 0,
        recordingDurationMs: 0,
        audioRecorded: false,
        challengePhraseRendered: false,
        spokenPromptRendered: false,
        spokenPromptShownAtMs: 0,
        spokenPromptDisplayMs: 0,
        speechRecognizer: null,
        speechRecognizerSupported: Boolean(window.SpeechRecognition || window.webkitSpeechRecognition),
        speechRecognitionActive: false,
        speechTranscript: "",
        speechConfidence: 0,
        speechStartedAtMs: null,
        speechEndedAtMs: null,
      };
      state.recordingContext = state.recordingCanvas.getContext("2d");

      function formatBadgeValue(value) {
        return String(value || "idle").replaceAll("_", " ");
      }

      function submissionBadgeState(status) {
        switch (status) {
          case "approved":
            return "approved";
          case "under_review":
            return "review";
          case "resubmission_required":
            return "warning";
          case "rejected":
            return "danger";
          case "error":
            return "error";
          default:
            return "idle";
        }
      }

      function updateSubmissionSummary(payload) {
        if (payload?.error) {
          const errorMessage =
            typeof payload.error === "string"
              ? payload.error
              : payload.error.message || payload.error.code || "检查接口返回";
          elements.submissionBadge.dataset.state = "error";
          elements.submissionBadge.textContent = "Error";
          elements.submissionId.textContent = "submission_id: unavailable";
          elements.submissionStatusText.textContent = "Status: error · Confidence: -";
          elements.submissionProvider.textContent = "Provider: local_oss · Auto-review: -";
          elements.submissionRecommendation.textContent = `Recommended: ${errorMessage}`;
          return;
        }

        const submission = payload?.submission;
        if (!submission) {
          elements.submissionBadge.dataset.state = "idle";
          elements.submissionBadge.textContent = "Idle";
          elements.submissionId.textContent = "submission_id: waiting_for_upload";
          elements.submissionStatusText.textContent = "Status: idle · Confidence: -";
          elements.submissionProvider.textContent = "Provider: local_oss · Auto-review: pending";
          elements.submissionRecommendation.textContent =
            "Recommended: open camera and start verification";
          return;
        }

        const status = String(submission.status || "under_review");
        const confidence =
          submission.confidence_band ||
          submission.machine_review?.confidence_band ||
          submission.machine_review?.overall_confidence_band ||
          "-";
        const provider =
          submission.verification_provider || submission.machine_review?.provider || "local_oss";
        const autoReview =
          submission.auto_review_applied === true
            ? "applied"
            : submission.auto_review_applied === false
              ? "not_applied"
              : "pending";
        const nextStep =
          submission.recommended_next_step || submission.recommended_decision || "manual_review";
        const speechResult = submission.machine_review?.speech_result
          ? ` · Speech: ${submission.machine_review.speech_result}`
          : "";

        elements.submissionBadge.dataset.state = submissionBadgeState(status);
        elements.submissionBadge.textContent = formatBadgeValue(status);
        elements.submissionId.textContent = `submission_id: ${
          submission.submission_id || "generated_after_upload"
        }`;
        elements.submissionStatusText.textContent = `Status: ${status} · Confidence: ${confidence}`;
        elements.submissionProvider.textContent = `Provider: ${provider} · Auto-review: ${autoReview}`;
        elements.submissionRecommendation.textContent = `Recommended: ${nextStep}${speechResult}`;
      }

      function setJsonResult(value) {
        elements.resultJson.textContent = JSON.stringify(value, null, 2);
        updateSubmissionSummary(value);
      }

      function clearAutoSubmitTimer() {
        if (state.autoSubmitTimer) {
          window.clearTimeout(state.autoSubmitTimer);
          state.autoSubmitTimer = 0;
        }
      }

      function setFlowStatus(message, isError = false) {
        elements.flowStatus.textContent = message;
        elements.flowStatus.classList.toggle("error", Boolean(isError));
      }

      function setEngineStatus(message, isError = false) {
        elements.engineStatus.textContent = message;
        elements.engineStatus.parentElement?.classList.toggle("error", Boolean(isError));
      }

      function addLog(message) {
        const timestamp = new Date().toLocaleTimeString("zh-CN", {
          hour12: false,
        });
        state.logs.unshift(`${timestamp} ${message}`);
        state.logs = state.logs.slice(0, 8);
        elements.eventLog.innerHTML = state.logs
          .map((item) => `<li>${escapeHtml(item)}</li>`)
          .join("");
      }

      function escapeHtml(value) {
        return String(value)
          .replaceAll("&", "&amp;")
          .replaceAll("<", "&lt;")
          .replaceAll(">", "&gt;")
          .replaceAll('"', "&quot;")
          .replaceAll("'", "&#39;");
      }

      function persistInputs() {
        localStorage.setItem("live-demo-api-key", elements.apiKey.value);
        localStorage.setItem("live-demo-user-id", elements.userId.value);
        localStorage.setItem("live-demo-profile-id", elements.profileId.value);
      }

      function restoreInputs() {
        elements.apiKey.value = localStorage.getItem("live-demo-api-key") || "";
        elements.userId.value = localStorage.getItem("live-demo-user-id") || "demo-live-user";
        elements.profileId.value = localStorage.getItem("live-demo-profile-id") || "1001";
      }

      function currentUserId() {
        return elements.userId.value.trim();
      }

      function currentProfileId() {
        const raw = elements.profileId.value.trim();
        if (!raw) {
          return null;
        }
        const parsed = Number.parseInt(raw, 10);
        if (Number.isNaN(parsed)) {
          throw new Error("profile_id 必须是整数");
        }
        return parsed;
      }

      function authHeaders() {
        const apiKey = elements.apiKey.value.trim();
        if (!apiKey) {
          return {};
        }
        return {
          Authorization: `Bearer ${apiKey}`,
          "X-API-Key": apiKey,
        };
      }

      async function apiPost(path, payload) {
        const response = await fetch(path, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Accept: "application/json",
            ...authHeaders(),
          },
          body: JSON.stringify(payload),
        });
        const text = await response.text();
        let data = {};
        if (text) {
          try {
            data = JSON.parse(text);
          } catch (error) {
            throw new Error(`接口返回了非 JSON：${text.slice(0, 180)}`);
          }
        }
        if (!response.ok) {
          const message =
            data?.error?.message ||
            data?.message ||
            `HTTP ${response.status} ${response.statusText}`;
          throw new Error(message);
        }
        return data;
      }

      async function ensureDetector() {
        if (state.detector) {
          return state.detector;
        }
        if (state.detectorPromise) {
          return await state.detectorPromise;
        }
        setEngineStatus("正在加载 MediaPipe Face Landmarker...");
        state.detectorPromise = (async () => {
          try {
            const filesetResolver = await FilesetResolver.forVisionTasks(WASM_ROOT);
            state.detector = await FaceLandmarker.createFromOptions(filesetResolver, {
              baseOptions: {
                modelAssetPath: MODEL_ASSET_PATH,
              },
              runningMode: "VIDEO",
              numFaces: 2,
              outputFaceBlendshapes: true,
            });
            setEngineStatus("MediaPipe 已就绪");
            addLog("MediaPipe Face Landmarker 已初始化");
            return state.detector;
          } catch (error) {
            state.detectorPromise = null;
            setEngineStatus("MediaPipe 加载失败", true);
            throw error;
          }
        })();
        return await state.detectorPromise;
      }

      function primeDetectorInBackground() {
        void (async () => {
          try {
            await ensureDetector();
          } catch (error) {
            console.error(error);
            setFlowStatus(
              "活体引擎加载失败，检查 /demo/assets 资源是否完整并重启网关后重试",
              true,
            );
            setJsonResult({
              error: error.message || String(error),
            });
            addLog(`活体引擎加载失败：${error.message || String(error)}`);
          }
        })();
      }

      function waitForVideoReady(timeoutMs = 1800) {
        if (elements.preview.readyState >= 2) {
          return Promise.resolve();
        }
        return new Promise((resolve) => {
          let settled = false;
          const finish = () => {
            if (settled) {
              return;
            }
            settled = true;
            window.clearTimeout(timerId);
            elements.preview.removeEventListener("loadedmetadata", finish);
            elements.preview.removeEventListener("canplay", finish);
            resolve();
          };
          const timerId = window.setTimeout(finish, timeoutMs);
          elements.preview.addEventListener("loadedmetadata", finish, { once: true });
          elements.preview.addEventListener("canplay", finish, { once: true });
        });
      }

      function kickOffPreviewPlayback() {
        const maybePromise = elements.preview.play();
        if (maybePromise && typeof maybePromise.catch === "function") {
          maybePromise.catch((error) => {
            console.warn("preview.play() failed", error);
          });
        }
      }

      function cameraConstraints(includeAudio) {
        return {
          video: {
            facingMode: "user",
            width: { ideal: DEFAULT_CANVAS_WIDTH },
            height: { ideal: DEFAULT_CANVAS_HEIGHT },
          },
          audio: includeAudio
            ? {
                echoCancellation: true,
                noiseSuppression: true,
                autoGainControl: true,
              }
            : false,
        };
      }

      async function openCamera() {
        if (state.stream) {
          kickOffPreviewPlayback();
          await waitForVideoReady();
          resizeCanvases();
          renderStageFrame(null);
          elements.startFlow.disabled = false;
          return;
        }
        if (!navigator.mediaDevices?.getUserMedia) {
          throw new Error("当前浏览器不支持 getUserMedia");
        }
        setEngineStatus("正在打开摄像头...");
        try {
          state.stream = await navigator.mediaDevices.getUserMedia(cameraConstraints(true));
          state.audioRecorded = state.stream.getAudioTracks().length > 0;
        } catch (error) {
          addLog("麦克风未授权，降级为仅视频录制");
          state.stream = await navigator.mediaDevices.getUserMedia(cameraConstraints(false));
          state.audioRecorded = false;
        }
        elements.preview.srcObject = state.stream;
        kickOffPreviewPlayback();
        await waitForVideoReady();
        resizeCanvases();
        renderStageFrame(null);
        setEngineStatus(state.audioRecorded ? "摄像头和麦克风已打开" : "摄像头已打开（当前无音频）");
        elements.faceStatus.textContent = "请正对镜头，保持单人入镜";
        elements.startFlow.disabled = false;
        addLog(state.audioRecorded ? "摄像头和麦克风已打开" : "摄像头已打开（无音频）");
      }

      function resizeCanvases() {
        const width = elements.preview.videoWidth || DEFAULT_CANVAS_WIDTH;
        const height = elements.preview.videoHeight || DEFAULT_CANVAS_HEIGHT;
        elements.overlay.width = width;
        elements.overlay.height = height;
        state.recordingCanvas.width = width;
        state.recordingCanvas.height = height;
      }

      function clearOverlay() {
        const ctx = elements.overlay.getContext("2d");
        if (!ctx) {
          return;
        }
        ctx.clearRect(0, 0, elements.overlay.width, elements.overlay.height);
      }

      function roundedRectPath(ctx, x, y, width, height, radius) {
        const r = Math.min(radius, width / 2, height / 2);
        ctx.beginPath();
        ctx.moveTo(x + r, y);
        ctx.arcTo(x + width, y, x + width, y + height, r);
        ctx.arcTo(x + width, y + height, x, y + height, r);
        ctx.arcTo(x, y + height, x, y, r);
        ctx.arcTo(x, y, x + width, y, r);
        ctx.closePath();
      }

      function wrapLines(ctx, text, maxWidth) {
        const input = String(text || "").trim();
        if (!input) {
          return [];
        }
        const lines = [];
        let current = "";
        for (const char of input) {
          const next = current + char;
          if (current && ctx.measureText(next).width > maxWidth) {
            lines.push(current);
            current = char;
          } else {
            current = next;
          }
        }
        if (current) {
          lines.push(current);
        }
        return lines;
      }

      function drawHudCard(ctx, config) {
        const {
          x,
          y,
          width,
          heading,
          title,
          note,
          accent = "rgba(15, 118, 110, 0.84)",
        } = config;
        const paddingX = 18;
        const paddingY = 16;
        const innerWidth = width - paddingX * 2;

        ctx.save();
        ctx.font = '700 12px "IBM Plex Sans", "Noto Sans SC", sans-serif';
        const headingLines = wrapLines(ctx, heading, innerWidth);
        ctx.font = '700 28px "IBM Plex Sans", "Noto Sans SC", sans-serif';
        const titleLines = wrapLines(ctx, title, innerWidth);
        ctx.font = '500 13px "IBM Plex Sans", "Noto Sans SC", sans-serif';
        const noteLines = wrapLines(ctx, note, innerWidth);

        const headingHeight = headingLines.length ? headingLines.length * 16 + 6 : 0;
        const titleHeight = Math.max(1, titleLines.length) * 32;
        const noteHeight = noteLines.length ? noteLines.length * 18 + 6 : 0;
        const height = paddingY * 2 + headingHeight + titleHeight + noteHeight;

        roundedRectPath(ctx, x, y, width, height, 22);
        ctx.fillStyle = "rgba(10, 16, 15, 0.66)";
        ctx.fill();
        ctx.strokeStyle = "rgba(255, 255, 255, 0.12)";
        ctx.lineWidth = 1;
        ctx.stroke();

        ctx.fillStyle = accent;
        roundedRectPath(ctx, x + paddingX, y + paddingY, 92, 28, 14);
        ctx.fill();

        ctx.fillStyle = "#dffef7";
        ctx.font = '700 12px "IBM Plex Sans", "Noto Sans SC", sans-serif';
        ctx.textBaseline = "top";
        ctx.fillText(headingLines[0] || "", x + paddingX + 12, y + paddingY + 8);

        let cursorY = y + paddingY + 40;
        ctx.fillStyle = "#f7faf9";
        ctx.font = '700 28px "IBM Plex Sans", "Noto Sans SC", sans-serif';
        for (const line of titleLines) {
          ctx.fillText(line, x + paddingX, cursorY);
          cursorY += 32;
        }

        if (noteLines.length) {
          cursorY += 4;
          ctx.fillStyle = "rgba(242, 247, 246, 0.86)";
          ctx.font = '500 13px "IBM Plex Sans", "Noto Sans SC", sans-serif';
          for (const line of noteLines) {
            ctx.fillText(line, x + paddingX, cursorY);
            cursorY += 18;
          }
        }
        ctx.restore();
        return height;
      }

      function computeFaceGeometry(landmarks, width, height, mirror = false) {
        if (!landmarks || !landmarks.length) {
          return null;
        }
        let minX = 1;
        let minY = 1;
        let maxX = 0;
        let maxY = 0;
        for (const point of landmarks) {
          minX = Math.min(minX, point.x);
          minY = Math.min(minY, point.y);
          maxX = Math.max(maxX, point.x);
          maxY = Math.max(maxY, point.y);
        }
        const boxWidth = (maxX - minX) * width;
        const boxHeight = (maxY - minY) * height;
        let x = minX * width;
        if (mirror) {
          x = width - x - boxWidth;
        }
        const y = minY * height;
        const nose = landmarks[1];
        return {
          x,
          y,
          boxWidth,
          boxHeight,
          noseX: nose ? (mirror ? width - nose.x * width : nose.x * width) : null,
          noseY: nose ? nose.y * height : null,
        };
      }

      function drawFaceBoxToContext(ctx, landmarks, { mirror = false } = {}) {
        const geometry = computeFaceGeometry(landmarks, ctx.canvas.width, ctx.canvas.height, mirror);
        if (!geometry) {
          return;
        }
        ctx.save();
        ctx.strokeStyle = "rgba(82, 244, 191, 0.95)";
        ctx.lineWidth = 3;
        ctx.setLineDash([10, 8]);
        ctx.strokeRect(geometry.x, geometry.y, geometry.boxWidth, geometry.boxHeight);
        ctx.setLineDash([]);
        if (geometry.noseX !== null && geometry.noseY !== null) {
          ctx.fillStyle = "rgba(255, 241, 140, 0.98)";
          ctx.beginPath();
          ctx.arc(geometry.noseX, geometry.noseY, 6, 0, Math.PI * 2);
          ctx.fill();
        }
        ctx.restore();
      }

      function formatActionSequence(actions) {
        const values = Array.isArray(actions) ? actions : [];
        if (!values.length) {
          return "等待 challenge";
        }
        return values
          .map((action, index) => `${index + 1}. ${ACTION_LABELS[action] || action}`)
          .join(" -> ");
      }

      function buildFallbackPromptStep(action) {
        return {
          kind: "action",
          action_key: action,
          instruction: `请${ACTION_LABELS[action] || action}`,
        };
      }

      function currentPromptStep() {
        if (!state.challenge) {
          return null;
        }
        const promptSteps = Array.isArray(state.challenge.prompt_steps)
          ? state.challenge.prompt_steps
          : [];
        if (state.currentActionIndex < promptSteps.length) {
          return (
            promptSteps[state.currentActionIndex] ||
            buildFallbackPromptStep(state.requiredActions[state.currentActionIndex])
          );
        }
        if (state.currentActionIndex < state.requiredActions.length) {
          return buildFallbackPromptStep(state.requiredActions[state.currentActionIndex]);
        }
        return null;
      }

      function updateStagePrompt() {
        if (!state.challenge) {
          elements.stageStep.textContent = "等待开始";
          elements.stagePrompt.textContent = "打开摄像头后，开始整套验证";
          elements.stagePromptNote.textContent = "录制视频里会同步带上这条提示。";
          return;
        }
        const promptStep = currentPromptStep();
        if (!promptStep) {
          elements.stageStep.textContent = "已完成";
          elements.stagePrompt.textContent = "保持看镜头，准备提交";
          elements.stagePromptNote.textContent = state.challenge.spoken_code
            ? `随机数字 ${state.challenge.spoken_code} 已写入视频画面`
            : "准备提交当前录制";
          return;
        }
        if (promptStep.kind === "spoken_code") {
          elements.stageStep.textContent = "最后一步";
          elements.stagePrompt.textContent =
            promptStep.instruction || `请大声读出数字 ${state.challenge.spoken_code || ""}`;
          elements.stagePromptNote.textContent = state.speechRecognizerSupported
            ? "这句提示会直接烧进上传视频里，浏览器也会尝试识别你读出的数字。"
            : "这句提示会直接烧进上传视频里；当前浏览器不支持自动语音识别，只会上报音频证据。";
          return;
        }
        elements.stageStep.textContent = `第 ${Math.min(
          state.currentActionIndex + 1,
          state.requiredActions.length,
        )} 步`;
        elements.stagePrompt.textContent =
          promptStep.instruction ||
          `请${ACTION_LABELS[promptStep.action_key] || promptStep.action_key || "完成动作"}`;
        elements.stagePromptNote.textContent = "必须按当前顺序完成，旧录播视频很难直接复用。";
      }

      function resetActionState(actions) {
        state.requiredActions = [...actions];
        state.actionState = {};
        state.actionEvents = [];
        state.latestMetrics = {
          blink: 0,
          open_mouth: 0,
          turn_left: 0,
        };
        state.faceCountMax = 0;
        state.baselineTurnSamples = [];
        state.baselineTurnOffset = 0;
        state.currentActionIndex = 0;
        state.recordingDurationMs = 0;
        state.challengePhraseRendered = false;
        state.spokenPromptRendered = false;
        state.spokenPromptShownAtMs = 0;
        state.spokenPromptDisplayMs = 0;
        resetSpeechState();
        for (const action of actions) {
          state.actionState[action] = {
            completed: false,
            score: 0,
            armed: false,
          };
        }
        renderActionList();
        renderMetrics();
        updateStagePrompt();
      }

      function renderActionList() {
        elements.actionList.innerHTML = state.requiredActions
          .map((action, index) => {
            const info = state.actionState[action] || { completed: false, score: 0 };
            let className = "action-item";
            let statusLabel = "等待前一步";
            if (info.completed) {
              className += " done";
              statusLabel = `已完成 ${info.score}`;
            } else if (index === state.currentActionIndex) {
              className += " active";
              statusLabel = "当前动作";
            }
            return `
              <li class="${className}">
                <div>
                  <strong>${escapeHtml(ACTION_LABELS[action] || action)}</strong>
                  <div class="metric-hint">${escapeHtml(action)}</div>
                </div>
                <span class="action-tag">${escapeHtml(statusLabel)}</span>
              </li>
            `;
          })
          .join("");
      }

      function renderMetrics() {
        elements.metricBlink.textContent = String(state.latestMetrics.blink || 0);
        elements.metricMouth.textContent = String(state.latestMetrics.open_mouth || 0);
        elements.metricTurn.textContent = String(state.latestMetrics.turn_left || 0);
      }

      function updateChallengeUI(challenge) {
        if (!challenge) {
          elements.challengeToken.textContent = "challenge_pending";
          elements.challengePhrase.textContent = "还没拿 challenge";
          elements.challengeActions.textContent = "默认随机池：blink, open_mouth, turn_left";
          elements.challengeMeta.textContent = "打开摄像头后，点“开始整套验证”。";
          return;
        }
        elements.challengeToken.textContent = challenge.challenge_token || "challenge_pending";
        elements.challengePhrase.textContent = challenge.challenge_phrase || "请按提示完成动作";
        elements.challengeActions.textContent = formatActionSequence(challenge.required_actions || []);
        elements.challengeMeta.textContent = [
          `challenge_id: ${challenge.challenge_id || "-"}`,
          `expires_at: ${challenge.expires_at || "-"}`,
          challenge.spoken_code ? `随机数字: ${challenge.spoken_code}` : null,
        ]
          .filter(Boolean)
          .join(" | ");
      }

      function currentRecordingElapsedMs() {
        if (!state.recordingStartedPerfMs) {
          return 0;
        }
        return Math.max(0, Math.round(performance.now() - state.recordingStartedPerfMs));
      }

      function currentSpokenPromptDisplayMs() {
        if (!state.spokenPromptRendered) {
          return 0;
        }
        let displayMs = state.spokenPromptDisplayMs;
        if (state.spokenPromptShownAtMs) {
          displayMs = Math.max(
            displayMs,
            Math.round(Math.max(0, performance.now() - state.spokenPromptShownAtMs)),
          );
        }
        return displayMs;
      }

      function resetSpeechState() {
        state.speechTranscript = "";
        state.speechConfidence = 0;
        state.speechStartedAtMs = null;
        state.speechEndedAtMs = null;
        state.speechRecognitionActive = false;
        state.speechRecognizer = null;
      }

      function speechRecognitionCtor() {
        return window.SpeechRecognition || window.webkitSpeechRecognition || null;
      }

      function startSpeechRecognitionForSpokenChallenge() {
        if (!state.challenge?.spoken_code || state.speechRecognitionActive || state.speechTranscript) {
          return;
        }
        const RecognitionCtor = speechRecognitionCtor();
        if (!RecognitionCtor) {
          addLog("当前浏览器不支持自动语音识别，只会上报音频证据");
          return;
        }
        try {
          const recognition = new RecognitionCtor();
          recognition.lang = "zh-CN";
          recognition.continuous = false;
          recognition.interimResults = true;
          recognition.maxAlternatives = 3;
          recognition.onstart = () => {
            state.speechRecognitionActive = true;
            state.speechStartedAtMs = currentRecordingElapsedMs();
            addLog("浏览器语音识别已启动，等待你读出随机数字");
          };
          recognition.onresult = (event) => {
            let finalText = "";
            let bestConfidence = state.speechConfidence || 0;
            for (let i = event.resultIndex; i < event.results.length; i += 1) {
              const result = event.results[i];
              const alternative = result?.[0];
              if (!alternative?.transcript) {
                continue;
              }
              if (result.isFinal) {
                finalText += alternative.transcript;
              }
              if (typeof alternative.confidence === "number" && Number.isFinite(alternative.confidence)) {
                const normalizedConfidence =
                  alternative.confidence <= 1
                    ? Math.round(alternative.confidence * 100)
                    : Math.round(alternative.confidence);
                bestConfidence = Math.max(bestConfidence, normalizedConfidence);
              }
            }
            if (finalText.trim()) {
              state.speechTranscript = finalText.trim();
              state.speechConfidence = Math.max(0, Math.min(100, bestConfidence));
              state.speechEndedAtMs = currentRecordingElapsedMs();
              addLog(`语音识别结果：${state.speechTranscript}`);
            }
          };
          recognition.onerror = (event) => {
            state.speechRecognitionActive = false;
            addLog(`语音识别失败：${event.error || "unknown_error"}`);
          };
          recognition.onend = () => {
            state.speechRecognitionActive = false;
            if (state.speechStartedAtMs !== null && state.speechEndedAtMs === null) {
              state.speechEndedAtMs = currentRecordingElapsedMs();
            }
            state.speechRecognizer = null;
          };
          state.speechRecognizer = recognition;
          recognition.start();
        } catch (error) {
          addLog(`语音识别启动失败：${error.message || String(error)}`);
        }
      }

      function stopSpeechRecognitionForSpokenChallenge() {
        if (!state.speechRecognizer) {
          return;
        }
        try {
          state.speechRecognizer.stop();
        } catch (error) {
          console.warn("speechRecognition.stop() failed", error);
        }
      }

      function currentSpeechChallengePayload() {
        if (!state.challenge?.spoken_code) {
          return null;
        }
        return {
          provider: state.speechRecognizerSupported
            ? "browser_speech_recognition"
            : "audio_only_fallback",
          transcript_text: state.speechTranscript || null,
          transcript_confidence: state.speechConfidence || null,
          speech_started_at_ms: state.speechStartedAtMs,
          speech_ended_at_ms: state.speechEndedAtMs,
        };
      }

      function chooseRecorderMimeType() {
        const options = [
          "video/webm;codecs=vp9,opus",
          "video/webm;codecs=vp8,opus",
          "video/webm",
          "video/mp4",
        ];
        for (const mimeType of options) {
          if (window.MediaRecorder?.isTypeSupported?.(mimeType)) {
            return mimeType;
          }
        }
        return "";
      }

      function buildRecordingStream() {
        if (!state.recordingCanvas.captureStream) {
          throw new Error("当前浏览器不支持 canvas.captureStream，无法把提示写进视频");
        }
        state.canvasStream = state.recordingCanvas.captureStream(24);
        const mixed = new MediaStream();
        for (const track of state.canvasStream.getVideoTracks()) {
          mixed.addTrack(track);
        }
        if (state.stream) {
          for (const track of state.stream.getAudioTracks()) {
            mixed.addTrack(track);
          }
        }
        state.recordingStream = mixed;
        state.audioRecorded = mixed.getAudioTracks().length > 0;
        return mixed;
      }

      function releaseRecordingStream() {
        if (state.canvasStream) {
          for (const track of state.canvasStream.getTracks()) {
            track.stop();
          }
        }
        state.canvasStream = null;
        state.recordingStream = null;
      }

      function renderCompositeFrame(landmarks) {
        const ctx = state.recordingContext;
        if (!ctx) {
          return;
        }
        const width = state.recordingCanvas.width || DEFAULT_CANVAS_WIDTH;
        const height = state.recordingCanvas.height || DEFAULT_CANVAS_HEIGHT;

        ctx.clearRect(0, 0, width, height);
        if (elements.preview.readyState >= 2) {
          ctx.save();
          ctx.translate(width, 0);
          ctx.scale(-1, 1);
          ctx.drawImage(elements.preview, 0, 0, width, height);
          ctx.restore();
        } else {
          ctx.fillStyle = "#0f172a";
          ctx.fillRect(0, 0, width, height);
        }

        const vignette = ctx.createLinearGradient(0, 0, 0, height);
        vignette.addColorStop(0, "rgba(10, 16, 15, 0.20)");
        vignette.addColorStop(1, "rgba(10, 16, 15, 0.42)");
        ctx.fillStyle = vignette;
        ctx.fillRect(0, 0, width, height);

        if (!state.challenge) {
          drawHudCard(ctx, {
            x: 24,
            y: 24,
            width: Math.min(width - 48, 430),
            heading: "等待 challenge",
            title: "打开摄像头后开始整套验证",
            note: "开始后，随机动作顺序和数字口令会直接出现在录制视频里。",
          });
          return;
        }

        drawHudCard(ctx, {
          x: 24,
          y: 24,
          width: Math.min(width - 48, 520),
          heading: "本次随机 challenge",
          title: state.challenge.challenge_phrase || "请按提示完成动作",
          note: "完整 challenge 文案会直接烧进这段上传视频。",
        });
        if (state.recordingStartedPerfMs) {
          state.challengePhraseRendered = true;
        }

        const promptStep = currentPromptStep();
        const activeTitle =
          promptStep?.kind === "spoken_code" ? "现在读出数字" : "当前动作提示";
        const activeBody = promptStep
          ? promptStep.instruction ||
            `请${ACTION_LABELS[promptStep.action_key] || promptStep.action_key || "完成动作"}`
          : "保持看镜头，准备提交";
        const activeNote =
          promptStep?.kind === "spoken_code"
            ? "这一句也会直接写进视频，用来证明这是当场录的。"
            : "系统只认当前这一步，顺序不对就会被拒。";
        drawHudCard(ctx, {
          x: 24,
          y: height - 176,
          width: Math.min(width - 48, 470),
          heading: activeTitle,
          title: activeBody,
          note: activeNote,
          accent:
            promptStep?.kind === "spoken_code"
              ? "rgba(180, 83, 9, 0.88)"
              : "rgba(15, 118, 110, 0.84)",
        });

        ctx.save();
        roundedRectPath(ctx, width - 192, height - 70, 168, 42, 21);
        ctx.fillStyle = "rgba(10, 16, 15, 0.58)";
        ctx.fill();
        ctx.fillStyle = "#f7faf9";
        ctx.font = '600 14px "IBM Plex Sans", "Noto Sans SC", sans-serif';
        ctx.textBaseline = "middle";
        ctx.fillText(
          state.audioRecorded ? "含音频录制中" : "当前无音频",
          width - 166,
          height - 49,
        );
        ctx.restore();

        if (promptStep?.kind === "spoken_code" && state.recordingStartedPerfMs) {
          state.spokenPromptRendered = true;
          if (!state.spokenPromptShownAtMs) {
            state.spokenPromptShownAtMs = performance.now();
          }
          state.spokenPromptDisplayMs = currentSpokenPromptDisplayMs();
        }

        if (landmarks) {
          drawFaceBoxToContext(ctx, landmarks, { mirror: true });
        }
      }

      function renderOverlayFrame(landmarks) {
        const ctx = elements.overlay.getContext("2d");
        if (!ctx) {
          return;
        }
        ctx.clearRect(0, 0, elements.overlay.width, elements.overlay.height);
        if (landmarks) {
          drawFaceBoxToContext(ctx, landmarks);
        }
      }

      function renderStageFrame(landmarks) {
        updateStagePrompt();
        renderOverlayFrame(landmarks);
        renderCompositeFrame(landmarks);
      }

      function startRecording() {
        if (!window.MediaRecorder) {
          throw new Error("当前浏览器不支持 MediaRecorder");
        }
        if (!state.recordingContext) {
          throw new Error("当前浏览器无法创建录制画布");
        }
        state.lastRecordedBlob = null;
        state.recorderChunks = [];
        resizeCanvases();
        renderStageFrame(null);
        const mediaStream = buildRecordingStream();
        const mimeType = chooseRecorderMimeType();
        const recorder = mimeType
          ? new MediaRecorder(mediaStream, { mimeType })
          : new MediaRecorder(mediaStream);
        recorder.ondataavailable = (event) => {
          if (event.data && event.data.size > 0) {
            state.recorderChunks.push(event.data);
          }
        };
        recorder.start(400);
        state.recordingStartedPerfMs = performance.now();
        state.recordingDurationMs = 0;
        state.challengePhraseRendered = false;
        state.spokenPromptRendered = false;
        state.spokenPromptShownAtMs = 0;
        state.spokenPromptDisplayMs = 0;
        resetSpeechState();
        state.recorder = recorder;
        renderStageFrame(null);
        elements.recordStatus.textContent = `录制中${mimeType ? ` (${mimeType})` : ""}${
          state.audioRecorded ? "，含音频" : "，无音频"
        }`;
        elements.manualSubmit.disabled = false;
        addLog(state.audioRecorded ? "开始录制视频证据（含音频）" : "开始录制视频证据（无音频）");
      }

      async function stopRecording() {
        if (!state.recorder || state.recorder.state === "inactive") {
          return null;
        }
        stopSpeechRecognitionForSpokenChallenge();
        const recorder = state.recorder;
        const mimeType = recorder.mimeType || "video/webm";
        const blob = await new Promise((resolve) => {
          recorder.onstop = () => {
            resolve(new Blob(state.recorderChunks, { type: mimeType }));
          };
          recorder.stop();
        });
        state.recordingDurationMs = currentRecordingElapsedMs();
        state.spokenPromptDisplayMs = currentSpokenPromptDisplayMs();
        state.recordingStartedPerfMs = 0;
        state.spokenPromptShownAtMs = 0;
        state.lastRecordedBlob = blob;
        elements.recordStatus.textContent = "录制已停止";
        state.recorder = null;
        releaseRecordingStream();
        return blob;
      }

      function detectorCategoryScore(categories, name) {
        const hit = categories.find((item) => item.categoryName === name);
        return hit ? hit.score : 0;
      }

      function estimateTurnOffset(landmarks) {
        const leftEye = landmarks[33];
        const rightEye = landmarks[263];
        const nose = landmarks[1];
        if (!leftEye || !rightEye || !nose) {
          return 0;
        }
        const eyeWidth = Math.max(0.0001, Math.abs(rightEye.x - leftEye.x));
        return (nose.x - leftEye.x) / eyeWidth - 0.5;
      }

      function scoreFromMagnitude(value, maxValue) {
        return Math.max(0, Math.min(99, Math.round((Math.abs(value) / maxValue) * 100)));
      }

      function scheduleAutoSubmit(delayMs) {
        clearAutoSubmitTimer();
        state.autoSubmitTimer = window.setTimeout(() => {
          void (async () => {
            try {
              await finishAndSubmit({ autoTriggered: true });
            } catch (error) {
              console.error(error);
              state.submitting = false;
              setFlowStatus(error.message || String(error), true);
              setJsonResult({
                error: error.message || String(error),
              });
              addLog(`报错：${error.message || String(error)}`);
            }
          })();
        }, delayMs);
      }

      function completeAction(action, score) {
        const expectedAction = state.requiredActions[state.currentActionIndex];
        if (!expectedAction || expectedAction !== action) {
          return;
        }
        const slot = state.actionState[action];
        if (!slot || slot.completed) {
          return;
        }
        slot.completed = true;
        slot.score = Math.max(85, Math.min(99, Math.round(score)));
        state.actionEvents.push({
          action,
          step_index: state.currentActionIndex + 1,
          detected_at_ms: currentRecordingElapsedMs(),
          score: slot.score,
        });
        state.currentActionIndex += 1;
        renderActionList();
        updateStagePrompt();
        addLog(`${ACTION_LABELS[action] || action} 已通过，得分 ${slot.score}`);

        if (!allRequiredActionsCompleted() || !state.running) {
          return;
        }
        const nextPrompt = currentPromptStep();
        if (nextPrompt?.kind === "spoken_code") {
          setFlowStatus(`动作完成，请读出数字 ${state.challenge?.spoken_code || ""}`);
          addLog(`进入随机数字口令阶段：${state.challenge?.spoken_code || ""}`);
          startSpeechRecognitionForSpokenChallenge();
          scheduleAutoSubmit(SPOKEN_PROMPT_MIN_MS);
          return;
        }
        setFlowStatus("动作已完成，准备自动提交");
        addLog("全部动作完成，准备自动提交");
        scheduleAutoSubmit(AUTO_SUBMIT_DELAY_MS);
      }

      function updateRealtimeActions(blendshapes, landmarks) {
        const blinkScoreRaw =
          (detectorCategoryScore(blendshapes, "eyeBlinkLeft") +
            detectorCategoryScore(blendshapes, "eyeBlinkRight")) /
          2;
        const mouthScoreRaw = detectorCategoryScore(blendshapes, "jawOpen");
        const turnOffset = estimateTurnOffset(landmarks);

        if (state.baselineTurnSamples.length < 18) {
          state.baselineTurnSamples.push(turnOffset);
          const total = state.baselineTurnSamples.reduce((sum, value) => sum + value, 0);
          state.baselineTurnOffset = total / state.baselineTurnSamples.length;
        }

        const turnDelta = turnOffset - state.baselineTurnOffset;
        state.latestMetrics.blink = Math.round(blinkScoreRaw * 100);
        state.latestMetrics.open_mouth = Math.round(mouthScoreRaw * 100);
        state.latestMetrics.turn_left = scoreFromMagnitude(turnDelta, 0.18);
        renderMetrics();

        const currentAction = state.requiredActions[state.currentActionIndex];
        const slot = state.actionState[currentAction];
        if (!currentAction || !slot || slot.completed) {
          return;
        }

        if (currentAction === "blink") {
          if (blinkScoreRaw < 0.25) {
            slot.armed = true;
          }
          if (slot.armed && blinkScoreRaw > 0.6) {
            completeAction("blink", blinkScoreRaw * 100);
          }
          return;
        }

        if (currentAction === "open_mouth") {
          if (mouthScoreRaw < 0.18) {
            slot.armed = true;
          }
          if (slot.armed && mouthScoreRaw > 0.45) {
            completeAction("open_mouth", mouthScoreRaw * 100);
          }
          return;
        }

        if (currentAction === "turn_left" || currentAction === "turn_right") {
          if (Math.abs(turnDelta) < 0.035) {
            slot.armed = true;
          }
          if (slot.armed && Math.abs(turnDelta) > 0.11) {
            completeAction(currentAction, scoreFromMagnitude(turnDelta, 0.18));
          }
        }
      }

      function allRequiredActionsCompleted() {
        return state.requiredActions.every((action) => state.actionState[action]?.completed);
      }

      function currentActionPayload() {
        const completedActions = state.actionEvents.map((event) => event.action);
        const actionScores = {};
        for (const event of state.actionEvents) {
          actionScores[event.action] = event.score;
        }
        return {
          capture_mode: "realtime_challenge",
          completed_actions: completedActions,
          action_events: state.actionEvents.map((event) => ({ ...event })),
          action_scores: actionScores,
          face_count_max: Math.max(1, state.faceCountMax || 1),
          challenge_passed: allRequiredActionsCompleted(),
          video_recorded: true,
          challenge_phrase_rendered: state.challengePhraseRendered,
          spoken_prompt_rendered: state.spokenPromptRendered,
          spoken_prompt_display_ms: currentSpokenPromptDisplayMs(),
          audio_recorded: state.audioRecorded,
          recording_started_at_ms: 0,
          recording_duration_ms: state.recordingDurationMs || currentRecordingElapsedMs(),
        };
      }

      function runDetectionLoop() {
        cancelAnimationFrame(state.rafId);
        const tick = () => {
          if (!state.running || !state.detector) {
            return;
          }
          if (elements.preview.readyState < 2) {
            renderStageFrame(null);
            state.rafId = requestAnimationFrame(tick);
            return;
          }
          if (elements.preview.currentTime === state.lastVideoTime) {
            state.rafId = requestAnimationFrame(tick);
            return;
          }
          state.lastVideoTime = elements.preview.currentTime;
          const result = state.detector.detectForVideo(elements.preview, performance.now());
          const faces = result.faceLandmarks || [];
          state.faceCountMax = Math.max(state.faceCountMax, faces.length);

          if (!faces.length) {
            elements.faceStatus.textContent = "未检测到人脸，请靠近镜头";
            renderStageFrame(null);
            state.rafId = requestAnimationFrame(tick);
            return;
          }

          if (faces.length > 1) {
            elements.faceStatus.textContent = "检测到多张人脸，请只保留你自己";
          } else {
            elements.faceStatus.textContent = "单人入镜，实时检测中";
          }

          const primaryFace = faces[0];
          renderStageFrame(primaryFace);
          const blendshapes = result.faceBlendshapes?.[0]?.categories || [];
          updateRealtimeActions(blendshapes, primaryFace);
          state.rafId = requestAnimationFrame(tick);
        };
        state.rafId = requestAnimationFrame(tick);
      }

      function stopRealtimeLoop() {
        state.running = false;
        cancelAnimationFrame(state.rafId);
        state.rafId = 0;
        state.lastVideoTime = -1;
      }

      async function blobToBase64(blob) {
        return await new Promise((resolve, reject) => {
          const reader = new FileReader();
          reader.onerror = () => reject(new Error("视频转 base64 失败"));
          reader.onload = () => {
            const result = String(reader.result || "");
            const commaIndex = result.lastIndexOf(",");
            resolve(commaIndex >= 0 ? result.slice(commaIndex + 1) : result);
          };
          reader.readAsDataURL(blob);
        });
      }

      function videoFileName(blob) {
        if ((blob.type || "").includes("mp4")) {
          return `live-demo-${Date.now()}.mp4`;
        }
        return `live-demo-${Date.now()}.webm`;
      }

      async function createChallenge() {
        const userId = currentUserId();
        if (!userId) {
          throw new Error("user_id 不能为空");
        }
        const payload = {
          user_id: userId,
          challenge_action_pool: DEMO_ACTION_POOL,
          action_count: DEMO_ACTION_POOL.length,
        };
        const profileId = currentProfileId();
        if (profileId !== null) {
          payload.profile_id = profileId;
        }
        const data = await apiPost("/v1/verifications/live-video-challenges", payload);
        return data.challenge;
      }

      async function startFullFlow() {
        persistInputs();
        await openCamera();
        await ensureDetector();
        clearAutoSubmitTimer();
        stopRealtimeLoop();
        state.lastRecordedBlob = null;
        if (state.recorder && state.recorder.state !== "inactive") {
          await stopRecording();
        }
        setJsonResult({ status: "starting" });
        setFlowStatus("正在申请随机 challenge...");
        const challenge = await createChallenge();
        state.challenge = challenge;
        updateChallengeUI(challenge);
        resetActionState(challenge.required_actions || DEMO_ACTION_POOL);
        resizeCanvases();
        renderStageFrame(null);
        startRecording();
        state.submitting = false;
        state.running = true;
        setFlowStatus(
          challenge.spoken_code
            ? `请先按顺序做动作，最后读出数字 ${challenge.spoken_code}`
            : "请按顺序做动作",
        );
        addLog(`challenge 已创建：${challenge.challenge_id}`);
        addLog(`本次顺序：${formatActionSequence(challenge.required_actions || [])}`);
        if (challenge.spoken_code) {
          addLog(`随机数字：${challenge.spoken_code}`);
        }
        elements.startFlow.disabled = true;
        runDetectionLoop();
      }

      async function finishAndSubmit({ autoTriggered = false } = {}) {
        if (!state.challenge) {
          throw new Error("还没有 challenge，不能提交");
        }
        if (state.submitting && !autoTriggered) {
          return;
        }
        state.submitting = true;
        clearAutoSubmitTimer();
        try {
          stopRealtimeLoop();
          setFlowStatus("正在结束录制并提交...");
          addLog("结束录制，准备调用 live-video-submissions");
          const blob =
            state.lastRecordedBlob ||
            (state.recorder && state.recorder.state !== "inactive"
              ? await stopRecording()
              : null);
          if (!blob || blob.size === 0) {
            throw new Error("录到的视频为空，请重新试一次");
          }
          const userId = currentUserId();
          const profileId = currentProfileId();
          const videoBase64 = await blobToBase64(blob);
          const payload = {
            user_id: userId,
            video_base64: videoBase64,
            file_name: videoFileName(blob),
            content_type: blob.type || "video/webm",
            challenge_token: state.challenge.challenge_token,
            challenge_phrase: state.challenge.challenge_phrase,
            metadata: {
              action_result: currentActionPayload(),
              speech_challenge_result: currentSpeechChallengePayload(),
            },
          };
          if (profileId !== null) {
            payload.profile_id = profileId;
          }
          const response = await apiPost("/v1/verifications/live-video-submissions", payload);
          setJsonResult(response);
          setFlowStatus(
            response?.submission?.status
              ? `提交完成：${response.submission.status}`
              : "提交完成",
          );
          addLog(
            response?.submission?.submission_id
              ? `提交成功：${response.submission.submission_id}`
              : "提交成功",
          );
          elements.manualSubmit.disabled = true;
          elements.startFlow.disabled = false;
          state.lastRecordedBlob = null;
        } catch (error) {
          state.submitting = false;
          throw error;
        }
        state.submitting = false;
      }

      async function stopEverything() {
        clearAutoSubmitTimer();
        stopRealtimeLoop();
        stopSpeechRecognitionForSpokenChallenge();
        if (state.recorder && state.recorder.state !== "inactive") {
          await stopRecording();
        }
        state.submitting = false;
        state.challenge = null;
        resetSpeechState();
        resetActionState(DEMO_ACTION_POOL);
        updateChallengeUI(null);
        clearOverlay();
        renderStageFrame(null);
        elements.manualSubmit.disabled = true;
        elements.recordStatus.textContent = "未录制";
        elements.startFlow.disabled = false;
        setFlowStatus("已停止");
        addLog("已停止当前流程");
      }

      async function withUiAction(
        action,
        {
          disableOpenCamera = true,
          disableStartFlow = true,
          disableManualSubmit = true,
          disableStopFlow = true,
        } = {},
      ) {
        if (disableOpenCamera) {
          elements.openCamera.disabled = true;
        }
        if (disableStartFlow) {
          elements.startFlow.disabled = true;
        }
        if (disableManualSubmit) {
          elements.manualSubmit.disabled = true;
        }
        if (disableStopFlow) {
          elements.stopFlow.disabled = true;
        }
        try {
          await action();
        } catch (error) {
          console.error(error);
          setFlowStatus(error.message || String(error), true);
          setJsonResult({
            error: error.message || String(error),
          });
          addLog(`报错：${error.message || String(error)}`);
        } finally {
          if (disableOpenCamera) {
            elements.openCamera.disabled = false;
          }
          if (disableStartFlow) {
            elements.startFlow.disabled = state.running || state.submitting;
          }
          if (disableStopFlow) {
            elements.stopFlow.disabled = false;
          }
          if (disableManualSubmit) {
            elements.manualSubmit.disabled =
              !state.recorder ||
              state.recorder.state === "inactive" ||
              state.submitting;
          }
        }
      }

      restoreInputs();
      updateChallengeUI(null);
      updateSubmissionSummary(null);
      resetActionState(DEMO_ACTION_POOL);
      renderMetrics();
      resizeCanvases();
      renderStageFrame(null);
      elements.startFlow.disabled = false;

      window.addEventListener("resize", () => {
        resizeCanvases();
        renderStageFrame(null);
      });
      elements.apiKey.addEventListener("change", persistInputs);
      elements.userId.addEventListener("change", persistInputs);
      elements.profileId.addEventListener("change", persistInputs);

      elements.openCamera.addEventListener("click", () => {
        void withUiAction(
          async () => {
            await openCamera();
            primeDetectorInBackground();
            setFlowStatus("摄像头已打开，可以直接开始；活体引擎继续后台加载");
          },
          {
            disableStartFlow: false,
            disableManualSubmit: false,
            disableStopFlow: false,
          },
        );
      });

      elements.startFlow.addEventListener("click", () => {
        void withUiAction(async () => {
          await startFullFlow();
        });
      });

      elements.manualSubmit.addEventListener("click", () => {
        void withUiAction(async () => {
          await finishAndSubmit();
        });
      });

      elements.stopFlow.addEventListener("click", () => {
        void withUiAction(async () => {
          await stopEverything();
        });
      });
