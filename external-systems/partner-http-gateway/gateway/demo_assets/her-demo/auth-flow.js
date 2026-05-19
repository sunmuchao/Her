(() => {
  const STORAGE_KEY = "her_demo_auth_state";
  const RESEND_SECONDS = 60;
  const REDIRECT_DELAY_MS = 1200;

  function readState() {
    try {
      const raw = window.localStorage.getItem(STORAGE_KEY);
      return raw ? JSON.parse(raw) : {};
    } catch (error) {
      return {};
    }
  }

  function writeState(patch) {
    const next = Object.assign({}, readState(), patch);
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
    } catch (error) {
      return next;
    }
    return next;
  }

  function digitsOnly(value) {
    return String(value || "").replace(/\D+/g, "");
  }

  function isValidCnPhone(phone) {
    return /^1[3-9]\d{9}$/.test(String(phone || ""));
  }

  function maskPhone(phone) {
    const digits = digitsOnly(phone);
    if (digits.length < 7) {
      return digits || "138****8888";
    }
    return `${digits.slice(0, 3)}****${digits.slice(-4)}`;
  }

  function scenarioFromPhone(phone) {
    const digits = digitsOnly(phone);
    const last = Number(digits.slice(-1));
    if (Number.isNaN(last)) {
      return "existing";
    }
    return last % 2 === 0 ? "existing" : "new";
  }

  function nextPathForScenario(scenario) {
    return scenario === "new" ? "/demo/auth/onboarding/basic" : "/demo/discovery";
  }

  function getQueryPhone() {
    const params = new URLSearchParams(window.location.search);
    return digitsOnly(params.get("phone") || "");
  }

  function setRowMessage(row, message) {
    const textNode = row ? row.querySelector("span:last-child") : null;
    if (textNode) {
      textNode.textContent = message;
    }
  }

  function setButtonLoading(button, loading, loadingLabel) {
    if (!button) {
      return;
    }
    if (!button.dataset.defaultLabel) {
      button.dataset.defaultLabel = button.textContent.trim();
    }
    button.dataset.loading = loading ? "true" : "false";
    button.classList.toggle("is-loading", loading);
    button.textContent = loading ? loadingLabel : button.dataset.defaultLabel;
  }

  async function postJson(url, payload) {
    const response = await window.fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    let data = {};
    try {
      data = await response.json();
    } catch (error) {
      data = {};
    }
    return { response, data };
  }

  function installDialogs() {
    const overlays = Array.from(document.querySelectorAll("[data-dialog]"));
    if (!overlays.length) {
      return;
    }

    function closeDialog(dialog) {
      if (!dialog) {
        return;
      }
      dialog.classList.add("is-hidden");
      dialog.setAttribute("aria-hidden", "true");
    }

    function openDialog(name) {
      const dialog = document.querySelector(`[data-dialog="${name}"]`);
      if (!dialog) {
        return;
      }
      dialog.classList.remove("is-hidden");
      dialog.setAttribute("aria-hidden", "false");
    }

    document.addEventListener("click", (event) => {
      const trigger = event.target.closest("[data-dialog-trigger]");
      if (trigger) {
        event.preventDefault();
        event.stopPropagation();
        openDialog(trigger.getAttribute("data-dialog-trigger"));
        return;
      }

      const close = event.target.closest("[data-dialog-close]");
      if (close) {
        closeDialog(close.closest("[data-dialog]"));
        return;
      }

      const overlay = event.target.closest("[data-dialog]");
      if (overlay && event.target === overlay) {
        closeDialog(overlay);
      }
    });

    document.addEventListener("keydown", (event) => {
      if (event.key !== "Escape") {
        return;
      }
      overlays.forEach((dialog) => closeDialog(dialog));
    });
  }

  function initBrandLetterBackdrop() {
    const lineNodes = Array.from(document.querySelectorAll("[data-letter-line]"));
    if (!lineNodes.length) {
      return;
    }

    const rowNodes = lineNodes.map((node) => node.closest(".auth-letter-line"));
    const motionPreference = window.matchMedia("(prefers-reduced-motion: reduce)");
    const letters = [
      ["亲爱的你：", "如果今晚还没遇见，", "那就让这封信先替我靠近你。"],
      ["见字如面。", "我把想说的话慢慢敲进夜色里，", "等你登录时刚好读到。"],
      ["也许我们还不认识，", "但故事已经在输入框里发光，", "只差你按下开始。"],
      ["愿你来的时候，", "有人真诚地看见你，", "也愿你刚好也看见对方。"],
    ];
    const state = {
      letterIndex: 0,
      timerId: 0,
    };

    function clearTimer() {
      if (!state.timerId) {
        return;
      }
      window.clearTimeout(state.timerId);
      state.timerId = 0;
    }

    function schedule(delay, callback) {
      clearTimer();
      state.timerId = window.setTimeout(callback, delay);
    }

    function setActiveLine(index) {
      rowNodes.forEach((row, rowIndex) => {
        if (!row) {
          return;
        }
        row.classList.toggle("is-active", rowIndex === index);
      });
    }

    function clearLines() {
      lineNodes.forEach((node) => {
        node.textContent = "";
      });
    }

    function renderStaticLetter() {
      const letter = letters[0];
      lineNodes.forEach((node, index) => {
        node.textContent = letter[index] || "";
      });
      setActiveLine(-1);
    }

    function nextDelay(text, charIndex) {
      if (charIndex === 0) {
        return 150;
      }
      const previousChar = text.charAt(charIndex - 1);
      if (/[，。！？,.]/.test(previousChar)) {
        return 180;
      }
      return 68 + Math.round(Math.random() * 42);
    }

    function typeLine(letter, lineIndex, charIndex) {
      if (document.visibilityState === "hidden") {
        clearTimer();
        return;
      }

      if (lineIndex >= lineNodes.length) {
        setActiveLine(-1);
        schedule(1800, () => {
          state.letterIndex = (state.letterIndex + 1) % letters.length;
          startLoop();
        });
        return;
      }

      const text = letter[lineIndex] || "";
      setActiveLine(lineIndex);
      lineNodes[lineIndex].textContent = text.slice(0, charIndex);

      if (charIndex < text.length) {
        schedule(nextDelay(text, charIndex), () => {
          typeLine(letter, lineIndex, charIndex + 1);
        });
        return;
      }

      schedule(320, () => {
        typeLine(letter, lineIndex + 1, 0);
      });
    }

    function startLoop() {
      clearTimer();
      if (motionPreference.matches) {
        renderStaticLetter();
        return;
      }

      clearLines();
      setActiveLine(0);
      schedule(260, () => {
        typeLine(letters[state.letterIndex], 0, 0);
      });
    }

    function handleVisibilityChange() {
      if (document.visibilityState === "hidden") {
        clearTimer();
        return;
      }
      startLoop();
    }

    if (typeof motionPreference.addEventListener === "function") {
      motionPreference.addEventListener("change", startLoop);
    } else if (typeof motionPreference.addListener === "function") {
      motionPreference.addListener(startLoop);
    }

    document.addEventListener("visibilitychange", handleVisibilityChange);
    startLoop();
  }

  function initAuthEntry() {
    const form = document.getElementById("auth-entry-form");
    if (!form) {
      return;
    }

    const phoneInput = document.getElementById("auth-phone-input");
    const phoneShell = document.getElementById("auth-phone-shell");
    const phoneError = document.getElementById("auth-entry-error");
    const agreement = document.getElementById("auth-agreement");
    const agreementError = document.getElementById("auth-agreement-error");
    const submitButton = document.getElementById("auth-entry-submit");
    const phoneFromQuery = getQueryPhone();
    const storedPhone = digitsOnly(readState().phone);
    let touchedPhone = false;
    let submitted = false;

    if (isValidCnPhone(phoneFromQuery)) {
      phoneInput.value = phoneFromQuery;
    } else if (isValidCnPhone(storedPhone)) {
      phoneInput.value = storedPhone;
    }

    function renderPhoneState() {
      const value = digitsOnly(phoneInput.value).slice(0, 11);
      phoneInput.value = value;
      const showInvalid = (submitted || touchedPhone) && value.length > 0 && !isValidCnPhone(value);
      phoneShell.classList.toggle("is-invalid", showInvalid);
      phoneError.classList.toggle("is-hidden", !showInvalid);
    }

    function renderAgreementState() {
      const showInvalid = submitted && !agreement.checked;
      agreementError.classList.toggle("is-hidden", !showInvalid);
    }

    function renderSubmitState() {
      const ready = isValidCnPhone(phoneInput.value) && agreement.checked;
      submitButton.disabled = !ready || submitButton.dataset.loading === "true";
    }

    phoneInput.addEventListener("input", () => {
      renderPhoneState();
      renderSubmitState();
    });

    phoneInput.addEventListener("blur", () => {
      touchedPhone = true;
      renderPhoneState();
    });

    agreement.addEventListener("change", () => {
      renderAgreementState();
      renderSubmitState();
    });

    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      submitted = true;
      touchedPhone = true;
      renderPhoneState();
      renderAgreementState();
      renderSubmitState();

      const phone = digitsOnly(phoneInput.value).slice(0, 11);
      if (!isValidCnPhone(phone) || !agreement.checked) {
        return;
      }

      setButtonLoading(submitButton, true, "发送中...");
      renderSubmitState();

      try {
        const { response, data } = await postJson("/v1/auth/sms/send-code", { phone });
        if (!response.ok) {
          throw new Error(
            (((data || {}).error || {}).message || "验证码发送失败，请稍后重试").toString()
          );
        }
        const scenario = (((data || {}).flow || {}).scenario || scenarioFromPhone(phone)).toString();
        const resendInSeconds = Number((((data || {}).delivery || {}).resend_in_seconds || RESEND_SECONDS));
        writeState({
          phone,
          scenario,
          nextPath: (((data || {}).flow || {}).next_path || nextPathForScenario(scenario)).toString(),
          resendAvailableAt: Date.now() + resendInSeconds * 1000,
          resendCount: 0,
          verifyAttempts: 0,
          verifiedAt: null,
        });
        window.location.href = `/demo/auth/code?phone=${encodeURIComponent(phone)}`;
      } catch (error) {
        setButtonLoading(submitButton, false, "");
        setRowMessage(
          phoneError,
          error instanceof Error ? error.message : "验证码发送失败，请稍后重试"
        );
        phoneShell.classList.add("is-invalid");
        phoneError.classList.remove("is-hidden");
        renderSubmitState();
      }
    });

    renderPhoneState();
    renderAgreementState();
    renderSubmitState();
  }

  function initAuthCode() {
    const form = document.getElementById("auth-code-form");
    if (!form) {
      return;
    }

    const phoneText = document.getElementById("auth-code-phone");
    const flowCopy = document.getElementById("auth-flow-copy");
    const demoCodeCopy = document.getElementById("auth-demo-code-copy");
    const inputs = Array.from(document.querySelectorAll(".auth-otp-input"));
    const submitButton = document.getElementById("auth-code-submit");
    const resendButton = document.getElementById("auth-code-resend");
    const voiceButton = document.getElementById("auth-code-voice");
    const errorRow = document.getElementById("auth-code-error");
    const successRow = document.getElementById("auth-code-success");
    const backLink = document.getElementById("auth-code-back");
    const editPhoneButton = document.getElementById("auth-code-edit-phone");
    const queryPhone = getQueryPhone();
    let state = readState();
    let verifying = false;
    let autoSubmitTimer = null;

    if (isValidCnPhone(queryPhone)) {
      state = writeState({
        phone: queryPhone,
        scenario: scenarioFromPhone(queryPhone),
      });
    }

    const phone = isValidCnPhone(state.phone) ? state.phone : queryPhone;
    const scenario = state.scenario || scenarioFromPhone(phone);
    const maskedPhone = maskPhone(phone);
    const backHref = `/demo/auth${isValidCnPhone(phone) ? `?phone=${encodeURIComponent(phone)}` : ""}`;

    phoneText.textContent = maskedPhone;
    flowCopy.textContent =
      scenario === "new"
        ? "首次验证成功后继续完善基础资料，再进入推荐与发现。"
        : "老用户验证成功后直接进入首页，继续浏览与沟通。";
    backLink.setAttribute("href", backHref);
    editPhoneButton.addEventListener("click", () => {
      window.location.href = backHref;
    });

    function renderHintCopy() {
      if (!demoCodeCopy) {
        return;
      }
      demoCodeCopy.textContent =
        "验证码应已发送到你的手机。如果长时间未收到，请重新发送或检查短信通道是否配置成功。";
    }

    function codeValue() {
      return inputs.map((input) => input.value).join("");
    }

    function setInputsDisabled(disabled) {
      inputs.forEach((input) => {
        input.disabled = disabled;
      });
    }

    function clearInputs() {
      inputs.forEach((input) => {
        input.value = "";
        input.classList.remove("is-filled");
      });
      inputs[0].focus();
    }

    function renderInputState() {
      inputs.forEach((input) => {
        input.classList.toggle("is-filled", Boolean(input.value));
      });
      submitButton.disabled = codeValue().length < 6 || verifying;
    }

    function remainingSeconds() {
      const resendAt = Number(readState().resendAvailableAt || 0);
      return Math.max(0, Math.ceil((resendAt - Date.now()) / 1000));
    }

    function renderResendState() {
      const remaining = remainingSeconds();
      resendButton.disabled = remaining > 0 || verifying;
      resendButton.textContent = remaining > 0 ? `${remaining} 秒后重新发送` : "重新发送验证码";
      voiceButton.disabled = remaining > 20 || verifying;
    }

    function showError(message) {
      successRow.classList.add("is-hidden");
      setRowMessage(errorRow, message);
      errorRow.classList.remove("is-hidden");
    }

    function showSuccess(message) {
      errorRow.classList.add("is-hidden");
      setRowMessage(successRow, message);
      successRow.classList.remove("is-hidden");
    }

    function finishVerification() {
      const latest = readState();
      const latestScenario = (latest.scenario || scenario).toString();
      const target = (latest.nextPath || nextPathForScenario(latestScenario)).toString();
      showSuccess(
        latestScenario === "new" ? "验证成功，正在进入资料完善..." : "验证成功，正在进入首页..."
      );
      setButtonLoading(submitButton, false, "");
      submitButton.textContent = "验证通过";
      submitButton.disabled = true;
      window.setTimeout(() => {
        window.location.href = target;
      }, REDIRECT_DELAY_MS);
    }

    function verifyCode(event) {
      if (event) {
        event.preventDefault();
      }
      if (verifying || codeValue().length < 6) {
        return;
      }

      verifying = true;
      renderInputState();
      renderResendState();
      errorRow.classList.add("is-hidden");
      successRow.classList.add("is-hidden");
      setInputsDisabled(true);
      setButtonLoading(submitButton, true, "验证中...");

      const currentCode = codeValue();
      const nextAttempts = Number(readState().verifyAttempts || 0) + 1;

      postJson("/v1/auth/sms/verify-code", { phone, code: currentCode })
        .then(({ response, data }) => {
          if (!response.ok) {
            writeState({ verifyAttempts: nextAttempts });
            showError(
              (((data || {}).error || {}).message || "验证码错误，请重新输入").toString()
            );
            setInputsDisabled(false);
            verifying = false;
            setButtonLoading(submitButton, false, "");
            clearInputs();
            renderInputState();
            renderResendState();
            return;
          }
          writeState({
            verifyAttempts: 0,
            verifiedAt: Date.now(),
            scenario: ((((data || {}).flow || {}).scenario || scenario)).toString(),
            nextPath: ((((data || {}).flow || {}).next_path || readState().nextPath || nextPathForScenario(scenario))).toString(),
          });
          verifying = false;
          finishVerification();
        })
        .catch(() => {
          showError("验证码校验失败，请稍后重试");
          setInputsDisabled(false);
          verifying = false;
          setButtonLoading(submitButton, false, "");
          renderInputState();
          renderResendState();
        });
    }

    inputs.forEach((input, index) => {
      input.addEventListener("input", () => {
        input.value = digitsOnly(input.value).slice(0, 1);
        renderInputState();
        errorRow.classList.add("is-hidden");

        if (input.value && index < inputs.length - 1) {
          inputs[index + 1].focus();
        }

        if (codeValue().length === 6) {
          window.clearTimeout(autoSubmitTimer);
          autoSubmitTimer = window.setTimeout(() => {
            verifyCode();
          }, 120);
        }
      });

      input.addEventListener("keydown", (event) => {
        if (event.key === "Backspace" && !input.value && index > 0) {
          inputs[index - 1].focus();
          inputs[index - 1].value = "";
          renderInputState();
          return;
        }

        if (event.key === "ArrowLeft" && index > 0) {
          event.preventDefault();
          inputs[index - 1].focus();
        }

        if (event.key === "ArrowRight" && index < inputs.length - 1) {
          event.preventDefault();
          inputs[index + 1].focus();
        }
      });
    });

    form.addEventListener("paste", (event) => {
      const pasted = digitsOnly(event.clipboardData.getData("text")).slice(0, 6);
      if (!pasted) {
        return;
      }
      event.preventDefault();
      pasted.split("").forEach((digit, index) => {
        if (inputs[index]) {
          inputs[index].value = digit;
        }
      });
      renderInputState();
      const nextIndex = Math.min(pasted.length, inputs.length - 1);
      inputs[nextIndex].focus();
      if (pasted.length === 6) {
        verifyCode();
      }
    });

    form.addEventListener("submit", verifyCode);

    resendButton.addEventListener("click", () => {
      if (remainingSeconds() > 0 || verifying) {
        return;
      }
      resendButton.disabled = true;
      resendButton.textContent = "发送中...";
      postJson("/v1/auth/sms/send-code", { phone })
        .then(({ response, data }) => {
          if (!response.ok) {
            throw new Error((((data || {}).error || {}).message || "验证码发送失败，请稍后重试").toString());
          }
          const resendCount = Number(readState().resendCount || 0) + 1;
          const resendInSeconds = Number((((data || {}).delivery || {}).resend_in_seconds || RESEND_SECONDS));
          writeState({
            resendCount,
            resendAvailableAt: Date.now() + resendInSeconds * 1000,
            verifyAttempts: 0,
          });
          clearInputs();
          renderHintCopy();
          showSuccess("验证码已重新发送，请留意手机短信。");
          renderInputState();
          renderResendState();
        })
        .catch((error) => {
          showError(error instanceof Error ? error.message : "验证码发送失败，请稍后重试");
          renderResendState();
        });
    });

    voiceButton.addEventListener("click", () => {
      showError("语音验证码通道暂未接入，请先使用短信验证码。");
    });

    renderHintCopy();
    renderInputState();
    renderResendState();
    inputs[0].focus();
    window.setInterval(renderResendState, 1000);
  }

  installDialogs();
  initBrandLetterBackdrop();
  initAuthEntry();
  initAuthCode();
})();
