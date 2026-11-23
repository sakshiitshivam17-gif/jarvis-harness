/* ==========================================================================
   J.A.R.V.I.S. // voice link + HUD controller
   ========================================================================== */
(() => {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const params = new URLSearchParams(location.search);
  const DEMO = params.has("demo");
  const DEFAULT_WAKE = ["jarvis", "jervis", "jarvus", "parvez", "parvis", "javis", "jarvix", "harvis", "charvis", "darvis", "jarvez", "जार्विस"];
  const WAKE_RE = /\b(?:jarvis|jervis|jarvus|parvez|parvis|javis|jarvix|harvis|charvis|darvis|jarvez|जार्विस)\b/i;
  const YES_NO_RE = /\b(yes|no|yeah|nope|confirm|cancel|affirmative|negative|do it|abort)\b/i;

  const state = {
    booted: false,
    engaged: false,
    awake: false,
    busy: false,
    queued: null,
    pending: false,
    speaking: false,
    listening: false,
    recognizing: false,
    wantMic: false,
    stream: null,
    audioCtx: null,
    micAnalyser: null,
    ttsAnalyser: null,
    micData: null,
    ttsData: null,
    audioEl: $("tts-audio"),
    currentUrl: null,
    speechToken: 0,
    awakeTimer: null,
    awakeUntil: 0,
    lastFinal: "",
    lastFinalAt: 0,
    saidWhileSpeaking: null,
    lastSpeechError: "",
    wakeWords: DEFAULT_WAKE,
    config: null,
    stats: null,
    capabilities: {},
    entryCount: 0,
    lastStatsAt: 0,
    bootFinished: false,
  };

  const el = {
    boot: $("boot"),
    bootLog: $("boot-log"),
    bootProgress: document.querySelector(".boot-progress i"),
    engage: $("engage"),
    bootNote: $("boot-note"),
    app: $("app"),
    clock: $("clock"),
    date: $("date"),
    stateText: $("state-text"),
    footerState: $("footer-state"),
    linkChipState: $("link-chip-state"),
    neuralChip: $("neural-chip"),
    ttsChip: $("tts-chip"),
    visionChip: $("vision-chip"),
    feed: $("feed"),
    feedCount: $("feed-count"),
    interim: $("interim"),
    interimText: $("interim-text"),
    footerHeard: $("footer-heard"),
    logList: $("log-list"),
    toasts: $("toasts"),
    helpModal: $("help-modal"),
    helpBody: $("help-body"),
    manualToggle: $("manual-toggle"),
    manualField: $("manual-field"),
    manualForm: $("manual-form"),
    manualInput: $("manual-input"),
    waveform: $("waveform"),
    reactor: $("reactor"),
    meterFill: $("meter-fill"),
    meterDb: $("meter-db"),
    latency: $("latency"),
    coreLoad: $("core-load"),
    coreTemp: $("core-temp"),
    awakeWindow: $("awake-window"),
    agentBar: $("agent-bar"),
    agentTrace: $("agent-trace"),
    agentTask: $("agent-task"),
    agentStep: $("agent-step"),
    agentStop: $("agent-stop"),
    listenBtn: $("listen-btn"),
    listenLabel: $("listen-label"),
    footerStop: $("footer-stop"),
    footerStopLabel: $("footer-stop-label"),
  };

  /* ------------------------------------------------------------------ utils */
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const pad = (n) => String(n).padStart(2, "0");
  const timeString = () => {
    const d = new Date();
    return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
  };
  const shortTime = () => {
    const d = new Date();
    return `${pad(d.getHours())}:${pad(d.getMinutes())}`;
  };
  const escapeHtml = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const clamp = (n, a, b) => Math.max(a, Math.min(b, n));

  async function api(path, options = {}) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), options.timeout || 30000);
    try {
      const response = await fetch(path, {
        ...options,
        signal: controller.signal,
        headers: { "Content-Type": "application/json", ...(options.headers || {}) },
      });
      const type = response.headers.get("Content-Type") || "";
      if (!response.ok) {
        let payload = null;
        if (type.includes("json")) payload = await response.json().catch(() => null);
        const err = new Error((payload && payload.say) || `Request failed (${response.status})`);
        err.payload = payload;
        throw err;
      }
      return type.includes("json") ? response.json() : response;
    } finally {
      clearTimeout(timer);
    }
  }

  function toast(title, message, kind = "") {
    const node = document.createElement("div");
    node.className = `toast ${kind}`.trim();
    node.innerHTML = `<strong>${escapeHtml(title)}</strong>${escapeHtml(message)}`;
    el.toasts.appendChild(node);
    setTimeout(() => {
      node.style.transition = "opacity .3s, transform .3s";
      node.style.opacity = "0";
      node.style.transform = "translateX(12px)";
      setTimeout(() => node.remove(), 350);
    }, 4600);
  }

  /* ------------------------------------------------------------------ boot */
  const BOOT_LINES = [
    ["CORE WAKE // MK-II", 16],
    ["HOST INTERFACE ......... MOUNTED", 34],
    ["TELEMETRY BUS ........... ONLINE", 52],
    ["NEURAL CORE ............. LINKED", 70],
    ["VOICE SYNTHESIS ......... ARMED", 86],
    ["ALL SYSTEMS NOMINAL", 100],
  ];

  async function runBoot() {
    try {
      state.config = await api("/api/state");
      applyConfig(state.config);
    } catch (err) {
      el.bootLog.innerHTML = `<span class="hot">SERVER LINK FAILED</span><br>Start app.py and reload.`;
      el.engage.hidden = false;
      el.engage.querySelector("span:last-child").textContent = "RETRY LINK";
      el.engage.onclick = () => location.reload();
      return;
    }

    for (const [line, progress] of BOOT_LINES) {
      const row = document.createElement("div");
      row.innerHTML = `<span class="good">›</span> ${escapeHtml(line)}`;
      el.bootLog.innerHTML = "";
      el.bootLog.appendChild(row);
      el.bootProgress.style.width = `${progress}%`;
      await sleep(DEMO ? 120 : 330);
    }
    el.engage.hidden = false;
    if (DEMO) {
      await sleep(250);
      enterApp({ demo: true });
    }
  }

  function applyConfig(cfg) {
    state.capabilities = cfg.capabilities || {};
    state.wakeWords = Array.isArray(cfg.wake_words) && cfg.wake_words.length ? cfg.wake_words : DEFAULT_WAKE;
    if (cfg.awake_seconds) el.awakeWindow.textContent = cfg.awake_seconds;
    const neural = el.neuralChip;
    const neuralReady = !!state.capabilities.llm;
    neural.classList.toggle("ready", neuralReady);
    neural.classList.toggle("offline", !neuralReady);
    neural.querySelector("em").textContent = neuralReady ? "LINKED" : "LOCAL";
    const vision = el.visionChip;
    const visionReady = !!state.capabilities.screen_ocr;
    vision.classList.toggle("ready", visionReady);
    vision.classList.toggle("offline", !visionReady);
    vision.querySelector("em").textContent = visionReady ? "OCR" : "OFFLINE";
    const tts = el.ttsChip;
    const ttsReady = !!state.capabilities.tts;
    tts.classList.toggle("ready", ttsReady);
    tts.classList.toggle("offline", !ttsReady);
    tts.querySelector("em").textContent = ttsReady ? "NEURAL" : "BROWSER";
    if (cfg.greeting) {
      state.greeting = cfg.greeting;
      if (cfg.capabilities && cfg.capabilities.tts) {
        fetch(`/api/tts?text=${encodeURIComponent(cfg.greeting)}`).catch(() => {});
      }
    }
    if (cfg.stats) updateStats(cfg.stats);
    if (cfg.logs) cfg.logs.slice(-24).forEach((entry) => appendLog(entry, false));
  }

  async function enterApp({ demo = false } = {}) {
    if (state.engaged) return;
    state.engaged = true;
    state.booted = true;
    el.boot.classList.add("done");
    el.app.classList.remove("is-locked");
    el.app.setAttribute("aria-hidden", "false");
    setTimeout(() => { el.boot.style.display = "none"; }, 950);
    addMessage("jarvis", state.greeting || "All systems online, sir. Voice link is standing by.", {
      badge: "SYSTEMS ONLINE", badgeKind: "green", typing: !DEMO,
    });
    setAwake(false);
    setState("listening");
    if (!demo) {
      playChime([660, 990], 0.05);
      speak("Voice link engaged. At your service, sir.");
      pollStatus();
    }
    if (DEMO) {
      await sleep(500);
      addMessage("user", "Jarvis, open Chrome and give me a status report.", { badge: "VOICE INPUT" });
      await sleep(400);
      addMessage("jarvis", "Opening Chrome, sir. All systems are online — CPU 24 percent, memory 41 percent, power cell 91 percent. Neural core linked.", {
        badge: "EXECUTED", badgeKind: "green", detail: "Launched flatpak run com.google.Chrome · Telemetry nominal", typing: true,
      });
      el.interimText.textContent = "Say “Jarvis” to wake the link.";
    }
  }

  async function engage() {
    if (state.engaged) return;
    el.engage.disabled = true;
    el.engage.querySelector("span:last-child").textContent = "LINKING…";
    el.bootNote.hidden = true;
    try {
      await ensureAudio();
      await startRecognition();
      el.bootLog.innerHTML = `<span class="good">›</span> MICROPHONE ACQUIRED · SPEECH SERVICE ONLINE`;
      await api("/api/engage", { method: "POST", body: "{}" }).catch(() => {});
      await enterApp();
    } catch (err) {
      el.engage.disabled = false;
      el.engage.querySelector("span:last-child").textContent = "RETRY VOICE LINK";
      el.bootNote.hidden = false;
      el.bootNote.textContent = `Microphone blocked: ${err.message || "permission denied"}. Allow access, then retry.`;
      toast("VOICE LINK", "Microphone unavailable. You can still use manual override.", "red");
      await enterApp();
    }
  }

  /* -------------------------------------------------------------- audio/mic */
  async function ensureAudio() {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      throw new Error("getUserMedia unsupported");
    }
    if (!state.stream) {
      state.stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
      });
    }
    if (!state.audioCtx) {
      const Ctx = window.AudioContext || window.webkitAudioContext;
      state.audioCtx = new Ctx();
      const source = state.audioCtx.createMediaStreamSource(state.stream);
      state.micAnalyser = state.audioCtx.createAnalyser();
      state.micAnalyser.fftSize = 512;
      state.micAnalyser.smoothingTimeConstant = 0.75;
      state.micData = new Uint8Array(state.micAnalyser.fftSize);
      source.connect(state.micAnalyser);

      state.ttsAnalyser = state.audioCtx.createAnalyser();
      state.ttsAnalyser.fftSize = 256;
      state.ttsData = new Uint8Array(state.ttsAnalyser.fftSize);
      try {
        const ttsSource = state.audioCtx.createMediaElementSource(state.audioEl);
        ttsSource.connect(state.ttsAnalyser);
        state.ttsAnalyser.connect(state.audioCtx.destination);
      } catch (_) { /* already connected */ }
    }
    if (state.audioCtx.state === "suspended") await state.audioCtx.resume();
  }

  function playChime(notes = [880], gainValue = 0.03) {
    if (!state.audioCtx || DEMO) return;
    try {
      const now = state.audioCtx.currentTime;
      notes.forEach((freq, i) => {
        const osc = state.audioCtx.createOscillator();
        const gain = state.audioCtx.createGain();
        osc.type = "sine";
        osc.frequency.value = freq;
        gain.gain.setValueAtTime(0, now + i * 0.09);
        gain.gain.linearRampToValueAtTime(gainValue, now + i * 0.09 + 0.01);
        gain.gain.exponentialRampToValueAtTime(0.0001, now + i * 0.09 + 0.22);
        osc.connect(gain).connect(state.audioCtx.destination);
        osc.start(now + i * 0.09);
        osc.stop(now + i * 0.09 + 0.24);
      });
    } catch (_) { /* audio is best-effort */ }
  }

  /* ---------------------------------------------------------------- speech */
  let recognition = null;
  let restartTimer = null;
  let startFailures = 0;

  function buildRecognition() {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) throw new Error("Speech recognition unsupported — use Chrome");
    const rec = new SR();
    rec.continuous = true;
    rec.interimResults = true;
    rec.maxAlternatives = 1;
    rec.lang = (state.config && state.config.language) || "en-IN";
    rec.onstart = () => {
      state.recognizing = true;
      state.listening = true;
      state.lastSpeechError = "";
      startFailures = 0;
      clearTimeout(restartTimer);
      if (!state.speaking && !state.busy) setState(state.awake ? "listening" : "idle");
    };
    rec.onend = () => {
      state.recognizing = false;
      scheduleRecognitionRestart(180);
    };
    rec.onerror = (event) => {
      state.recognizing = false;
      state.lastSpeechError = event.error || "unknown";
      if (event.error === "not-allowed" || event.error === "service-not-allowed") {
        state.wantMic = false;
        toast("MIC BLOCKED", "Allow microphone access in Chrome, then reload.", "red");
      } else if (event.error === "network") {
        toast("SPEECH SERVICE", "Chrome's speech service is unreachable. Retrying…", "warn");
        scheduleRecognitionRestart(1400);
      } else {
        scheduleRecognitionRestart(500);
      }
    };
    rec.onresult = onSpeechResult;
    rec.onspeechstart = () => {
      if (!state.speaking) setState("listening");
    };
    return rec;
  }

  function scheduleRecognitionRestart(delay = 350) {
    if (!state.wantMic) return;
    clearTimeout(restartTimer);
    restartTimer = setTimeout(() => {
      if (state.wantMic && !state.recognizing) startRecognition().catch(() => {});
    }, delay);
  }

  async function startRecognition() {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) throw new Error("Speech recognition unsupported — use Chrome");
    state.wantMic = true;
    if (state.recognizing) return;
    if (!recognition) recognition = buildRecognition();
    try {
      recognition.start();
    } catch (_) {
      startFailures += 1;
      if (startFailures > 2) {
        try { recognition.abort(); } catch (_) { /* noop */ }
        recognition = null;
        startFailures = 0;
        scheduleRecognitionRestart(400);
      } else {
        scheduleRecognitionRestart(420);
      }
    }
  }

  function onSpeechResult(event) {
    let interim = "";
    let finalText = "";
    for (let i = event.resultIndex; i < event.results.length; i++) {
      const result = event.results[i];
      if (result.isFinal) finalText += result[0].transcript;
      else interim += result[0].transcript;
    }
    if (interim) {
      el.interim.classList.add("live");
      el.interimText.textContent = interim.trim();
      el.footerHeard.textContent = interim.trim().toUpperCase();
    }
    if (finalText.trim()) {
      el.interim.classList.remove("live");
      el.interimText.textContent = "Processing…";
      const text = finalText.trim();
      const stamp = Date.now();
      if (text.toLowerCase() === state.lastFinal.toLowerCase() && stamp - state.lastFinalAt < 1200) return;
      state.lastFinal = text;
      state.lastFinalAt = stamp;
      handleUtterance(text);
    }
  }

  function handleUtterance(text) {
    const raw = text.trim();
    if (!raw) return;
    if (!state.wantMic) return;
    const lower = raw.toLowerCase();

    if (state.speaking) {
      if (/\b(stop|quiet|hush|shut up|cancel)\b/.test(lower)) {
        stopSpeaking();
        toast("VOICE OUTPUT", "Silenced.", "");
      }
      return;
    }

    const wakeRe = new RegExp(`\\b(?:${state.wakeWords.join("|")})\\b`, "i");
    const hasWake = wakeRe.test(lower);
    const cleaned = raw.replace(new RegExp(wakeRe.source, "gi"), "").replace(/^[\s,.:;-]+/, "").replace(/\s+/g, " ").trim();

    if (state.pending) {
      submitCommand(cleaned || raw, { spoken: true });
      return;
    }

    if (state.awake) {
      submitCommand(cleaned || raw, { spoken: true });
      return;
    }

    if (hasWake) {
      setAwake(true);
      if (!cleaned) {
        addMessage("jarvis", "Yes, sir?", { badge: "VOICE LINK", typing: false });
        speak("Yes, sir?");
        playChime([740, 1040], 0.025);
        return;
      }
      submitCommand(cleaned, { spoken: true });
      return;
    }

    el.footerHeard.textContent = `AMBIENT · ${raw.slice(0, 42).toUpperCase()}`;
  }

  function setListening(on) {
    state.wantMic = on;
    el.listenBtn.setAttribute("aria-pressed", on ? "true" : "false");
    el.listenLabel.textContent = on ? "LISTENING" : "PAUSED";
    el.footerStop.setAttribute("aria-pressed", on ? "true" : "false");
    el.footerStopLabel.textContent = on ? "STOP LISTENING" : "RESUME";
    fetch("/api/listen", { method: "POST", body: JSON.stringify({ on }) }).catch(() => {});
    if (!on) {
      clearTimeout(state.awakeTimer);
      state.awake = false;
      try { if (recognition) recognition.abort(); } catch (_) { /* noop */ }
      stopSpeaking();
      fetch("/api/agent/stop", { method: "POST", body: "{}" }).catch(() => {});
      el.agentBar.hidden = true;
      setState("idle");
      el.interimText.textContent = "Voice link paused — press LISTENING to resume.";
      el.footerHeard.textContent = "PAUSED";
      playChime([520, 390], 0.03);
      return;
    }
    playChime([600, 900], 0.03);
    setState("listening");
    el.interimText.textContent = "Awaiting voice input…";
    el.footerHeard.textContent = "AWAITING WAKE WORD";
    // Start from a clean recognition object so a previous abort can't wedge it.
    recognition = null;
    startFailures = 0;
    setTimeout(() => startRecognition().catch(() => {}), 260);
  }

  function setAwake(value) {
    state.awake = value;
    if (value) {
      state.awakeUntil = Date.now() + ((state.config && state.config.awake_seconds) || 45) * 1000;
      clearTimeout(state.awakeTimer);
      state.awakeTick = setInterval(() => {
        const left = Math.max(0, Math.ceil((state.awakeUntil - Date.now()) / 1000));
        if (!state.pending && !state.speaking && !state.busy) {
          el.footerHeard.textContent = `AWAKE · ${left}s`;
        }
      }, 500);
      state.awakeTimer = setTimeout(() => {
        if (!state.pending && !state.speaking && !state.busy) {
          state.awake = false;
          clearInterval(state.awakeTick);
          setState("idle");
          el.footerHeard.textContent = "AWAITING WAKE WORD";
        }
      }, ((state.config && state.config.awake_seconds) || 45) * 1000);
      if (!state.speaking) setState(state.busy ? "thinking" : "listening");
    } else {
      clearInterval(state.awakeTick);
      if (!state.speaking && !state.busy) setState("idle");
    }
  }

  /* ------------------------------------------------------------------- tts */
  const browserVoice = () => {
    const voices = window.speechSynthesis ? speechSynthesis.getVoices() : [];
    return voices.find((v) => /en-GB/i.test(v.lang) && /male|daniel|arthur|george|ryan/i.test(v.name))
      || voices.find((v) => /en-GB/i.test(v.lang))
      || voices.find((v) => /^en/i.test(v.lang))
      || null;
  };

  async function speak(text) {
    const content = (text || "").trim();
    if (!content || DEMO) return;
    const token = ++state.speechToken;
    stopCurrentAudio();
    state.speaking = true;
    setState("speaking");

    let played = false;
    if (state.capabilities.tts) {
      try {
        state.audioEl.src = `/api/tts?text=${encodeURIComponent(content)}`;
        state.audioEl.volume = 0.92;
        state.audioEl.load();
        played = await playAudio();
      } catch (err) {
        if (token !== state.speechToken) return;
      }
    }

    if (!played && token === state.speechToken) {
      played = await browserSpeak(content);
    }
    if (token !== state.speechToken) return;
    state.speaking = false;
    if (state.engaged) setState(state.awake ? "listening" : "idle");
    if (state.saidWhileSpeaking) {
      const queued = state.saidWhileSpeaking;
      state.saidWhileSpeaking = null;
      setTimeout(() => handleUtterance(queued), 60);
    }
  }

  function playAudio() {
    return new Promise((resolve) => {
      let settled = false;
      let guard = 0;
      const done = (ok) => {
        if (settled) return;
        settled = true;
        clearTimeout(guard);
        state.audioEl.removeEventListener("ended", onEnd);
        state.audioEl.removeEventListener("error", onError);
        resolve(ok);
      };
      const onEnd = () => done(true);
      const onError = () => done(false);
      state.audioEl.addEventListener("ended", onEnd, { once: true });
      state.audioEl.addEventListener("error", onError, { once: true });
      const attempt = state.audioEl.play();
      if (attempt && attempt.catch) {
        attempt.catch(() => done(false));
      }
      guard = setTimeout(() => done(true), 18000);
    });
  }

  function browserSpeak(text) {
    return new Promise((resolve) => {
      if (!window.speechSynthesis) return resolve(false);
      const utterance = new SpeechSynthesisUtterance(text);
      const voice = browserVoice();
      if (voice) utterance.voice = voice;
      utterance.rate = 0.98;
      utterance.pitch = 0.9;
      utterance.volume = 0.95;
      utterance.onend = () => resolve(true);
      utterance.onerror = () => resolve(false);
      speechSynthesis.cancel();
      speechSynthesis.speak(utterance);
    });
  }

  function stopCurrentAudio() {
    try {
      state.audioEl.pause();
      state.audioEl.currentTime = 0;
    } catch (_) { /* noop */ }
    if (window.speechSynthesis) speechSynthesis.cancel();
  }

  function stopSpeaking() {
    state.speechToken++;
    stopCurrentAudio();
    if (state.speaking) {
      state.speaking = false;
      setState(state.awake ? "listening" : "idle");
    }
  }

  /* -------------------------------------------------------------- commands */
  async function submitCommand(text, { spoken = false } = {}) {
    const command = text.trim();
    if (!command) return;
    if (state.busy) { state.queued = { text: command, spoken }; return; }
    state.busy = true;
    setAwake(true);
    setState("thinking");
    addMessage("user", command, { badge: spoken ? "VOICE INPUT" : "MANUAL INPUT" });
    const started = performance.now();
    try {
      const result = await api("/api/command", {
        method: "POST",
        body: JSON.stringify({ text: command }),
        timeout: 60000,
      });
      const latency = Math.round(performance.now() - started);
      el.latency.textContent = `RTT ${latency} MS`;
      handleResult(result, command);
    } catch (err) {
      const message = (err.payload && err.payload.say) || "I've lost the host interface, sir.";
      addMessage("jarvis", message, { badge: "CONNECTION FAULT", badgeKind: "red", detail: err.message });
      speak(message);
    } finally {
      state.busy = false;
      if (state.queued) {
        const next = state.queued;
        state.queued = null;
        setTimeout(() => submitCommand(next.text, { spoken: next.spoken }), 120);
      }
    }
  }

  function handleResult(result, command) {
    const action = result.action || "unknown";
    state.pending = !!result.pending;
    if (state.pending) setAwake(true);

    if (action === "quiet") {
      stopSpeaking();
      addMessage("jarvis", "Voice output silenced, sir.", { badge: "MUTED", badgeKind: "warn" });
      return;
    }
    if (action === "clear_feed") {
      clearFeed(true);
      return;
    }
    if (action === "standby") {
      setTimeout(() => setListening(false), 2200);
    }

    let badge = result.ok ? "EXECUTED" : "FAULT";
    let badgeKind = result.ok ? "green" : "red";
    if (state.pending) { badge = "AWAITING CONFIRMATION"; badgeKind = "warn"; }
    if (action === "chat") { badge = "NEURAL"; badgeKind = ""; }
    if (action === "standby") { badge = "STANDBY"; badgeKind = "warn"; }
    if (action === "help") { badge = "COMMAND MATRIX"; badgeKind = ""; }
    if (action === "screen_look") { badge = "SCREEN VISION"; badgeKind = "green"; }
    if (action === "cua_task") { badge = "AGENT"; badgeKind = ""; if (result.data && result.data.task) agentStart(result.data.task); }
    if (["shutdown", "restart", "suspend", "logout"].includes(action)) {
      badge = "MACHINE CONTROL"; badgeKind = "red"; setState("alert");
    }

    const fullAnswer = result.data && result.data.full;
    addMessage("jarvis", fullAnswer || result.say || "Done, sir.", {
      badge,
      badgeKind,
      detail: result.detail || "",
      sections: result.data && result.data.sections,
      image: result.data && result.data.image,
      showImage: false,
      rich: !!fullAnswer,
      typing: !fullAnswer,
    });
    if (result.data && result.data.path) {
      toast("SCREEN CAPTURE", result.data.path, "");
    }
    if (result.say) speak(result.say);
    if (action === "help") openHelp(result.data && result.data.sections);
    if (state.pending) {
      el.footerHeard.textContent = "AWAITING YES / NO";
    } else {
      setAwake(true);
    }
  }

  /* --------------------------------------------------------------- messages */
  function addMessage(role, text, options = {}) {
    const { badge = "", badgeKind = "", detail = "", sections = null, typing = false, image = "", rich = false, showImage = true } = options;
    const wrap = document.createElement("div");
    wrap.className = `msg ${role === "user" ? "user" : "jarvis"}`;
    if (options.neural) wrap.classList.add("neural");
    state.entryCount++;
    el.feedCount.textContent = `${pad(state.entryCount)} ENTRIES`;

    const avatar = document.createElement("div");
    avatar.className = "msg-avatar";
    avatar.textContent = role === "user" ? "YOU" : "J";

    const content = document.createElement("div");
    const meta = document.createElement("div");
    meta.className = "msg-meta";
    const label = role === "user" ? "YOU" : "J.A.R.V.I.S.";
    meta.innerHTML = `<b>${label}</b><time>${shortTime()}</time>`;
    if (badge) {
      const badgeEl = document.createElement("span");
      badgeEl.className = `badge ${badgeKind}`.trim();
      badgeEl.textContent = badge;
      meta.appendChild(badgeEl);
    }
    const body = document.createElement("div");
    body.className = "msg-body";
    if (typing && role !== "user") body.classList.add("typing");
    content.append(meta, body);
    wrap.append(avatar, content);

    if (image && showImage) {
      const shot = document.createElement("img");
      shot.className = "msg-image";
      shot.src = image;
      shot.alt = "Captured screen";
      shot.loading = "lazy";
      content.appendChild(shot);
    }
    if (detail) {
      const detailEl = document.createElement("div");
      detailEl.className = "msg-detail";
      detailEl.textContent = detail;
      content.appendChild(detailEl);
    }
    if (sections && sections.length) {
      content.appendChild(buildHelpCard(sections));
    }

    el.feed.appendChild(wrap);
    scrollFeed();
    if (rich && /```/.test(text)) {
      renderRichText(body, text);
      body.classList.remove("typing");
    } else if (typing && role !== "user" && !DEMO) {
      typeText(body, text, () => {
        body.classList.remove("typing");
        scrollFeed();
      });
    } else {
      body.textContent = text;
      body.classList.remove("typing");
    }
    return wrap;
  }

  function typeText(node, text, done) {
    let index = 0;
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduced) { node.textContent = text; done(); return; }
    const step = () => {
      index = Math.min(text.length, index + Math.max(2, Math.round(text.length / 70)));
      node.textContent = text.slice(0, index);
      scrollFeed();
      if (index < text.length) setTimeout(step, 16);
      else done();
    };
    step();
  }

  function renderRichText(node, text) {
    const pieces = String(text).split(/```/);
    pieces.forEach((piece, index) => {
      if (index % 2 === 1) {
        const pre = document.createElement("pre");
        pre.className = "code-block";
        pre.textContent = piece.replace(/^[A-Za-z0-9_+-]+\n/, "");
        node.appendChild(pre);
      } else if (piece.trim()) {
        const paragraph = document.createElement("div");
        paragraph.textContent = piece.trim();
        node.appendChild(paragraph);
      }
    });
    scrollFeed();
  }

  function buildHelpCard(sections) {
    const card = document.createElement("div");
    card.className = "help-card";
    sections.forEach(([title, commands]) => {
      const h = document.createElement("h4");
      h.textContent = title;
      const list = document.createElement("ul");
      commands.forEach((command) => {
        const li = document.createElement("li");
        li.textContent = command;
        list.appendChild(li);
      });
      card.append(h, list);
    });
    return card;
  }

  function scrollFeed() {
    el.feed.scrollTop = el.feed.scrollHeight;
  }

  function clearFeed(announce = false) {
    el.feed.innerHTML = "";
    state.entryCount = 0;
    el.feedCount.textContent = "00 ENTRIES";
    if (announce) addMessage("jarvis", "Transcript cleared, sir.", { badge: "SYSTEM", badgeKind: "" });
  }

  /* ---------------------------------------------------------------- support */
  function setState(mode) {
    const labels = {
      idle: state.awake ? "PASSIVE SCAN" : "STANDBY",
      listening: "LISTENING",
      thinking: "PROCESSING",
      speaking: "SPEAKING",
      alert: "EXECUTING",
    };
    document.body.dataset.state = mode;
    const label = labels[mode] || "STANDBY";
    el.stateText.textContent = label;
    el.footerState.textContent = label;
    el.linkChipState.textContent = label;
    if (mode === "idle" && !state.awake) el.footerHeard.textContent = "AWAITING WAKE WORD";
  }

  function updateClock() {
    el.clock.textContent = timeString();
    const now = new Date();
    el.date.textContent = now.toLocaleDateString("en-GB", { weekday: "short", day: "2-digit", month: "short", year: "numeric" }).toUpperCase();
  }

  function updateStats(stats) {
    if (!stats) return;
    state.stats = stats;
    state.lastStatsAt = Date.now();
    setText("v-cpu", `${Math.round(stats.cpu || 0)}%`);
    setWidth("bar-cpu", stats.cpu || 0);
    setText("v-mem", `${Math.round(stats.mem || 0)}%`);
    setWidth("bar-mem", stats.mem || 0);
    setText("sub-mem", `${stats.mem_used_gb ?? "—"} / ${stats.mem_total_gb ?? "—"} GB`);
    setText("v-temp", stats.temp == null ? "—" : `${stats.temp}°C`);
    setWidth("bar-temp", clamp(((stats.temp || 0) / 100) * 100, 0, 100));
    setText("v-net", stats.net_if ? stats.net_if.toUpperCase() : "OFFLINE");
    setText("v-down", `↓ ${formatRate(stats.down)}`);
    setText("v-up", `↑ ${formatRate(stats.up)}`);
    setText("v-batt", stats.battery == null ? "AC" : `${stats.battery}%`);
    setWidth("bar-batt", stats.battery == null ? 100 : stats.battery);
    setText("sub-batt", stats.battery == null ? "MAINS POWER" : String(stats.charging || "").toUpperCase());
    setText("v-vol", stats.muted ? "MUTED" : `${stats.volume ?? "—"}%`);
    setWidth("bar-vol", stats.volume || 0);
    setText("sub-vol", stats.muted ? "OUTPUT MUTED" : "PIPE WIRE · DEFAULT SINK");
    setText("v-host", `${(stats.host || "HOST").toUpperCase()} · ${stats.net_if || "NO LINK"}`);
    setText("v-uptime", `UP ${formatUptime(stats.uptime)}`);
    setText("core-load", `CORE ${pad(Math.round(stats.cpu || 0))}%`);
    setText("core-temp", `TEMP ${stats.temp == null ? "—" : Math.round(stats.temp) + "°"}`);
    sparkline("spark-cpu", (stats.history && stats.history.cpu) || [], false);
    sparkline("spark-net", (stats.history && stats.history.down) || [], true);
  }

  function setText(id, value) {
    const node = $(id);
    if (node && node.textContent !== String(value)) node.textContent = value;
  }
  function setWidth(id, value) {
    const node = $(id);
    if (node) node.style.width = `${clamp(Number(value) || 0, 0, 100)}%`;
  }
  function formatRate(value) {
    const n = Number(value) || 0;
    if (n >= 1024) return `${(n / 1024).toFixed(1)} MB/s`;
    return `${n.toFixed(n < 10 ? 1 : 0)} KB/s`;
  }
  function formatUptime(seconds) {
    const s = Number(seconds) || 0;
    const h = Math.floor(s / 3600);
    const m = Math.floor((s % 3600) / 60);
    if (h > 47) return `${Math.floor(h / 24)}D ${h % 24}H`;
    return `${h}H ${pad(m)}M`;
  }
  function sparkline(id, values, fillZero) {
    const node = $(id);
    if (!node) return;
    const data = values.slice(-36);
    if (data.length < 2) { node.setAttribute("points", ""); return; }
    const max = Math.max(...data, fillZero ? 1 : 5);
    const step = 100 / (data.length - 1);
    const points = data.map((v, i) => `${(i * step).toFixed(2)},${(23 - clamp((v / max) * 21, 0, 21)).toFixed(2)}`).join(" ");
    node.setAttribute("points", points);
  }

  function appendLog(entry, animate = true) {
    const node = document.createElement("div");
    node.className = "log-entry";
    if (!animate) node.style.animation = "none";
    const timestamp = new Date((entry.at || Date.now() / 1000) * 1000).toLocaleTimeString("en-GB", { hour12: false });
    let tagClass = "";
    let tag = entry.kind || "SYS";
    if (entry.kind === "YOU") tagClass = "red";
    if (entry.kind === "SYS" || entry.level === "ok") tagClass = "green";
    if (entry.level === "warn") tagClass = "warn";
    if (entry.kind === "ACT" || entry.kind === "NEURAL") tagClass = "";
    node.innerHTML = `<time>${timestamp}</time><span class="tag ${tagClass}">${escapeHtml(tag)}</span><span>${escapeHtml(entry.message || "")}</span>`;
    el.logList.appendChild(node);
    while (el.logList.children.length > 60) el.logList.firstElementChild.remove();
    el.logList.scrollTop = el.logList.scrollHeight;
  }

  async function pollStatus() {
    try {
      const data = await api("/api/state", { timeout: 6000 });
      applyConfig(data);
    } catch (_) { /* SSE will keep trying */ }
  }

  /* ------------------------------------------------------------------- sse */
  let eventSource = null;
  function connectSSE() {
    if (eventSource) eventSource.close();
    eventSource = new EventSource("/api/events");
    eventSource.addEventListener("hello", () => {
      el.logList.innerHTML = "";
      el.latency.textContent = "RTT —";
    });
    eventSource.addEventListener("stats", (event) => {
      try { updateStats(JSON.parse(event.data)); } catch (_) { /* ignore */ }
    });
    eventSource.addEventListener("log", (event) => {
      try { appendLog(JSON.parse(event.data)); } catch (_) { /* ignore */ }
    });
    eventSource.addEventListener("agent", (event) => {
      let data = {};
      try { data = JSON.parse(event.data); } catch (_) { return; }
      handleAgent(data);
    });
    eventSource.addEventListener("timer_fired", (event) => {
      let data = {};
      try { data = JSON.parse(event.data); } catch (_) { /* ignore */ }
      const line = data.label ? `Sir, your timer for ${data.label} has elapsed.` : "Sir, your timer has elapsed.";
      addMessage("jarvis", line, { badge: "TIMER", badgeKind: "warn" });
      speak(line);
      playChime([520, 780, 1040], 0.05);
      toast("TIMER", data.label || "Timer elapsed", "warn");
      if (data.seconds) setState("listening");
    });
    eventSource.onerror = () => {
      el.logList.style.opacity = "0.6";
      setTimeout(() => { el.logList.style.opacity = ""; }, 1200);
    };
  }

  /* ---------------------------------------------------------- visualizer */
  let raf = 0;
  let wavCtx = null;

  function initVisuals() {
    const ticks = $("ticks");
    if (ticks) {
      const ns = "http://www.w3.org/2000/svg";
      for (let i = 0; i < 60; i++) {
        const angle = (i / 60) * Math.PI * 2;
        const major = i % 5 === 0;
        const r1 = 182;
        const r2 = major ? 191 : 186;
        const line = document.createElementNS(ns, "line");
        line.setAttribute("x1", (200 + Math.cos(angle) * r1).toFixed(2));
        line.setAttribute("y1", (200 + Math.sin(angle) * r1).toFixed(2));
        line.setAttribute("x2", (200 + Math.cos(angle) * r2).toFixed(2));
        line.setAttribute("y2", (200 + Math.sin(angle) * r2).toFixed(2));
        if (major) line.classList.add("major");
        ticks.appendChild(line);
      }
    }
    const canvas = el.waveform;
    wavCtx = canvas.getContext("2d");
    resizeWave();
    window.addEventListener("resize", resizeWave);
    drawWave();
  }

  function resizeWave() {
    const canvas = el.waveform;
    const ratio = Math.min(window.devicePixelRatio || 1, 2);
    const rect = canvas.getBoundingClientRect();
    canvas.width = Math.max(1, Math.round(rect.width * ratio));
    canvas.height = Math.max(1, Math.round(rect.height * ratio));
    wavCtx.setTransform(ratio, 0, 0, ratio, 0, 0);
  }

  function rms(data) {
    if (!data || !data.length) return 0;
    let sum = 0;
    for (let i = 0; i < data.length; i++) {
      const v = (data[i] - 128) / 128;
      sum += v * v;
    }
    return Math.sqrt(sum / data.length);
  }

  function drawWave() {
    raf = requestAnimationFrame(drawWave);
    if (!wavCtx) return;
    const canvas = el.waveform;
    const width = canvas.clientWidth;
    const height = canvas.clientHeight;
    if (!width || !height) return;
    wavCtx.clearRect(0, 0, width, height);
    const t = performance.now() / 1000;

    let micLevel = 0;
    if (state.micAnalyser && state.micData) {
      state.micAnalyser.getByteTimeDomainData(state.micData);
      micLevel = rms(state.micData);
    }
    let ttsLevel = 0;
    if (state.speaking && state.ttsAnalyser && state.ttsData) {
      state.ttsAnalyser.getByteTimeDomainData(state.ttsData);
      ttsLevel = rms(state.ttsData);
    }
    const active = state.speaking ? ttsLevel : micLevel;
    const level = Math.max(active, state.engaged ? 0.015 : 0);
    document.body.style.setProperty("--level", level.toFixed(3));
    if (el.meterFill) el.meterFill.style.width = `${clamp(level * 420, 0, 100)}%`;
    if (el.meterDb) el.meterDb.textContent = level > 0.005 ? `${(20 * Math.log10(level)).toFixed(0)} DB` : "--";

    const bars = 72;
    const gap = 2;
    const barWidth = Math.max(1, width / bars - gap);
    const mid = height / 2;
    for (let i = 0; i < bars; i++) {
      const x = i * (barWidth + gap);
      const norm = Math.abs((i - bars / 2) / (bars / 2));
      const envelope = Math.pow(1 - norm, 1.6);
      let h;
      if (state.speaking) {
        h = envelope * (4 + level * 240) * (0.55 + 0.45 * Math.abs(Math.sin(t * 8 + i * 0.55)));
      } else if (state.listening && state.engaged) {
        h = envelope * (3 + level * 190) * (0.5 + 0.5 * Math.sin(t * 2.2 + i * 0.28));
        h += envelope * 2;
      } else {
        h = envelope * (2.5 + Math.sin(t * 1.2 + i * 0.2) * 1.5);
      }
      h = clamp(h, 1, height - 2);
      const gradient = wavCtx.createLinearGradient(0, mid - h, 0, mid + h);
      gradient.addColorStop(0, "rgba(255, 45, 75, .85)");
      gradient.addColorStop(0.45, "rgba(42, 190, 255, .9)");
      gradient.addColorStop(1, "rgba(12, 88, 142, .55)");
      wavCtx.fillStyle = gradient;
      wavCtx.fillRect(x, mid - h / 2, barWidth, h);
    }
    wavCtx.strokeStyle = "rgba(127, 230, 255, .16)";
    wavCtx.beginPath();
    wavCtx.moveTo(0, mid);
    wavCtx.lineTo(width, mid);
    wavCtx.stroke();
  }

  /* ----------------------------------------------------------------- agent */
  function agentStart(task) {
    el.agentTrace.innerHTML = "";
    el.agentTask.textContent = task;
    el.agentStep.textContent = "STEP 0";
    el.agentBar.hidden = false;
    setState("thinking");
    const head = document.createElement("li");
    head.className = "ok";
    head.innerHTML = `<b>00</b><span class="verb">observe</span><span>reading the window</span>`;
    el.agentTrace.appendChild(head);
  }

  function agentRow(step, verb, detail, failure) {
    const row = document.createElement("li");
    row.className = failure ? "fail" : "ok";
    row.innerHTML = `<b>${String(step).padStart(2, "0")}</b><span class="verb">${escapeHtml(verb)}</span><span>${escapeHtml(detail)}</span>`;
    el.agentTrace.appendChild(row);
    el.agentStep.textContent = `STEP ${step}`;
    el.agentBar.scrollTop = el.agentBar.scrollHeight;
  }

  function handleAgent(data) {
    const kind = data.kind;
    if (kind === "start") { agentStart(data.task || "working"); return; }
    if (kind === "observe") {
      if (el.agentBar.hidden) agentStart(data.say || "working");
      el.agentTask.textContent = `${data.app}${data.title ? " — " + data.title : ""}`;
      return;
    }
    if (kind === "act") {
      agentRow(data.step, data.action, data.ok ? (data.label || "done") : (data.error || "refused"), !data.ok);
      return;
    }
    if (kind === "done" || kind === "error") {
      const say = data.say || "Finished, sir.";
      addMessage("jarvis", say, {
        badge: data.cancelled ? "AGENT STOPPED" : kind === "error" ? "AGENT FAULT" : "AGENT DONE",
        badgeKind: kind === "error" ? "red" : data.cancelled ? "warn" : "green",
        detail: data.steps ? `${data.steps} step${data.steps === 1 ? "" : "s"} executed` : "",
      });
      speak(say);
      setTimeout(() => { el.agentBar.hidden = true; }, 4500);
      setState("listening");
    }
  }

  /* ------------------------------------------------------------------- ui */
  function openHelp(sections) {
    const data = sections || HELP_FALLBACK;
    el.helpBody.innerHTML = "";
    data.forEach(([title, commands]) => {
      const section = document.createElement("div");
      section.className = "help-section";
      const h = document.createElement("h3");
      h.textContent = title;
      const list = document.createElement("ul");
      commands.forEach((command) => {
        const li = document.createElement("li");
        li.textContent = command;
        list.appendChild(li);
      });
      section.append(h, list);
      el.helpBody.appendChild(section);
    });
    el.helpModal.hidden = false;
  }

  const HELP_FALLBACK = [
    ["APPS & WEB", ["open chrome", "open terminal", "open youtube", "search the web for …", "play … on youtube", "close spotify"]],
    ["SYSTEM", ["volume up", "set volume to 40", "mute", "lock the screen", "battery status", "what's my CPU usage", "take a screenshot"]],
    ["TIME & UTILITY", ["set a timer for five minutes", "remember that …", "read my notes", "what's the weather in Mumbai", "calculate 128 times 4"]],
    ["MACHINE", ["suspend", "restart", "shut down", "turn off wifi", "do not disturb", "run command neofetch"]],
    ["SCREEN & CODE", ["look at my screen", "what's on my screen", "fix this error", "review my code", "vibe coding"]],
    ["VOICE", ["Jarvis, wake up", "quiet", "stop listening"]],
    ["AGENT (ACTS FOR YOU)", ["click 7 in the calculator", "type hello in the search box", "press ctrl+s", "go to github.com and search cua", "stop the agent"]],
    ["HINGLISH", ["chrome kholo", "volume badha do", "screen dekho", "pc band karo"]],
  ];

  function closeHelp() { el.helpModal.hidden = true; }

  function toggleManual(force) {
    const show = force ?? el.manualField.hidden;
    el.manualField.hidden = !show;
    if (show) el.manualInput.focus();
  }

  /* --------------------------------------------------------------- binds */
  el.engage.addEventListener("click", engage);
  $("screen-btn").addEventListener("click", () => submitCommand("look at my screen", { spoken: false }));
  el.listenBtn.addEventListener("click", () => setListening(!state.wantMic));
  el.footerStop.addEventListener("click", () => setListening(!state.wantMic));
  el.agentStop.addEventListener("click", () => {
    fetch("/api/agent/stop", { method: "POST", body: "{}" }).catch(() => {});
    el.agentStep.textContent = "STOPPING";
  });
  $("help-btn").addEventListener("click", () => openHelp());
  $("clear-btn").addEventListener("click", () => clearFeed(true));
  el.helpModal.addEventListener("click", (event) => {
    if (event.target.hasAttribute("data-close")) closeHelp();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") { closeHelp(); toggleManual(false); }
    if (event.key === "/" && document.activeElement !== el.manualInput) {
      event.preventDefault();
      toggleManual(true);
    }
  });
  el.manualToggle.addEventListener("click", () => toggleManual());
  el.manualForm.addEventListener("submit", (event) => {
    event.preventDefault();
    const value = el.manualInput.value.trim();
    if (!value) return;
    el.manualInput.value = "";
    submitCommand(value, { spoken: false });
  });
  document.querySelectorAll(".chip").forEach((chip) => {
    chip.addEventListener("click", () => submitCommand(chip.dataset.cmd, { spoken: false }));
  });
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden && state.engaged && state.wantMic && !state.recognizing && !state.speaking) {
      startRecognition().catch(() => {});
    }
  });
  window.addEventListener("beforeunload", () => {
    state.wantMic = false;
    if (recognition) try { recognition.stop(); } catch (_) { /* noop */ }
    if (eventSource) eventSource.close();
  });

  window.__jarvis = {
    get snapshot() {
      return {
        engaged: state.engaged, awake: state.awake, speaking: state.speaking,
        recognizing: state.recognizing, wantMic: state.wantMic,
        lastSpeechError: state.lastSpeechError, lastFinal: state.lastFinal,
        busy: state.busy, state: document.body.dataset.state,
      };
    },
    say: (text) => handleUtterance(text),
  };

  /* --------------------------------------------------------------- start */
  updateClock();
  setInterval(updateClock, 1000);
  initVisuals();
  connectSSE();
  runBoot();
})();
