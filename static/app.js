(() => {
  "use strict";

  const THEME_STORAGE_KEY = "exclaim_download_theme";
  const HISTORY_STORAGE_KEY = "exclaim_download_history_v1";

  const state = {
    appInfo: null,
    media: null,
    mode: "video",
    selectedHeight: null,
    selectedContainer: "mp4",
    selectedAudioFormat: "mp3",
    selectedAudioBitrate: 192,
    activeJobId: null,
    eventSource: null,
    pollTimer: null,
    autoDownloadedJobs: new Set(),
    updateInfo: null,
    history: loadLocalHistory(),
  };

  const els = {
    runtimeMiniStatus: document.getElementById("runtimeMiniStatus"),
    updatePill: document.getElementById("updatePill"),
    updatePillText: document.getElementById("updatePillText"),
    themeToggleBtn: document.getElementById("themeToggleBtn"),
    openSettingsBtn: document.getElementById("openSettingsBtn"),

    analyzeForm: document.getElementById("analyzeForm"),
    urlInput: document.getElementById("urlInput"),
    clearBtn: document.getElementById("clearBtn"),
    pasteBtn: document.getElementById("pasteBtn"),
    analyzeBtn: document.getElementById("analyzeBtn"),
    errorBanner: document.getElementById("errorBanner"),
    errorMessage: document.getElementById("errorMessage"),

    mediaSection: document.getElementById("mediaSection"),
    mediaThumb: document.getElementById("mediaThumb"),
    thumbFallback: document.getElementById("thumbFallback"),
    mediaDuration: document.getElementById("mediaDuration"),
    mediaLiveBadge: document.getElementById("mediaLiveBadge"),
    mediaPlatform: document.getElementById("mediaPlatform"),
    mediaMaxRes: document.getElementById("mediaMaxRes"),
    mediaSourceAudio: document.getElementById("mediaSourceAudio"),
    mediaSubtitles: document.getElementById("mediaSubtitles"),
    openSourceBtn: document.getElementById("openSourceBtn"),
    mediaTitle: document.getElementById("mediaTitle"),
    mediaUploader: document.getElementById("mediaUploader"),
    mediaDate: document.getElementById("mediaDate"),
    mediaViews: document.getElementById("mediaViews"),
    mediaLikes: document.getElementById("mediaLikes"),

    detailsToggleBtn: document.getElementById("detailsToggleBtn"),
    detailsPanel: document.getElementById("detailsPanel"),
    specsGrid: document.getElementById("specsGrid"),
    descriptionBox: document.getElementById("descriptionBox"),
    mediaDescription: document.getElementById("mediaDescription"),

    modeSegmented: document.getElementById("modeSegmented"),
    tabVideo: document.getElementById("tabVideo"),
    tabAudio: document.getElementById("tabAudio"),
    videoPanel: document.getElementById("videoPanel"),
    audioPanel: document.getElementById("audioPanel"),
    videoQualityGrid: document.getElementById("videoQualityGrid"),
    noVideoNote: document.getElementById("noVideoNote"),
    containerPills: document.getElementById("containerPills"),
    audioFormatGrid: document.getElementById("audioFormatGrid"),
    audioBitrateGrid: document.getElementById("audioBitrateGrid"),
    losslessNote: document.getElementById("losslessNote"),

    folderPill: document.getElementById("folderPill"),
    folderPathText: document.getElementById("folderPathText"),
    quickFolderBtn: document.getElementById("quickFolderBtn"),
    embedMetadata: document.getElementById("embedMetadata"),
    startDownloadBtn: document.getElementById("startDownloadBtn"),
    downloadBtnText: document.getElementById("downloadBtnText"),

    progressSection: document.getElementById("progressSection"),
    progressBadge: document.getElementById("progressBadge"),
    progressTitle: document.getElementById("progressTitle"),
    progressMeta: document.getElementById("progressMeta"),
    progressPercent: document.getElementById("progressPercent"),
    progressTrack: document.getElementById("progressTrack"),
    progressFill: document.getElementById("progressFill"),
    progressStage: document.getElementById("progressStage"),
    progressSpeed: document.getElementById("progressSpeed"),
    progressEta: document.getElementById("progressEta"),
    progressSize: document.getElementById("progressSize"),
    cancelJobBtn: document.getElementById("cancelJobBtn"),
    openSavedFolderBtn: document.getElementById("openSavedFolderBtn"),
    openSavedFileBtn: document.getElementById("openSavedFileBtn"),
    saveFileBtn: document.getElementById("saveFileBtn"),
    savedPathLine: document.getElementById("savedPathLine"),

    historySection: document.getElementById("historySection"),
    historySub: document.getElementById("historySub"),
    historyList: document.getElementById("historyList"),
    clearHistoryBtn: document.getElementById("clearHistoryBtn"),
    footerCredit: document.getElementById("footerCredit"),

    settingsModal: document.getElementById("settingsModal"),
    closeSettingsBtn: document.getElementById("closeSettingsBtn"),
    modalVersionSub: document.getElementById("modalVersionSub"),
    modalFolderSection: document.getElementById("modalFolderSection"),
    modalFolderPath: document.getElementById("modalFolderPath"),
    modalOpenFolderBtn: document.getElementById("modalOpenFolderBtn"),
    modalChooseFolderBtn: document.getElementById("modalChooseFolderBtn"),
    updateEngineBtn: document.getElementById("updateEngineBtn"),
    modalToolsGrid: document.getElementById("modalToolsGrid"),
    engineFeedback: document.getElementById("engineFeedback"),
    restartAppBtn: document.getElementById("restartAppBtn"),
    checkAppUpdateBtn: document.getElementById("checkAppUpdateBtn"),
    appUpdateText: document.getElementById("appUpdateText"),
    appReleaseNotes: document.getElementById("appReleaseNotes"),
    installAppUpdateBtn: document.getElementById("installAppUpdateBtn"),
    openReleasePageLink: document.getElementById("openReleasePageLink"),
  };

  function hasDesktopBridge() {
    return Boolean(window.pywebview && window.pywebview.api);
  }

  function isDesktopMode() {
    return Boolean((state.appInfo && state.appInfo.desktop_mode) || hasDesktopBridge());
  }

  function getCurrentTheme() {
    return document.documentElement.getAttribute("data-theme") === "light" ? "light" : "dark";
  }

  function applyTheme(theme, persistRemote) {
    const normalized = theme === "light" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", normalized);
    try {
      localStorage.setItem(THEME_STORAGE_KEY, normalized);
    } catch {
      // Ignore storage error
    }
    if (hasDesktopBridge() && typeof window.pywebview.api.set_window_theme === "function") {
      window.pywebview.api.set_window_theme(normalized).catch(() => {});
    }
    if (persistRemote) {
      fetch("/api/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ theme: normalized }),
      }).catch(() => {});
    }
  }

  function loadLocalHistory() {
    try {
      const raw = localStorage.getItem(HISTORY_STORAGE_KEY);
      const parsed = raw ? JSON.parse(raw) : [];
      return Array.isArray(parsed) ? parsed.slice(0, 15) : [];
    } catch {
      return [];
    }
  }

  function saveLocalHistory() {
    try {
      localStorage.setItem(HISTORY_STORAGE_KEY, JSON.stringify(state.history.slice(0, 15)));
    } catch {
      // Ignore quota errors
    }
  }

  function formatBytes(bytes) {
    if (!bytes || bytes <= 0) return null;
    const units = ["B", "KB", "MB", "GB"];
    let val = bytes;
    let idx = 0;
    while (val >= 1024 && idx < units.length - 1) {
      val /= 1024;
      idx += 1;
    }
    return `${val >= 100 || idx === 0 ? val.toFixed(0) : val.toFixed(1)} ${units[idx]}`;
  }

  function formatSpeed(bytesPerSec) {
    if (!bytesPerSec || bytesPerSec <= 0) return "";
    return `${formatBytes(bytesPerSec)}/s`;
  }

  function formatEta(seconds) {
    if (seconds === null || seconds === undefined || seconds < 0) return "";
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    if (mins > 0) return `ETA ${mins}m ${secs}s`;
    return `ETA ${secs}s`;
  }

  function formatCount(count, suffix) {
    if (count === null || count === undefined || count < 0) return null;
    return `${new Intl.NumberFormat("es").format(count)} ${suffix}`;
  }

  function showError(msg) {
    els.errorMessage.textContent = msg;
    els.errorBanner.hidden = false;
  }

  function clearError() {
    els.errorBanner.hidden = true;
    els.errorMessage.textContent = "";
  }

  function setAnalyzing(loading) {
    els.analyzeBtn.disabled = loading;
    els.analyzeBtn.classList.toggle("is-loading", loading);
    const label = els.analyzeBtn.querySelector(".btn-label");
    if (label) {
      label.textContent = loading ? "Analizando..." : "Analizar";
    }
  }

  async function loadAppInfo() {
    try {
      const resp = await fetch("/api/app-info");
      if (!resp.ok) return;
      const info = await resp.json();
      state.appInfo = info;

      const version = info.version || "1.0.0";
      const developer = info.developer || "Juan Corporation";
      els.footerCredit.textContent = `${info.name || "!Download"} v${version} · ${developer}`;
      els.modalVersionSub.textContent = `v${version} · ${developer}`;

      updateFolderDisplays(info.download_dir);
      renderTools(info.tools || {});

      if (info.desktop_mode) {
        els.historySub.textContent = "Historial reciente guardado directamente en tu carpeta.";
      } else {
        els.historySub.textContent = "Los archivos temporales permanecen disponibles 30 minutos.";
      }

      if (info.settings && info.settings.theme && !localStorage.getItem(THEME_STORAGE_KEY)) {
        applyTheme(info.settings.theme, false);
      } else {
        applyTheme(getCurrentTheme(), false);
      }
    } catch {
      // Ignore silent initialization error
    }
  }

  function updateFolderDisplays(dirPath) {
    const clean = dirPath || "";
    const desktop = isDesktopMode();
    els.folderPill.hidden = !desktop || !clean;
    els.modalFolderSection.hidden = !desktop || !clean;
    if (clean) {
      const parts = clean.split(/[\\/]/).filter(Boolean);
      const shortName = parts.length > 0 ? parts[parts.length - 1] : clean;
      els.folderPathText.textContent = `Guardar en: ${shortName}`;
      els.folderPill.title = clean;
      els.modalFolderPath.textContent = clean;
    }
  }

  function formatToolVersion(key, raw) {
    if (!raw) return "Disponible";
    const text = String(raw).trim();
    if (key === "ffmpeg" || key === "ffprobe") {
      const nMatch = text.match(/\b(N-\d+)(?:-[a-z0-9]+)?-(\d{4})(\d{2})(\d{2})\b/i);
      if (nMatch) {
        return `${nMatch[1]} (${nMatch[2]}-${nMatch[3]}-${nMatch[4]})`;
      }
      const verMatch = text.match(/version\s+([^\s]+)/i);
      if (verMatch) return verMatch[1];
    }
    if (key === "deno") {
      const denoMatch = text.match(/deno\s+([\d.]+)/i);
      if (denoMatch) return `v${denoMatch[1]}`;
    }
    if (key === "yt_dlp" && /^\d/.test(text)) {
      return `v${text}`;
    }
    return text;
  }

  function renderTools(tools) {
    els.runtimeMiniStatus.querySelectorAll(".engine-dot").forEach((dot) => {
      const key = dot.dataset.tool;
      const item = tools[key];
      dot.classList.remove("is-ready", "is-missing");
      if (item && item.available) {
        dot.classList.add("is-ready");
        dot.title = item.version ? `${key}: ${formatToolVersion(key, item.version)}` : `${key}: listo`;
      } else {
        dot.classList.add("is-missing");
        dot.title = `${key}: no detectado`;
      }
    });

    const labels = [
      ["yt_dlp", "yt-dlp"],
      ["ffmpeg", "FFmpeg"],
      ["ffprobe", "FFprobe"],
      ["deno", "Deno"],
    ];
    els.modalToolsGrid.innerHTML = "";
    labels.forEach(([key, label]) => {
      const item = tools[key] || {};
      const box = document.createElement("div");
      box.className = "tool-box";

      const top = document.createElement("div");
      top.className = "tool-box-top";
      const title = document.createElement("span");
      title.textContent = label;
      const dot = document.createElement("span");
      dot.className = `engine-dot ${item.available ? "is-ready" : "is-missing"}`;
      top.append(title, dot);

      const ver = document.createElement("div");
      ver.className = "tool-box-ver";
      if (item.available) {
        const suffix = item.using_override ? " (Actualizado)" : "";
        ver.textContent = `${formatToolVersion(key, item.version)}${suffix}`;
        ver.title = item.version || "";
      } else {
        ver.textContent = "No detectado";
      }

      box.append(top, ver);
      els.modalToolsGrid.appendChild(box);
    });
  }

  async function checkUpdatesSilent() {
    try {
      const resp = await fetch("/api/updates/check");
      if (!resp.ok) return;
      const data = await resp.json();
      renderUpdateStatus(data);
    } catch {
      // Silent background check
    }
  }

  function renderUpdateStatus(data) {
    state.updateInfo = data;
    if (data && data.update_available && data.latest_version) {
      els.updatePillText.textContent = `v${data.latest_version} disponible`;
      els.updatePill.hidden = false;
    } else {
      els.updatePill.hidden = true;
    }

    if (!data) return;
    els.appUpdateText.textContent = data.message || "Sin información.";

    if (data.release_notes) {
      els.appReleaseNotes.textContent = data.release_notes;
      els.appReleaseNotes.hidden = false;
    } else {
      els.appReleaseNotes.hidden = true;
    }

    if (data.release_url) {
      els.openReleasePageLink.href = data.release_url;
      els.openReleasePageLink.hidden = false;
    } else {
      els.openReleasePageLink.hidden = true;
    }

    const selfUpdateSupported = state.appInfo
      ? (typeof state.appInfo.can_self_update === "boolean"
          ? state.appInfo.can_self_update
          : Boolean(state.appInfo.frozen))
      : false;
    const canSelfUpdate = Boolean(
      data.update_available &&
      data.asset_url &&
      data.asset_name &&
      selfUpdateSupported
    );
    els.installAppUpdateBtn.hidden = !canSelfUpdate;
  }

  function updateClearButton() {
    els.clearBtn.hidden = !els.urlInput.value.trim();
  }

  async function analyzeUrl(urlValue) {
    const url = (urlValue || els.urlInput.value).trim();
    clearError();
    if (!url) {
      showError("Pega un enlace de video o audio para analizarlo.");
      els.urlInput.focus();
      return;
    }

    setAnalyzing(true);
    try {
      const resp = await fetch("/api/info", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url }),
      });
      const payload = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        throw new Error(payload.detail || "No se pudo analizar ese enlace.");
      }

      state.media = payload;
      pickDefaultSelections(payload);
      renderMediaSection(payload);
    } catch (err) {
      showError(err instanceof Error ? err.message : "Error al analizar el enlace.");
    } finally {
      setAnalyzing(false);
    }
  }

  function pickDefaultSelections(media) {
    const videoOptions = media.video_options || [];
    if (videoOptions.length > 0) {
      state.mode = "video";
      const fullHd = videoOptions.find((opt) => opt.height === 1080);
      state.selectedHeight = (fullHd || videoOptions[0]).height;
    } else {
      state.mode = "audio";
      state.selectedHeight = null;
    }
    state.selectedContainer = "mp4";
    state.selectedAudioFormat = "mp3";
    state.selectedAudioBitrate = 192;
  }

  function renderMediaSection(media) {
    els.mediaSection.hidden = false;
    els.mediaTitle.textContent = media.title || "Archivo multimedia";
    els.mediaPlatform.textContent = media.platform || "Web";

    const videoOptions = media.video_options || [];
    if (videoOptions.length > 0 && videoOptions[0].quality_tag) {
      els.mediaMaxRes.textContent = `Máx. ${videoOptions[0].quality_tag}`;
      els.mediaMaxRes.hidden = false;
    } else {
      els.mediaMaxRes.hidden = true;
    }

    if (media.source_audio_abr || media.source_audio_codec) {
      const audioParts = [];
      if (media.source_audio_codec) audioParts.push(media.source_audio_codec);
      if (media.source_audio_abr) audioParts.push(`${media.source_audio_abr} kbps`);
      els.mediaSourceAudio.textContent = `Audio ${audioParts.join(" · ")}`;
      els.mediaSourceAudio.hidden = false;
    } else {
      els.mediaSourceAudio.hidden = true;
    }

    const subs = media.subtitle_languages || [];
    if (subs.length > 0) {
      els.mediaSubtitles.textContent = `${subs.length} subtítulo${subs.length === 1 ? "" : "s"}`;
      els.mediaSubtitles.title = subs.join(", ");
      els.mediaSubtitles.hidden = false;
    } else {
      els.mediaSubtitles.hidden = true;
    }

    els.openSourceBtn.hidden = !(media.webpage_url || media.url);
    els.mediaLiveBadge.hidden = !media.is_live;

    if (media.uploader) {
      els.mediaUploader.textContent = media.uploader;
      els.mediaUploader.hidden = false;
    } else {
      els.mediaUploader.hidden = true;
    }

    if (media.upload_date) {
      els.mediaDate.textContent = `Publicado el ${media.upload_date}`;
      els.mediaDate.hidden = false;
    } else {
      els.mediaDate.hidden = true;
    }

    const viewsText = formatCount(media.view_count, "vistas");
    if (viewsText) {
      els.mediaViews.textContent = viewsText;
      els.mediaViews.hidden = false;
    } else {
      els.mediaViews.hidden = true;
    }

    const likesText = formatCount(media.like_count, "me gusta");
    if (likesText) {
      els.mediaLikes.textContent = likesText;
      els.mediaLikes.hidden = false;
    } else {
      els.mediaLikes.hidden = true;
    }

    if (media.duration_text) {
      els.mediaDuration.textContent = media.duration_text;
      els.mediaDuration.hidden = false;
    } else {
      els.mediaDuration.hidden = true;
    }

    if (media.thumbnail) {
      els.mediaThumb.hidden = true;
      els.thumbFallback.hidden = false;
      els.mediaThumb.onload = () => {
        els.mediaThumb.hidden = false;
        els.thumbFallback.hidden = true;
      };
      els.mediaThumb.onerror = () => {
        els.mediaThumb.hidden = true;
        els.thumbFallback.hidden = false;
      };
      els.mediaThumb.src = `/api/thumbnail?url=${encodeURIComponent(media.thumbnail)}`;
    } else {
      els.mediaThumb.removeAttribute("src");
      els.mediaThumb.hidden = true;
      els.thumbFallback.hidden = false;
    }

    if (media.description) {
      els.mediaDescription.textContent = media.description;
      els.descriptionBox.hidden = false;
    } else {
      els.descriptionBox.hidden = true;
    }

    renderModeTabs();
    renderVideoOptions();
    renderAudioOptions();
    renderDetailedSpecs();
    updateDownloadCta();
  }

  function renderDetailedSpecs() {
    if (!state.media) return;
    const media = state.media;
    const cells = [];

    if (state.mode === "video") {
      const selected = (media.video_options || []).find((o) => o.height === state.selectedHeight) || (media.video_options || [])[0];
      if (selected) {
        const res = selected.width && selected.height ? `${selected.width} × ${selected.height} px` : selected.label;
        cells.push(["Resolución elegida", res]);
        if (selected.fps) cells.push(["Fotogramas", `${selected.fps} fps`]);
        if (selected.vcodec) cells.push(["Códec de video", selected.vcodec]);
        cells.push(["Rango dinámico", selected.dynamic_range || "SDR"]);
        if (selected.tbr) cells.push(["Bitrate de video", `~${selected.tbr} kbps`]);
        const est = formatBytes(selected.filesize_approx);
        if (est) cells.push(["Tamaño estimado", `~${est}`]);
      }
      cells.push(["Contenedor", state.selectedContainer.toUpperCase()]);
    } else {
      const fmtObj = (media.audio_formats || []).find((f) => f.format === state.selectedAudioFormat);
      const isLossless = Boolean(fmtObj && fmtObj.lossless);
      cells.push(["Formato de salida", state.selectedAudioFormat.toUpperCase()]);
      cells.push(["Calidad elegida", isLossless ? "Sin pérdida (Lossless)" : `${state.selectedAudioBitrate} kbps`]);
      if (!isLossless) {
        const brObj = (media.audio_bitrates || []).find((b) => b.bitrate === state.selectedAudioBitrate);
        const est = formatBytes(brObj && brObj.estimated_bytes);
        if (est) cells.push(["Tamaño estimado", `~${est}`]);
      }
    }

    if (media.source_audio_codec || media.source_audio_abr) {
      const parts = [];
      if (media.source_audio_codec) parts.push(media.source_audio_codec);
      if (media.source_audio_abr) parts.push(`${media.source_audio_abr} kbps`);
      cells.push(["Audio origen", parts.join(" · ")]);
    }
    if (media.duration_text) {
      cells.push(["Duración", media.duration_text]);
    }
    if ((media.subtitle_languages || []).length > 0) {
      cells.push(["Subtítulos", media.subtitle_languages.slice(0, 8).join(", ")]);
    }

    els.specsGrid.innerHTML = "";
    cells.forEach(([label, value]) => {
      const cell = document.createElement("div");
      cell.className = "spec-cell";
      const lbl = document.createElement("span");
      lbl.className = "spec-label";
      lbl.textContent = label;
      const val = document.createElement("span");
      val.className = "spec-value";
      val.textContent = value;
      cell.append(lbl, val);
      els.specsGrid.appendChild(cell);
    });
  }

  function renderModeTabs() {
    const isVideo = state.mode === "video";
    els.modeSegmented.classList.toggle("is-audio", !isVideo);
    els.tabVideo.classList.toggle("is-active", isVideo);
    els.tabVideo.setAttribute("aria-selected", String(isVideo));
    els.tabAudio.classList.toggle("is-active", !isVideo);
    els.tabAudio.setAttribute("aria-selected", String(!isVideo));
    els.videoPanel.hidden = !isVideo;
    els.audioPanel.hidden = isVideo;
  }

  function renderVideoOptions() {
    const media = state.media;
    const options = (media && media.video_options) || [];
    els.videoQualityGrid.innerHTML = "";

    if (options.length === 0) {
      els.noVideoNote.hidden = false;
    } else {
      els.noVideoNote.hidden = true;
      options.forEach((opt) => {
        const card = document.createElement("button");
        card.type = "button";
        card.className = "choice-card";
        if (opt.height === state.selectedHeight) {
          card.classList.add("is-selected");
        }

        const top = document.createElement("div");
        top.className = "choice-top";

        const title = document.createElement("span");
        title.className = "choice-title";
        title.textContent = opt.label;

        const tag = document.createElement("span");
        tag.className = "choice-tag";
        const tagParts = [opt.quality_tag];
        if (opt.fps && opt.fps >= 50) tagParts.push(`${opt.fps}fps`);
        if (opt.dynamic_range) tagParts.push(opt.dynamic_range);
        tag.textContent = tagParts.join(" · ");

        top.append(title, tag);

        const sub = document.createElement("span");
        sub.className = "choice-sub";
        const parts = [];
        if (opt.vcodec) parts.push(opt.vcodec);
        const sizeLabel = formatBytes(opt.filesize_approx);
        parts.push(sizeLabel ? `~${sizeLabel}` : "Tamaño variable");
        sub.textContent = parts.join(" · ");

        card.append(top, sub);
        card.addEventListener("click", () => {
          state.selectedHeight = opt.height;
          renderVideoOptions();
          renderDetailedSpecs();
          updateDownloadCta();
        });
        els.videoQualityGrid.appendChild(card);
      });
    }

    const containers = (media && media.video_containers) || [];
    els.containerPills.innerHTML = "";
    containers.forEach((item) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "pill-choice";
      if (item.value === state.selectedContainer) {
        btn.classList.add("is-selected");
      }

      const strong = document.createElement("strong");
      strong.textContent = item.label;
      const desc = document.createElement("span");
      desc.textContent = item.description;

      btn.append(strong, desc);
      btn.addEventListener("click", () => {
        state.selectedContainer = item.value;
        renderVideoOptions();
        renderDetailedSpecs();
        updateDownloadCta();
      });
      els.containerPills.appendChild(btn);
    });
  }

  function renderAudioOptions() {
    const media = state.media;
    const formats = (media && media.audio_formats) || [];
    const bitrates = (media && media.audio_bitrates) || [];
    const selectedFormatObj = formats.find((f) => f.format === state.selectedAudioFormat);
    const isLossless = Boolean(selectedFormatObj && selectedFormatObj.lossless);

    els.audioFormatGrid.innerHTML = "";
    formats.forEach((fmt) => {
      const card = document.createElement("button");
      card.type = "button";
      card.className = "choice-card";
      if (fmt.format === state.selectedAudioFormat) {
        card.classList.add("is-selected");
      }

      const top = document.createElement("div");
      top.className = "choice-top";

      const title = document.createElement("span");
      title.className = "choice-title";
      title.textContent = fmt.label;
      top.append(title);

      if (fmt.lossless) {
        const tag = document.createElement("span");
        tag.className = "choice-tag";
        tag.textContent = "Sin pérdida";
        top.append(tag);
      }

      const sub = document.createElement("span");
      sub.className = "choice-sub";
      sub.textContent = fmt.description;

      card.append(top, sub);
      card.addEventListener("click", () => {
        state.selectedAudioFormat = fmt.format;
        renderAudioOptions();
        renderDetailedSpecs();
        updateDownloadCta();
      });
      els.audioFormatGrid.appendChild(card);
    });

    els.audioBitrateGrid.innerHTML = "";
    els.audioBitrateGrid.hidden = isLossless;
    els.losslessNote.hidden = !isLossless;

    if (!isLossless) {
      bitrates.forEach((br) => {
        const card = document.createElement("button");
        card.type = "button";
        card.className = "choice-card";
        if (br.bitrate === state.selectedAudioBitrate) {
          card.classList.add("is-selected");
        }

        const top = document.createElement("div");
        top.className = "choice-top";

        const title = document.createElement("span");
        title.className = "choice-title";
        title.textContent = br.label;
        top.append(title);

        if (br.bitrate === 320) {
          const tag = document.createElement("span");
          tag.className = "choice-tag";
          tag.textContent = "Máxima";
          top.append(tag);
        } else if (br.bitrate === 192) {
          const tag = document.createElement("span");
          tag.className = "choice-tag";
          tag.textContent = "Equilibrada";
          top.append(tag);
        }

        const sub = document.createElement("span");
        sub.className = "choice-sub";
        const sizeLabel = formatBytes(br.estimated_bytes);
        sub.textContent = sizeLabel ? `~${sizeLabel}` : "Bitrate constante";

        card.append(top, sub);
        card.addEventListener("click", () => {
          state.selectedAudioBitrate = br.bitrate;
          renderAudioOptions();
          renderDetailedSpecs();
          updateDownloadCta();
        });
        els.audioBitrateGrid.appendChild(card);
      });
    }
  }

  function updateDownloadCta() {
    if (!state.media) return;
    if (state.mode === "video") {
      const options = state.media.video_options || [];
      if (options.length === 0) {
        els.startDownloadBtn.disabled = true;
        els.downloadBtnText.textContent = "Sin pistas de video";
        return;
      }
      els.startDownloadBtn.disabled = false;
      const selected = options.find((opt) => opt.height === state.selectedHeight) || options[0];
      const resLabel = selected ? selected.label : "Mejor calidad";
      els.downloadBtnText.textContent = `Descargar Video · ${resLabel} · ${state.selectedContainer.toUpperCase()}`;
    } else {
      els.startDownloadBtn.disabled = false;
      const fmtObj = (state.media.audio_formats || []).find((f) => f.format === state.selectedAudioFormat);
      const isLossless = Boolean(fmtObj && fmtObj.lossless);
      const suffix = isLossless ? "Sin pérdida" : `${state.selectedAudioBitrate} kbps`;
      els.downloadBtnText.textContent = `Descargar Audio · ${state.selectedAudioFormat.toUpperCase()} · ${suffix}`;
    }
  }

  async function startDownload() {
    if (!state.media) return;
    clearError();

    const payload = {
      url: state.media.url,
      mode: state.mode,
      height: state.mode === "video" ? state.selectedHeight : null,
      container: state.selectedContainer,
      audio_format: state.selectedAudioFormat,
      audio_bitrate: state.selectedAudioBitrate,
      embed_metadata: els.embedMetadata.checked,
      title_hint: state.media.title,
    };

    els.startDownloadBtn.disabled = true;
    try {
      const resp = await fetch("/api/downloads", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const job = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        throw new Error(job.detail || "No se pudo iniciar la descarga.");
      }

      state.activeJobId = job.job_id;
      upsertHistory({
        job_id: job.job_id,
        url: state.media.url,
        title: job.title || state.media.title,
        quality_label: job.quality_label,
        status: job.status,
        filesize: job.filesize,
        saved_path: job.saved_path,
        created_at: job.created_at,
      });

      renderProgressCard(job);
      subscribeToJob(job.job_id);
    } catch (err) {
      showError(err instanceof Error ? err.message : "Error al iniciar la descarga.");
    } finally {
      updateDownloadCta();
    }
  }

  function closeJobListeners() {
    if (state.eventSource) {
      state.eventSource.close();
      state.eventSource = null;
    }
    if (state.pollTimer) {
      clearInterval(state.pollTimer);
      state.pollTimer = null;
    }
  }

  function subscribeToJob(jobId) {
    closeJobListeners();
    if (typeof EventSource !== "undefined") {
      const es = new EventSource(`/api/downloads/${encodeURIComponent(jobId)}/events`);
      state.eventSource = es;

      es.onmessage = (event) => {
        try {
          handleJobUpdate(JSON.parse(event.data));
        } catch {
          // Ignore invalid frame
        }
      };

      es.onerror = () => {
        es.close();
        state.eventSource = null;
        startFallbackPolling(jobId);
      };
    } else {
      startFallbackPolling(jobId);
    }
  }

  function startFallbackPolling(jobId) {
    if (state.pollTimer) return;
    state.pollTimer = setInterval(async () => {
      try {
        const resp = await fetch(`/api/downloads/${encodeURIComponent(jobId)}`);
        if (!resp.ok) {
          closeJobListeners();
          return;
        }
        handleJobUpdate(await resp.json());
      } catch {
        // Retry next tick
      }
    }, 1000);
  }

  function handleJobUpdate(job) {
    renderProgressCard(job);
    upsertHistory({
      job_id: job.job_id,
      url: (state.media && state.media.url) || "",
      title: job.title,
      quality_label: job.quality_label,
      status: job.status,
      filesize: job.filesize,
      saved_path: job.saved_path,
      created_at: job.created_at,
    });

    if (job.status === "completed") {
      closeJobListeners();
      if (!job.saved_path && !isDesktopMode() && !state.autoDownloadedJobs.has(job.job_id)) {
        state.autoDownloadedJobs.add(job.job_id);
        triggerBrowserDownload(job.job_id);
      }
    } else if (job.status === "error" || job.status === "cancelled") {
      closeJobListeners();
      if (job.error) {
        showError(job.error);
      }
    }
  }

  function renderProgressCard(job) {
    els.progressSection.hidden = false;
    els.progressTitle.textContent = job.title || "Procesando descarga...";
    els.progressMeta.textContent = job.quality_label || "";

    const pct = Math.max(0, Math.min(100, Number(job.percent || 0)));
    els.progressPercent.textContent = `${pct.toFixed(pct >= 100 || pct === 0 ? 0 : 1)}%`;
    els.progressFill.style.width = `${pct}%`;
    els.progressTrack.setAttribute("aria-valuenow", String(Math.round(pct)));

    els.progressBadge.className = "status-pill";
    els.progressFill.className = "liquid-progress-fill";

    if (job.status === "completed") {
      els.progressBadge.textContent = "Completado";
      els.progressBadge.classList.add("is-completed");
      els.progressFill.classList.add("is-completed");
    } else if (job.status === "error") {
      els.progressBadge.textContent = "Error";
      els.progressBadge.classList.add("is-error");
      els.progressFill.classList.add("is-error");
    } else if (job.status === "cancelled") {
      els.progressBadge.textContent = "Cancelado";
      els.progressBadge.classList.add("is-error");
    } else if (job.status === "processing") {
      els.progressBadge.textContent = "Procesando";
      els.progressFill.classList.add("is-active");
    } else if (job.status === "queued") {
      els.progressBadge.textContent = "En cola";
      els.progressFill.classList.add("is-active");
    } else {
      els.progressBadge.textContent = "Descargando";
      els.progressFill.classList.add("is-active");
    }

    els.progressStage.textContent = job.stage || "";
    els.progressSpeed.textContent = formatSpeed(job.speed);
    els.progressEta.textContent = job.status === "downloading" ? formatEta(job.eta) : "";

    const downloadedLabel = formatBytes(job.downloaded_bytes);
    const totalLabel = formatBytes(job.filesize || job.total_bytes);
    if (job.status === "completed" && totalLabel) {
      els.progressSize.textContent = `Tamaño final: ${totalLabel}`;
    } else if (downloadedLabel && totalLabel) {
      els.progressSize.textContent = `${downloadedLabel} / ${totalLabel}`;
    } else if (downloadedLabel) {
      els.progressSize.textContent = downloadedLabel;
    } else {
      els.progressSize.textContent = "";
    }

    const isActive = ["queued", "downloading", "processing"].includes(job.status);
    els.cancelJobBtn.hidden = !isActive;
    els.cancelJobBtn.disabled = !isActive;

    els.openSavedFolderBtn.hidden = true;
    els.openSavedFileBtn.hidden = true;
    els.saveFileBtn.hidden = true;
    els.savedPathLine.hidden = true;

    if (job.status === "completed") {
      if (job.saved_path && isDesktopMode()) {
        els.openSavedFolderBtn.hidden = false;
        els.openSavedFolderBtn.onclick = () => openSystemPath("/api/system/open-folder", job.saved_path);
        els.openSavedFileBtn.hidden = false;
        els.openSavedFileBtn.onclick = () => openSystemPath("/api/system/open-file", job.saved_path);
        els.savedPathLine.textContent = `Guardado en: ${job.saved_path}`;
        els.savedPathLine.hidden = false;
      } else {
        els.saveFileBtn.href = `/api/downloads/${encodeURIComponent(job.job_id)}/file`;
        els.saveFileBtn.hidden = false;
      }
    }
  }

  async function openSystemPath(endpoint, targetPath) {
    if (!targetPath) return;
    try {
      await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path: targetPath }),
      });
    } catch {
      // Ignore error
    }
  }

  function triggerBrowserDownload(jobId) {
    const anchor = document.createElement("a");
    anchor.href = `/api/downloads/${encodeURIComponent(jobId)}/file`;
    anchor.download = "";
    anchor.style.display = "none";
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
  }

  async function cancelActiveJob() {
    if (!state.activeJobId) return;
    els.cancelJobBtn.disabled = true;
    try {
      const resp = await fetch(`/api/downloads/${encodeURIComponent(state.activeJobId)}/cancel`, {
        method: "POST",
      });
      if (resp.ok) {
        handleJobUpdate(await resp.json());
      }
    } catch {
      // Ignore
    }
  }

  function upsertHistory(item) {
    if (!item || !item.job_id) return;
    const idx = state.history.findIndex((h) => h.job_id === item.job_id);
    const prev = idx >= 0 ? state.history[idx] : {};
    const merged = {
      job_id: item.job_id,
      url: item.url || prev.url || "",
      title: item.title || prev.title || "Descarga multimedia",
      quality_label: item.quality_label || prev.quality_label || "",
      status: item.status || prev.status || "queued",
      filesize: item.filesize || prev.filesize || null,
      saved_path: item.saved_path || prev.saved_path || null,
      created_at: item.created_at || prev.created_at || Date.now() / 1000,
    };

    if (idx >= 0) {
      state.history[idx] = merged;
    } else {
      state.history.unshift(merged);
    }

    state.history = state.history.slice(0, 15);
    saveLocalHistory();
    renderHistory();
  }

  function renderHistory() {
    if (state.history.length === 0) {
      els.historySection.hidden = true;
      els.historyList.innerHTML = "";
      return;
    }

    els.historySection.hidden = false;
    els.historyList.innerHTML = "";

    state.history.forEach((item) => {
      const row = document.createElement("div");
      row.className = "history-item";

      const info = document.createElement("div");
      info.className = "history-info";

      const title = document.createElement("div");
      title.className = "history-title";
      title.textContent = item.title;

      const sub = document.createElement("div");
      sub.className = "history-subline";
      const parts = [item.quality_label];
      const sizeText = formatBytes(item.filesize);
      if (sizeText) parts.push(sizeText);
      if (item.status === "error") parts.push("Error");
      else if (item.status === "cancelled") parts.push("Cancelado");
      sub.textContent = parts.filter(Boolean).join(" · ");

      info.append(title, sub);

      const actions = document.createElement("div");
      actions.className = "history-actions";

      if (item.status === "completed") {
        if (item.saved_path && isDesktopMode()) {
          const folderBtn = document.createElement("button");
          folderBtn.type = "button";
          folderBtn.className = "glass-pill-btn";
          folderBtn.textContent = "Carpeta";
          folderBtn.addEventListener("click", () => openSystemPath("/api/system/open-folder", item.saved_path));
          actions.appendChild(folderBtn);
        } else {
          const dlLink = document.createElement("a");
          dlLink.className = "glass-pill-btn";
          dlLink.href = `/api/downloads/${encodeURIComponent(item.job_id)}/file`;
          dlLink.download = "";
          dlLink.textContent = "Descargar";
          actions.appendChild(dlLink);
        }
      }

      if (item.url) {
        const reBtn = document.createElement("button");
        reBtn.type = "button";
        reBtn.className = "glass-pill-btn";
        reBtn.textContent = "Re-analizar";
        reBtn.addEventListener("click", () => {
          els.urlInput.value = item.url;
          updateClearButton();
          analyzeUrl(item.url);
          window.scrollTo({ top: 0, behavior: "smooth" });
        });
        actions.appendChild(reBtn);
      }

      row.append(info, actions);
      els.historyList.appendChild(row);
    });
  }

  async function syncServerDownloads() {
    try {
      const resp = await fetch("/api/downloads");
      if (!resp.ok) return;
      const jobs = await resp.json();
      if (Array.isArray(jobs)) {
        jobs.slice().reverse().forEach((job) => upsertHistory(job));
      }
    } catch {
      // Ignore sync error
    }
  }

  async function pickDownloadFolder() {
    if (!hasDesktopBridge() || typeof window.pywebview.api.select_download_folder !== "function") {
      return;
    }
    try {
      const chosen = await window.pywebview.api.select_download_folder();
      if (!chosen) return;
      const resp = await fetch("/api/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ download_dir: chosen }),
      });
      if (resp.ok) {
        const data = await resp.json();
        updateFolderDisplays(data.download_dir);
      }
    } catch {
      // Ignore cancel
    }
  }

  function openSettingsModal() {
    els.settingsModal.hidden = false;
    loadAppInfo();
  }

  function closeSettingsModal() {
    els.settingsModal.hidden = true;
  }

  // Event listeners
  els.themeToggleBtn.addEventListener("click", () => {
    const next = getCurrentTheme() === "dark" ? "light" : "dark";
    applyTheme(next, true);
  });

  els.openSettingsBtn.addEventListener("click", openSettingsModal);
  els.updatePill.addEventListener("click", openSettingsModal);
  els.closeSettingsBtn.addEventListener("click", closeSettingsModal);
  els.settingsModal.addEventListener("click", (e) => {
    if (e.target === els.settingsModal) closeSettingsModal();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !els.settingsModal.hidden) {
      closeSettingsModal();
    }
  });

  els.analyzeForm.addEventListener("submit", (e) => {
    e.preventDefault();
    analyzeUrl();
  });

  els.urlInput.addEventListener("input", updateClearButton);

  els.clearBtn.addEventListener("click", () => {
    els.urlInput.value = "";
    updateClearButton();
    clearError();
    els.urlInput.focus();
  });

  els.pasteBtn.addEventListener("click", async () => {
    clearError();
    try {
      if (!navigator.clipboard || !navigator.clipboard.readText) {
        throw new Error("Clipboard unavailable");
      }
      const text = (await navigator.clipboard.readText()).trim();
      if (!text) {
        showError("El portapapeles está vacío.");
        return;
      }
      els.urlInput.value = text;
      updateClearButton();
      if (/^https?:\/\//i.test(text)) {
        analyzeUrl(text);
      }
    } catch {
      showError("No se pudo leer el portapapeles automáticamente. Usa Ctrl+V en el campo.");
      els.urlInput.focus();
    }
  });

  els.detailsToggleBtn.addEventListener("click", () => {
    const expanded = els.detailsToggleBtn.getAttribute("aria-expanded") === "true";
    els.detailsToggleBtn.setAttribute("aria-expanded", String(!expanded));
    els.detailsPanel.classList.toggle("is-open", !expanded);
  });

  els.openSourceBtn.addEventListener("click", () => {
    if (!state.media) return;
    const target = state.media.webpage_url || state.media.url;
    if (!target) return;
    if (hasDesktopBridge() && typeof window.pywebview.api.open_external_url === "function") {
      window.pywebview.api.open_external_url(target).catch(() => {});
    } else {
      window.open(target, "_blank", "noopener");
    }
  });

  els.tabVideo.addEventListener("click", () => {
    state.mode = "video";
    renderModeTabs();
    renderDetailedSpecs();
    updateDownloadCta();
  });

  els.tabAudio.addEventListener("click", () => {
    state.mode = "audio";
    renderModeTabs();
    renderDetailedSpecs();
    updateDownloadCta();
  });

  els.quickFolderBtn.addEventListener("click", pickDownloadFolder);
  els.modalChooseFolderBtn.addEventListener("click", pickDownloadFolder);
  els.modalOpenFolderBtn.addEventListener("click", () => {
    if (state.appInfo && state.appInfo.download_dir) {
      openSystemPath("/api/system/open-folder", state.appInfo.download_dir);
    }
  });

  els.startDownloadBtn.addEventListener("click", startDownload);
  els.cancelJobBtn.addEventListener("click", cancelActiveJob);

  els.clearHistoryBtn.addEventListener("click", () => {
    state.history = [];
    saveLocalHistory();
    renderHistory();
  });

  els.updateEngineBtn.addEventListener("click", async () => {
    els.updateEngineBtn.disabled = true;
    els.updateEngineBtn.textContent = "Actualizando...";
    els.engineFeedback.hidden = false;
    els.engineFeedback.textContent = "Consultando GitHub de yt-dlp...";
    try {
      const resp = await fetch("/api/updates/engine", { method: "POST" });
      const data = await resp.json();
      els.engineFeedback.textContent = data.message || "Listo.";
      els.restartAppBtn.hidden = !(data.restart_required && isDesktopMode());
      loadAppInfo();
    } catch {
      els.engineFeedback.textContent = "No se pudo actualizar el motor en este momento.";
    } finally {
      els.updateEngineBtn.disabled = false;
      els.updateEngineBtn.textContent = "Actualizar motor";
    }
  });

  els.restartAppBtn.addEventListener("click", () => {
    if (hasDesktopBridge() && typeof window.pywebview.api.restart_app === "function") {
      window.pywebview.api.restart_app().catch(() => {});
    }
  });

  els.checkAppUpdateBtn.addEventListener("click", async () => {
    els.checkAppUpdateBtn.disabled = true;
    els.checkAppUpdateBtn.textContent = "Buscando...";
    try {
      const resp = await fetch("/api/updates/check");
      const data = await resp.json();
      renderUpdateStatus(data);
    } catch {
      els.appUpdateText.textContent = "No se pudo consultar GitHub Releases.";
    } finally {
      els.checkAppUpdateBtn.disabled = false;
      els.checkAppUpdateBtn.textContent = "Buscar actualización";
    }
  });

  els.installAppUpdateBtn.addEventListener("click", async () => {
    if (!state.updateInfo || !state.updateInfo.asset_url) return;
    els.installAppUpdateBtn.disabled = true;
    els.installAppUpdateBtn.textContent = "Descargando...";
    try {
      const resp = await fetch("/api/updates/app", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          asset_url: state.updateInfo.asset_url,
          asset_name: state.updateInfo.asset_name,
        }),
      });
      const data = await resp.json();
      els.appUpdateText.textContent = data.message || data.detail || "Instalando actualización...";
    } catch {
      els.appUpdateText.textContent = "No se pudo descargar la actualización.";
      els.installAppUpdateBtn.disabled = false;
      els.installAppUpdateBtn.textContent = "Instalar actualización";
    }
  });

  window.addEventListener("pywebviewready", () => {
    applyTheme(getCurrentTheme(), false);
    loadAppInfo();
  });

  // Init
  updateClearButton();
  renderHistory();
  loadAppInfo().then(() => {
    syncServerDownloads();
    checkUpdatesSilent();
  });
})();
