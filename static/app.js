(() => {
  "use strict";

  const THEME_STORAGE_KEY = "exclaim_download_theme";
  const HISTORY_STORAGE_KEY = "exclaim_download_history_v1";

  const VIEW_TITLES = {
    download: "Descargar",
    player: "Reproductor",
    activity: "Actividad",
    engines: "Motores",
    settings: "Ajustes",
  };

  const state = {
    appInfo: null,
    media: null,
    activeView: "download",
    mode: "video",
    playlistMode: "auto",
    selectedPlaylistIndices: new Set(),
    selectedHeight: null,
    selectedContainer: "mp4",
    selectedAudioFormat: "mp3",
    selectedAudioBitrate: 192,
    activeJobId: null,
    eventSource: null,
    pollTimer: null,
    autoDownloadedJobs: new Set(),
    updateInfo: null,
    lastSyncedTheme: null,
    pickingFolder: false,
    history: loadLocalHistory(),
  };

  const els = {
    sidebarNav: document.getElementById("sidebarNav"),
    mobileTabCapsule: document.getElementById("mobileTabCapsule"),
    viewTitle: document.getElementById("viewTitle"),
    mobileLargeTitle: document.getElementById("mobileLargeTitle"),
    navActivityBadge: document.getElementById("navActivityBadge"),
    mobileActivityDot: document.getElementById("mobileActivityDot"),
    sidebarEngineDot: document.getElementById("sidebarEngineDot"),
    sidebarUpdateDot: document.getElementById("sidebarUpdateDot"),
    mobileUpdateDot: document.getElementById("mobileUpdateDot"),
    mobileUpdateBtn: document.getElementById("mobileUpdateBtn"),
    mobileThemeBtn: document.getElementById("mobileThemeBtn"),

    updatePill: document.getElementById("updatePill"),
    updatePillText: document.getElementById("updatePillText"),

    heroComposer: document.getElementById("heroComposer"),
    quickTiles: document.getElementById("quickTiles"),
    tilePasteBtn: document.getElementById("tilePasteBtn"),
    tileActivityBtn: document.getElementById("tileActivityBtn"),
    tileFolderBtn: document.getElementById("tileFolderBtn"),
    tileFolderLabel: document.getElementById("tileFolderLabel"),

    analyzeForm: document.getElementById("analyzeForm"),
    urlInput: document.getElementById("urlInput"),
    clearBtn: document.getElementById("clearBtn"),
    pasteBtn: document.getElementById("pasteBtn"),
    analyzeBtn: document.getElementById("analyzeBtn"),
    errorBanner: document.getElementById("errorBanner"),
    errorMessage: document.getElementById("errorMessage"),

    mediaSection: document.getElementById("mediaSection"),
    mediaThumbBg: document.getElementById("mediaThumbBg"),
    mediaThumb: document.getElementById("mediaThumb"),
    thumbFallback: document.getElementById("thumbFallback"),
    mediaDuration: document.getElementById("mediaDuration"),
    mediaLiveBadge: document.getElementById("mediaLiveBadge"),
    mediaPlatform: document.getElementById("mediaPlatform"),
    mediaMaxRes: document.getElementById("mediaMaxRes"),
    mediaSourceAudio: document.getElementById("mediaSourceAudio"),
    mediaSubtitles: document.getElementById("mediaSubtitles"),
    openSourceBtn: document.getElementById("openSourceBtn"),
    resetMediaBtn: document.getElementById("resetMediaBtn"),
    mediaTitle: document.getElementById("mediaTitle"),
    mediaUploader: document.getElementById("mediaUploader"),
    mediaDate: document.getElementById("mediaDate"),
    mediaViews: document.getElementById("mediaViews"),
    mediaLikes: document.getElementById("mediaLikes"),

    qualityMeter: document.getElementById("qualityMeter"),
    qualityMeterValue: document.getElementById("qualityMeterValue"),
    qualityMeterLabel: document.getElementById("qualityMeterLabel"),
    qualityMeterInfoBtn: document.getElementById("qualityMeterInfoBtn"),

    playlistScopeBar: document.getElementById("playlistScopeBar"),
    scopeSingleBtn: document.getElementById("scopeSingleBtn"),
    scopePlaylistBtn: document.getElementById("scopePlaylistBtn"),
    playlistSection: document.getElementById("playlistSection"),
    playlistSelectedCount: document.getElementById("playlistSelectedCount"),
    toggleAllPlaylistBtn: document.getElementById("toggleAllPlaylistBtn"),
    playlistEntriesList: document.getElementById("playlistEntriesList"),

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
    progressIconSquircle: document.getElementById("progressIconSquircle"),
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
    playSavedFileBtn: document.getElementById("playSavedFileBtn"),
    openSavedFileBtn: document.getElementById("openSavedFileBtn"),
    saveFileBtn: document.getElementById("saveFileBtn"),
    savedPathLine: document.getElementById("savedPathLine"),
    copySideStoreUrlBtn: document.getElementById("copySideStoreUrlBtn"),
    sideStoreSourceUrl: document.getElementById("sideStoreSourceUrl"),
    openSideStoreBtn: document.getElementById("openSideStoreBtn"),

    historySection: document.getElementById("historySection"),
    historyEmptyState: document.getElementById("historyEmptyState"),
    historySub: document.getElementById("historySub"),
    historyList: document.getElementById("historyList"),
    clearHistoryBtn: document.getElementById("clearHistoryBtn"),
    footerCredit: document.getElementById("footerCredit"),

    modalVersionSub: document.getElementById("modalVersionSub"),
    settingsThemeLight: document.getElementById("settingsThemeLight"),
    settingsThemeDark: document.getElementById("settingsThemeDark"),
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

  function hasAndroidBridge() {
    return Boolean(window.AndroidBridge);
  }

  function hasIOSBridge() {
    return Boolean(window.webkit && window.webkit.messageHandlers && window.webkit.messageHandlers.iosBridge);
  }

  function isMobileNative() {
    return Boolean(
      (state.appInfo && (state.appInfo.platform === "android" || state.appInfo.platform === "ios")) ||
      hasAndroidBridge() ||
      hasIOSBridge()
    );
  }

  function isDesktopMode() {
    return Boolean(
      (state.appInfo && state.appInfo.desktop_mode) ||
      hasDesktopBridge() ||
      hasAndroidBridge() ||
      hasIOSBridge()
    );
  }

  function setActiveView(viewName) {
    const view = VIEW_TITLES[viewName] ? viewName : "download";
    state.activeView = view;
    document.body.setAttribute("data-active-view", view);

    if (els.viewTitle) {
      els.viewTitle.textContent = VIEW_TITLES[view];
    }
    if (els.mobileLargeTitle) {
      els.mobileLargeTitle.textContent = view === "download" ? "!Download" : VIEW_TITLES[view];
    }

    document.querySelectorAll("[data-view-panel]").forEach((panel) => {
      panel.hidden = panel.getAttribute("data-view-panel") !== view;
    });

    document.querySelectorAll("[data-view]").forEach((btn) => {
      btn.classList.toggle("is-active", btn.getAttribute("data-view") === view);
    });

    if ((view === "engines" || view === "settings") && !state.appInfo) {
      loadAppInfo();
    }
    if (window.ExclaimPlayer) {
      if (typeof window.ExclaimPlayer.onViewChanged === "function") {
        window.ExclaimPlayer.onViewChanged(view);
      }
      if (view === "player" && typeof window.ExclaimPlayer.onViewActivated === "function") {
        window.ExclaimPlayer.onViewActivated();
      }
    }
    window.scrollTo({ top: 0, behavior: "smooth" });
  }
  window.__setActiveView = setActiveView;

  function getCurrentTheme() {
    return document.documentElement.getAttribute("data-theme") === "light" ? "light" : "dark";
  }

  function applyTheme(theme, persistRemote) {
    const normalized = theme === "light" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", normalized);

    if (els.settingsThemeLight) {
      els.settingsThemeLight.classList.toggle("is-active", normalized === "light");
    }
    if (els.settingsThemeDark) {
      els.settingsThemeDark.classList.toggle("is-active", normalized === "dark");
    }

    try {
      localStorage.setItem(THEME_STORAGE_KEY, normalized);
    } catch {
      // Ignore storage error
    }
    if (
      hasDesktopBridge() &&
      typeof window.pywebview.api.set_window_theme === "function" &&
      state.lastSyncedTheme !== normalized
    ) {
      state.lastSyncedTheme = normalized;
      window.pywebview.api.set_window_theme(normalized).catch(() => {});
    }
    if (hasAndroidBridge() && typeof window.AndroidBridge.setSystemBarTheme === "function") {
      try {
        window.AndroidBridge.setSystemBarTheme(normalized);
      } catch {
        // Ignore Android bridge error
      }
    }
    if (hasIOSBridge()) {
      try {
        window.webkit.messageHandlers.iosBridge.postMessage({ action: "setTheme", theme: normalized });
      } catch {
        // Ignore iOS bridge error
      }
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
  }

  function createCheckSvg() {
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("viewBox", "0 0 24 24");
    svg.setAttribute("fill", "none");
    svg.setAttribute("stroke", "currentColor");
    svg.setAttribute("stroke-width", "2.5");
    svg.setAttribute("stroke-linecap", "round");
    svg.setAttribute("stroke-linejoin", "round");
    svg.setAttribute("class", "inset-check");
    svg.setAttribute("aria-hidden", "true");
    const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
    path.setAttribute("d", "m5 12.5 4.8 4.8L19 7");
    svg.appendChild(path);
    return svg;
  }

  async function loadAppInfo() {
    try {
      const resp = await fetch("/api/app-info");
      if (!resp.ok) return;
      const info = await resp.json();
      state.appInfo = info;

      const version = info.version || "1.6.0";
      const developer = info.developer || "Juan Corporation";
      els.footerCredit.textContent = `${info.name || "!Download"} v${version} · ${developer}`;
      els.modalVersionSub.textContent = `v${version} · ${developer}`;

      updateFolderDisplays(info.download_dir);
      renderTools(info.tools || {});

      if (info.desktop_mode) {
        els.historySub.textContent = "Guardadas directamente en tu carpeta de descargas.";
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
    const mobileNative = isMobileNative();
    els.folderPill.hidden = !desktop || !clean;
    els.modalFolderSection.hidden = !desktop || !clean;
    els.quickFolderBtn.hidden = mobileNative;
    els.modalChooseFolderBtn.hidden = mobileNative;

    if (els.tileFolderLabel) {
      els.tileFolderLabel.textContent = desktop && !mobileNative ? "Carpeta destino" : "Motores y ajustes";
    }

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
    const anyMissing = ["yt_dlp", "ffmpeg", "deno"].some((key) => {
      const item = tools[key];
      return !(item && item.available);
    });

    if (els.sidebarEngineDot) {
      els.sidebarEngineDot.classList.toggle("is-missing", anyMissing);
    }

    const specs = [
      ["yt_dlp", "yt-dlp", "sf-blue", "DL"],
      ["ffmpeg", "FFmpeg", "sf-green", "AV"],
      ["ffprobe", "FFprobe", "sf-teal", "IN"],
      ["deno", "Deno", "sf-orange", "JS"],
    ];

    els.modalToolsGrid.innerHTML = "";
    specs.forEach(([key, label, colorClass, codeText]) => {
      const item = tools[key] || {};
      const row = document.createElement("div");
      row.className = "inset-row";

      const badge = document.createElement("span");
      badge.className = `sf-squircle sf-sm ${colorClass}`;
      badge.textContent = codeText;
      badge.style.fontSize = "0.66rem";
      badge.style.fontWeight = "700";

      const main = document.createElement("div");
      main.className = "inset-row-main";

      const title = document.createElement("span");
      title.className = "inset-row-title";
      title.textContent = label;

      const sub = document.createElement("span");
      sub.className = "inset-row-sub";
      if (item.available) {
        const suffix = item.using_override ? " · Actualizado" : "";
        sub.textContent = `${formatToolVersion(key, item.version)}${suffix}`;
        sub.title = item.version || "";
      } else {
        sub.textContent = "No detectado en este sistema";
      }
      main.append(title, sub);

      const status = document.createElement("span");
      status.className = `engine-row-status ${item.available ? "" : "is-missing"}`;
      status.textContent = item.available ? "✓ Listo" : "Falta";

      row.append(badge, main, status);
      els.modalToolsGrid.appendChild(row);
    });
  }

  async function checkUpdatesSilent() {
    try {
      const resp = await fetch("/api/updates/check");
      if (!resp.ok) return;
      renderUpdateStatus(await resp.json());
    } catch {
      // Silent background check
    }
  }

  function renderUpdateStatus(data) {
    state.updateInfo = data;
    const available = Boolean(data && data.update_available && data.latest_version);

    if (available) {
      els.updatePillText.textContent = `v${data.latest_version} disponible`;
      els.updatePill.hidden = false;
    } else {
      els.updatePill.hidden = true;
    }
    if (els.sidebarUpdateDot) els.sidebarUpdateDot.hidden = !available;
    if (els.mobileUpdateDot) els.mobileUpdateDot.hidden = !available;
    if (els.mobileUpdateBtn) els.mobileUpdateBtn.hidden = !available;

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
    const canSelfUpdate = Boolean(available && data.asset_url && data.asset_name && selfUpdateSupported);
    els.installAppUpdateBtn.hidden = !canSelfUpdate;
  }

  function updateClearButton() {
    els.clearBtn.hidden = !els.urlInput.value.trim();
  }

  function resetMediaView() {
    state.media = null;
    state.playlistMode = "auto";
    state.selectedPlaylistIndices.clear();
    els.mediaSection.hidden = true;
    els.heroComposer.hidden = false;
    els.quickTiles.hidden = false;
    clearError();
    els.urlInput.focus();
  }

  async function analyzeUrl(urlValue, overrideMode) {
    const url = (urlValue || els.urlInput.value).trim();
    clearError();
    if (!url) {
      showError("Pega un enlace de video o audio para analizarlo.");
      els.urlInput.focus();
      return;
    }

    const playlistMode = overrideMode || state.playlistMode || "auto";
    state.playlistMode = playlistMode;

    setAnalyzing(true);
    try {
      const resp = await fetch("/api/info", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url, playlist_mode: playlistMode }),
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
    const containers = media.video_containers || [];
    state.selectedContainer = containers.some((c) => c.value === "mp4")
      ? "mp4"
      : ((containers[0] && containers[0].value) || "mp4");
    const audioFormats = media.audio_formats || [];
    state.selectedAudioFormat = audioFormats.some((f) => f.format === "mp3")
      ? "mp3"
      : ((audioFormats[0] && audioFormats[0].format) || "mp3");
    state.selectedAudioBitrate = 192;
  }

  function renderQualityMeter() {
    if (!state.media || !els.qualityMeter) return;
    let level = 3;
    let headline = "";
    let subline = "";

    if (state.mode === "video") {
      const options = state.media.video_options || [];
      const selected = options.find((opt) => opt.height === state.selectedHeight) || options[0];
      if (selected) {
        const h = Number(selected.height || 0);
        if (h >= 2160) level = 5;
        else if (h >= 1440) level = 4;
        else if (h >= 1080) level = 4;
        else if (h >= 720) level = 3;
        else if (h >= 480) level = 2;
        else level = 1;

        headline = `${selected.label}${selected.quality_tag ? ` (${selected.quality_tag})` : ""}`;
        const size = formatBytes(selected.filesize_approx);
        const bits = [state.selectedContainer.toUpperCase()];
        if (selected.vcodec) bits.push(selected.vcodec);
        if (size) bits.push(`~${size}`);
        subline = bits.join(" · ");
      } else {
        level = 1;
        headline = "Solo Audio";
        subline = "Este enlace no incluye video";
      }
    } else {
      const formats = state.media.audio_formats || [];
      const fmtObj = formats.find((f) => f.format === state.selectedAudioFormat);
      const isLossless = Boolean(fmtObj && fmtObj.lossless);
      if (isLossless || state.selectedAudioBitrate >= 320) level = 5;
      else if (state.selectedAudioBitrate >= 256) level = 4;
      else if (state.selectedAudioBitrate >= 192) level = 3;
      else level = 2;

      headline = `${state.selectedAudioFormat.toUpperCase()} · ${isLossless ? "Sin pérdida" : `${state.selectedAudioBitrate} kbps`}`;
      const brObj = (state.media.audio_bitrates || []).find((b) => b.bitrate === state.selectedAudioBitrate);
      const size = formatBytes(brObj && brObj.estimated_bytes);
      subline = isLossless ? "Calidad maestra sin compresión" : (size ? `Tamaño estimado ~${size}` : "Audio comprimido");
    }

    els.qualityMeterValue.textContent = headline;
    els.qualityMeterLabel.textContent = subline;
    const bars = els.qualityMeter.querySelectorAll("span");
    bars.forEach((bar, index) => {
      bar.classList.toggle("is-active", index < level);
    });
  }

  function renderMediaSection(media) {
    els.heroComposer.hidden = true;
    els.quickTiles.hidden = true;
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
      const proxied = `/api/thumbnail?url=${encodeURIComponent(media.thumbnail)}`;
      els.mediaThumb.hidden = true;
      els.mediaThumbBg.hidden = true;
      els.thumbFallback.hidden = false;
      els.mediaThumb.onload = () => {
        els.mediaThumb.hidden = false;
        els.thumbFallback.hidden = true;
        els.mediaThumbBg.src = proxied;
        els.mediaThumbBg.hidden = false;
      };
      els.mediaThumb.onerror = () => {
        els.mediaThumb.hidden = true;
        els.mediaThumbBg.hidden = true;
        els.thumbFallback.hidden = false;
      };
      els.mediaThumb.src = proxied;
    } else {
      els.mediaThumb.removeAttribute("src");
      els.mediaThumbBg.removeAttribute("src");
      els.mediaThumb.hidden = true;
      els.mediaThumbBg.hidden = true;
      els.thumbFallback.hidden = false;
    }

    if (media.description) {
      els.mediaDescription.textContent = media.description;
      els.descriptionBox.hidden = false;
    } else {
      els.descriptionBox.hidden = true;
    }

    renderPlaylistSection(media);
    renderModeTabs();
    renderVideoOptions();
    renderAudioOptions();
    renderDetailedSpecs();
    renderQualityMeter();
    updateDownloadCta();
  }

  function renderPlaylistSection(media) {
    const canToggle = Boolean(media.can_toggle_playlist);
    const isPlaylist = Boolean(media.is_playlist);

    if (els.playlistScopeBar) {
      els.playlistScopeBar.hidden = !canToggle;
      if (canToggle && els.scopeSingleBtn && els.scopePlaylistBtn) {
        els.scopeSingleBtn.className = isPlaylist ? "apple-secondary-pill" : "apple-blue-pill";
        els.scopePlaylistBtn.className = isPlaylist ? "apple-blue-pill" : "apple-secondary-pill";
      }
    }

    if (!els.playlistSection || !els.playlistEntriesList) return;
    if (!isPlaylist) {
      state.selectedPlaylistIndices.clear();
      els.playlistSection.hidden = true;
      els.playlistEntriesList.innerHTML = "";
      return;
    }

    const entries = media.playlist_entries || [];
    state.selectedPlaylistIndices = new Set(entries.map((entry) => entry.index));
    renderPlaylistEntriesList(entries);
    els.playlistSection.hidden = false;
  }

  function renderPlaylistEntriesList(entries) {
    if (!els.playlistEntriesList) return;
    els.playlistEntriesList.innerHTML = "";

    entries.forEach((entry) => {
      const selected = state.selectedPlaylistIndices.has(entry.index);
      const row = document.createElement("button");
      row.type = "button";
      row.className = `inset-row playlist-row${selected ? " is-selected" : ""}`;

      const circle = document.createElement("span");
      circle.className = "playlist-check-circle";
      const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
      svg.setAttribute("viewBox", "0 0 24 24");
      svg.setAttribute("fill", "none");
      svg.setAttribute("stroke", "currentColor");
      svg.setAttribute("stroke-width", "3");
      svg.setAttribute("stroke-linecap", "round");
      svg.setAttribute("stroke-linejoin", "round");
      const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
      path.setAttribute("d", "m5 12.5 4.8 4.8L19 7");
      svg.appendChild(path);
      circle.appendChild(svg);

      const idxPill = document.createElement("span");
      idxPill.className = "playlist-index-pill";
      idxPill.textContent = String(entry.index).padStart(2, "0");

      const main = document.createElement("div");
      main.className = "inset-row-main";

      const title = document.createElement("span");
      title.className = "inset-row-title";
      title.textContent = entry.title || `Elemento ${entry.index}`;

      const subParts = [];
      if (entry.uploader) subParts.push(entry.uploader);
      if (entry.duration_text) subParts.push(entry.duration_text);
      if (subParts.length > 0) {
        const sub = document.createElement("span");
        sub.className = "inset-row-sub";
        sub.textContent = subParts.join(" · ");
        main.append(title, sub);
      } else {
        main.append(title);
      }

      row.append(circle, idxPill, main);
      row.addEventListener("click", () => {
        if (state.selectedPlaylistIndices.has(entry.index)) {
          state.selectedPlaylistIndices.delete(entry.index);
        } else {
          state.selectedPlaylistIndices.add(entry.index);
        }
        renderPlaylistEntriesList(entries);
        updateDownloadCta();
      });
      els.playlistEntriesList.appendChild(row);
    });

    updatePlaylistSelectionHeader(entries.length);
  }

  function updatePlaylistSelectionHeader(totalCount) {
    const selectedCount = state.selectedPlaylistIndices.size;
    if (els.playlistSelectedCount) {
      els.playlistSelectedCount.textContent = `${selectedCount}/${totalCount}`;
    }
    if (els.toggleAllPlaylistBtn) {
      els.toggleAllPlaylistBtn.textContent =
        selectedCount === totalCount && totalCount > 0 ? "Deseleccionar todo" : "Seleccionar todo";
    }
  }

  function renderDetailedSpecs() {
    if (!state.media) return;
    const media = state.media;
    const rows = [];

    if (state.mode === "video") {
      const selected = (media.video_options || []).find((o) => o.height === state.selectedHeight) || (media.video_options || [])[0];
      if (selected) {
        const res = selected.width && selected.height ? `${selected.width} × ${selected.height} px` : selected.label;
        rows.push(["Resolución elegida", res]);
        if (selected.fps) rows.push(["Fotogramas", `${selected.fps} fps`]);
        if (selected.vcodec) rows.push(["Códec de video", selected.vcodec]);
        rows.push(["Rango dinámico", selected.dynamic_range || "SDR"]);
        if (selected.tbr) rows.push(["Bitrate de video", `~${selected.tbr} kbps`]);
        const est = formatBytes(selected.filesize_approx);
        if (est) rows.push(["Tamaño estimado", `~${est}`]);
      }
      rows.push(["Contenedor", state.selectedContainer.toUpperCase()]);
    } else {
      const fmtObj = (media.audio_formats || []).find((f) => f.format === state.selectedAudioFormat);
      const isLossless = Boolean(fmtObj && fmtObj.lossless);
      rows.push(["Formato de salida", state.selectedAudioFormat.toUpperCase()]);
      rows.push(["Calidad elegida", isLossless ? "Sin pérdida (Lossless)" : `${state.selectedAudioBitrate} kbps`]);
      if (!isLossless) {
        const brObj = (media.audio_bitrates || []).find((b) => b.bitrate === state.selectedAudioBitrate);
        const est = formatBytes(brObj && brObj.estimated_bytes);
        if (est) rows.push(["Tamaño estimado", `~${est}`]);
      }
    }

    if (media.source_audio_codec || media.source_audio_abr) {
      const parts = [];
      if (media.source_audio_codec) parts.push(media.source_audio_codec);
      if (media.source_audio_abr) parts.push(`${media.source_audio_abr} kbps`);
      rows.push(["Audio origen", parts.join(" · ")]);
    }
    if (media.duration_text) {
      rows.push(["Duración", media.duration_text]);
    }
    if ((media.subtitle_languages || []).length > 0) {
      rows.push(["Subtítulos", media.subtitle_languages.slice(0, 8).join(", ")]);
    }

    els.specsGrid.innerHTML = "";
    rows.forEach(([label, value]) => {
      const row = document.createElement("div");
      row.className = "inset-row";
      const lbl = document.createElement("span");
      lbl.className = "spec-label";
      lbl.textContent = label;
      const val = document.createElement("span");
      val.className = "spec-value";
      val.textContent = value;
      row.append(lbl, val);
      els.specsGrid.appendChild(row);
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
      els.videoQualityGrid.hidden = true;
    } else {
      els.noVideoNote.hidden = true;
      els.videoQualityGrid.hidden = false;
      options.forEach((opt) => {
        const row = document.createElement("button");
        row.type = "button";
        row.className = "inset-row";
        if (opt.height === state.selectedHeight) {
          row.classList.add("is-selected");
        }

        const main = document.createElement("div");
        main.className = "inset-row-main";

        const titleRow = document.createElement("span");
        titleRow.className = "inset-row-title";
        titleRow.textContent = opt.label;

        const tagParts = [opt.quality_tag];
        if (opt.fps && opt.fps >= 50) tagParts.push(`${opt.fps}fps`);
        if (opt.dynamic_range) tagParts.push(opt.dynamic_range);
        if (tagParts.filter(Boolean).length > 0) {
          const tag = document.createElement("span");
          tag.className = "inset-tag";
          tag.textContent = tagParts.filter(Boolean).join(" · ");
          titleRow.appendChild(tag);
        }

        const sub = document.createElement("span");
        sub.className = "inset-row-sub";
        const parts = [];
        if (opt.vcodec) parts.push(opt.vcodec);
        const sizeLabel = formatBytes(opt.filesize_approx);
        parts.push(sizeLabel ? `~${sizeLabel}` : "Tamaño variable");
        sub.textContent = parts.join(" · ");

        main.append(titleRow, sub);
        row.append(main, createCheckSvg());
        row.addEventListener("click", () => {
          state.selectedHeight = opt.height;
          renderVideoOptions();
          renderDetailedSpecs();
          renderQualityMeter();
          updateDownloadCta();
        });
        els.videoQualityGrid.appendChild(row);
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
        renderQualityMeter();
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
      const row = document.createElement("button");
      row.type = "button";
      row.className = "inset-row";
      if (fmt.format === state.selectedAudioFormat) {
        row.classList.add("is-selected");
      }

      const main = document.createElement("div");
      main.className = "inset-row-main";

      const titleRow = document.createElement("span");
      titleRow.className = "inset-row-title";
      titleRow.textContent = fmt.label;

      if (fmt.lossless) {
        const tag = document.createElement("span");
        tag.className = "inset-tag";
        tag.textContent = "Sin pérdida";
        titleRow.appendChild(tag);
      }

      const sub = document.createElement("span");
      sub.className = "inset-row-sub";
      sub.textContent = fmt.description;

      main.append(titleRow, sub);
      row.append(main, createCheckSvg());
      row.addEventListener("click", () => {
        state.selectedAudioFormat = fmt.format;
        renderAudioOptions();
        renderDetailedSpecs();
        renderQualityMeter();
        updateDownloadCta();
      });
      els.audioFormatGrid.appendChild(row);
    });

    els.audioBitrateGrid.innerHTML = "";
    els.audioBitrateGrid.hidden = isLossless;
    els.losslessNote.hidden = !isLossless;

    if (!isLossless) {
      bitrates.forEach((br) => {
        const row = document.createElement("button");
        row.type = "button";
        row.className = "inset-row";
        if (br.bitrate === state.selectedAudioBitrate) {
          row.classList.add("is-selected");
        }

        const main = document.createElement("div");
        main.className = "inset-row-main";

        const titleRow = document.createElement("span");
        titleRow.className = "inset-row-title";
        titleRow.textContent = br.label;

        if (br.bitrate === 320 || br.bitrate === 192) {
          const tag = document.createElement("span");
          tag.className = "inset-tag";
          tag.textContent = br.bitrate === 320 ? "Máxima" : "Equilibrada";
          titleRow.appendChild(tag);
        }

        const sub = document.createElement("span");
        sub.className = "inset-row-sub";
        const sizeLabel = formatBytes(br.estimated_bytes);
        sub.textContent = sizeLabel ? `~${sizeLabel}` : "Bitrate constante";

        main.append(titleRow, sub);
        row.append(main, createCheckSvg());
        row.addEventListener("click", () => {
          state.selectedAudioBitrate = br.bitrate;
          renderAudioOptions();
          renderDetailedSpecs();
          renderQualityMeter();
          updateDownloadCta();
        });
        els.audioBitrateGrid.appendChild(row);
      });
    }
  }

  function updateDownloadCta() {
    if (!state.media) return;
    const isPlaylist = Boolean(state.media.is_playlist);
    const count = state.selectedPlaylistIndices.size;
    if (isPlaylist && count === 0) {
      els.startDownloadBtn.disabled = true;
      els.downloadBtnText.textContent = "Selecciona al menos 1 elemento";
      return;
    }
    const prefix = isPlaylist ? `Descargar Playlist (${count})` : null;

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
      els.downloadBtnText.textContent = prefix
        ? `${prefix} · ${resLabel} · ${state.selectedContainer.toUpperCase()}`
        : `Descargar Video · ${resLabel} · ${state.selectedContainer.toUpperCase()}`;
    } else {
      els.startDownloadBtn.disabled = false;
      const fmtObj = (state.media.audio_formats || []).find((f) => f.format === state.selectedAudioFormat);
      const isLossless = Boolean(fmtObj && fmtObj.lossless);
      const suffix = isLossless ? "Sin pérdida" : `${state.selectedAudioBitrate} kbps`;
      els.downloadBtnText.textContent = prefix
        ? `${prefix} · ${state.selectedAudioFormat.toUpperCase()} · ${suffix}`
        : `Descargar Audio · ${state.selectedAudioFormat.toUpperCase()} · ${suffix}`;
    }
  }

  async function startDownload() {
    if (!state.media) return;
    clearError();

    const isPlaylist = Boolean(state.media.is_playlist);
    const playlistItems = isPlaylist
      ? Array.from(state.selectedPlaylistIndices).sort((a, b) => a - b)
      : null;

    if (isPlaylist && (!playlistItems || playlistItems.length === 0)) {
      showError("Selecciona al menos un elemento de la playlist para descargar.");
      return;
    }

    const payload = {
      url: state.media.url,
      mode: state.mode,
      height: state.mode === "video" ? state.selectedHeight : null,
      container: state.selectedContainer,
      audio_format: state.selectedAudioFormat,
      audio_bitrate: state.selectedAudioBitrate,
      embed_metadata: els.embedMetadata.checked,
      title_hint: state.media.title,
      is_playlist: isPlaylist,
      playlist_items: playlistItems,
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
      if (window.ExclaimPlayer && typeof window.ExclaimPlayer.refreshLibrary === "function") {
        window.ExclaimPlayer.refreshLibrary();
      }
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
    els.progressIconSquircle.className = "live-squircle";

    if (job.status === "completed") {
      els.progressBadge.textContent = "Completado";
      els.progressBadge.classList.add("is-completed");
      els.progressFill.classList.add("is-completed");
      els.progressIconSquircle.classList.add("is-completed");
    } else if (job.status === "error") {
      els.progressBadge.textContent = "Error";
      els.progressBadge.classList.add("is-error");
      els.progressFill.classList.add("is-error");
      els.progressIconSquircle.classList.add("is-error");
    } else if (job.status === "cancelled") {
      els.progressBadge.textContent = "Cancelado";
      els.progressBadge.classList.add("is-error");
      els.progressIconSquircle.classList.add("is-error");
    } else if (job.status === "processing") {
      els.progressBadge.textContent = "Procesando";
    } else if (job.status === "queued") {
      els.progressBadge.textContent = "En cola";
    } else {
      els.progressBadge.textContent = "Descargando";
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
    els.playSavedFileBtn.hidden = true;
    els.openSavedFileBtn.hidden = true;
    els.saveFileBtn.hidden = true;
    els.savedPathLine.hidden = true;

    if (job.status === "completed") {
      if (job.saved_path && isDesktopMode()) {
        els.openSavedFolderBtn.textContent = job.is_playlist ? "Abrir carpeta" : "Mostrar en carpeta";
        els.openSavedFolderBtn.hidden = false;
        els.openSavedFolderBtn.onclick = () => openSystemPath("/api/system/open-folder", job.saved_path);
        els.playSavedFileBtn.hidden = Boolean(job.is_playlist);
        els.playSavedFileBtn.onclick = () => {
          if (window.ExclaimPlayer && typeof window.ExclaimPlayer.playPath === "function") {
            window.ExclaimPlayer.playPath(job.saved_path);
          }
        };
        els.openSavedFileBtn.hidden = Boolean(job.is_playlist);
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

  function createHistorySquircle(item) {
    const label = String(item.quality_label || "").toLowerCase();
    const isAudio = label.includes("audio") || label.includes("mp3") || label.includes("m4a") || label.includes("flac") || label.includes("opus") || label.includes("wav");
    const box = document.createElement("span");
    box.className = `sf-squircle sf-lg ${isAudio ? "sf-purple" : "sf-blue"}`;
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("viewBox", "0 0 24 24");
    svg.setAttribute("fill", "none");
    svg.setAttribute("stroke", "currentColor");
    svg.setAttribute("stroke-width", "2");
    svg.setAttribute("stroke-linecap", "round");
    svg.setAttribute("stroke-linejoin", "round");
    if (isAudio) {
      const p = document.createElementNS("http://www.w3.org/2000/svg", "path");
      p.setAttribute("d", "M9 18V5l12-2v13");
      const c1 = document.createElementNS("http://www.w3.org/2000/svg", "circle");
      c1.setAttribute("cx", "6"); c1.setAttribute("cy", "18"); c1.setAttribute("r", "3");
      const c2 = document.createElementNS("http://www.w3.org/2000/svg", "circle");
      c2.setAttribute("cx", "18"); c2.setAttribute("cy", "16"); c2.setAttribute("r", "3");
      svg.append(p, c1, c2);
    } else {
      const rect = document.createElementNS("http://www.w3.org/2000/svg", "rect");
      rect.setAttribute("x", "3"); rect.setAttribute("y", "5"); rect.setAttribute("width", "18"); rect.setAttribute("height", "14"); rect.setAttribute("rx", "3");
      const poly = document.createElementNS("http://www.w3.org/2000/svg", "polygon");
      poly.setAttribute("points", "10 9 16 12 10 15 10 9");
      svg.append(rect, poly);
    }
    box.appendChild(svg);
    return box;
  }

  function renderHistory() {
    const count = state.history.length;
    if (els.navActivityBadge) {
      els.navActivityBadge.textContent = String(count);
      els.navActivityBadge.hidden = count === 0;
    }
    if (els.mobileActivityDot) {
      els.mobileActivityDot.hidden = count === 0;
    }

    if (count === 0) {
      els.historySection.hidden = true;
      els.historyEmptyState.hidden = false;
      els.historyList.innerHTML = "";
      return;
    }

    els.historySection.hidden = false;
    els.historyEmptyState.hidden = true;
    els.historyList.innerHTML = "";

    state.history.forEach((item) => {
      const row = document.createElement("div");
      row.className = "inset-row history-row";

      const squircle = createHistorySquircle(item);

      const main = document.createElement("div");
      main.className = "inset-row-main";

      const title = document.createElement("div");
      title.className = "history-title-text";
      title.textContent = item.title;

      const sub = document.createElement("div");
      sub.className = `history-status-line ${item.status === "completed" ? "is-ok" : ""}`;
      if (item.status === "completed") {
        const ck = document.createElementNS("http://www.w3.org/2000/svg", "svg");
        ck.setAttribute("viewBox", "0 0 24 24");
        ck.setAttribute("fill", "none");
        ck.setAttribute("stroke", "currentColor");
        ck.setAttribute("stroke-width", "2.6");
        const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
        path.setAttribute("d", "m5 12.5 4.8 4.8L19 7");
        ck.appendChild(path);
        sub.appendChild(ck);
      }
      const parts = [item.quality_label];
      const sizeText = formatBytes(item.filesize);
      if (sizeText) parts.push(sizeText);
      if (item.status === "error") parts.push("Error");
      else if (item.status === "cancelled") parts.push("Cancelado");
      const textNode = document.createElement("span");
      textNode.textContent = parts.filter(Boolean).join(" · ");
      sub.appendChild(textNode);

      main.append(title, sub);

      const actions = document.createElement("div");
      actions.className = "history-row-actions";

      if (item.status === "completed") {
        if (item.saved_path && isDesktopMode()) {
          if (!item.saved_path.endsWith(item.title || "") || /\.[a-z0-9]{2,5}$/i.test(item.saved_path)) {
            const playHistBtn = document.createElement("button");
            playHistBtn.type = "button";
            playHistBtn.className = "apple-blue-pill";
            playHistBtn.textContent = "Reproducir";
            playHistBtn.addEventListener("click", () => {
              if (window.ExclaimPlayer && typeof window.ExclaimPlayer.playPath === "function") {
                window.ExclaimPlayer.playPath(item.saved_path);
              }
            });
            actions.appendChild(playHistBtn);
          }
          const folderBtn = document.createElement("button");
          folderBtn.type = "button";
          folderBtn.className = "apple-secondary-pill";
          folderBtn.textContent = "Carpeta";
          folderBtn.addEventListener("click", () => openSystemPath("/api/system/open-folder", item.saved_path));
          actions.appendChild(folderBtn);
        } else {
          const dlLink = document.createElement("a");
          dlLink.className = "apple-secondary-pill";
          dlLink.href = `/api/downloads/${encodeURIComponent(item.job_id)}/file`;
          dlLink.download = "";
          dlLink.textContent = "Guardar";
          actions.appendChild(dlLink);
        }
      }

      if (item.url) {
        const reBtn = document.createElement("button");
        reBtn.type = "button";
        reBtn.className = "circle-action-outline";
        reBtn.title = "Re-analizar enlace";
        reBtn.setAttribute("aria-label", "Re-analizar enlace");
        reBtn.textContent = "↻";
        reBtn.addEventListener("click", () => {
          setActiveView("download");
          els.urlInput.value = item.url;
          updateClearButton();
          analyzeUrl(item.url);
        });
        actions.appendChild(reBtn);
      }

      row.append(squircle, main, actions);
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
    if (
      state.pickingFolder ||
      !hasDesktopBridge() ||
      typeof window.pywebview.api.select_download_folder !== "function"
    ) {
      return;
    }
    state.pickingFolder = true;
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
    } finally {
      state.pickingFolder = false;
    }
  }

  async function pasteFromClipboardAndAnalyze() {
    clearError();
    try {
      let text = "";
      if (hasDesktopBridge() && typeof window.pywebview.api.read_clipboard_text === "function") {
        text = String((await window.pywebview.api.read_clipboard_text()) || "").trim();
      } else if (hasAndroidBridge() && typeof window.AndroidBridge.readClipboardText === "function") {
        text = String(window.AndroidBridge.readClipboardText() || "").trim();
      } else if (navigator.clipboard && navigator.clipboard.readText) {
        text = (await navigator.clipboard.readText()).trim();
      } else {
        throw new Error("Clipboard unavailable");
      }
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
      showError("No se pudo leer el portapapeles automáticamente. Pega el enlace en el campo.");
      els.urlInput.focus();
    }
  }

  // Navigation listeners
  document.querySelectorAll("[data-view]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const target = btn.getAttribute("data-view");
      if (target) setActiveView(target);
    });
  });

  els.updatePill.addEventListener("click", () => setActiveView("settings"));
  if (els.mobileUpdateBtn) {
    els.mobileUpdateBtn.addEventListener("click", () => setActiveView("settings"));
  }

  // Theme listeners
  if (els.mobileThemeBtn) {
    els.mobileThemeBtn.addEventListener("click", () => {
      applyTheme(getCurrentTheme() === "dark" ? "light" : "dark", true);
    });
  }
  if (els.settingsThemeLight) {
    els.settingsThemeLight.addEventListener("click", () => applyTheme("light", true));
  }
  if (els.settingsThemeDark) {
    els.settingsThemeDark.addEventListener("click", () => applyTheme("dark", true));
  }

  // Form & tiles
  els.analyzeForm.addEventListener("submit", (e) => {
    e.preventDefault();
    state.playlistMode = "auto";
    analyzeUrl(undefined, "auto");
  });

  if (els.scopeSingleBtn) {
    els.scopeSingleBtn.addEventListener("click", () => {
      if (state.media) analyzeUrl(state.media.url, "single");
    });
  }
  if (els.scopePlaylistBtn) {
    els.scopePlaylistBtn.addEventListener("click", () => {
      if (state.media) analyzeUrl(state.media.url, "playlist");
    });
  }
  if (els.toggleAllPlaylistBtn) {
    els.toggleAllPlaylistBtn.addEventListener("click", () => {
      if (!state.media || !state.media.is_playlist) return;
      const entries = state.media.playlist_entries || [];
      if (state.selectedPlaylistIndices.size === entries.length && entries.length > 0) {
        state.selectedPlaylistIndices.clear();
      } else {
        state.selectedPlaylistIndices = new Set(entries.map((entry) => entry.index));
      }
      renderPlaylistEntriesList(entries);
      updateDownloadCta();
    });
  }

  els.urlInput.addEventListener("input", () => {
    state.playlistMode = "auto";
    updateClearButton();
  });

  els.clearBtn.addEventListener("click", () => {
    els.urlInput.value = "";
    updateClearButton();
    clearError();
    els.urlInput.focus();
  });

  els.pasteBtn.addEventListener("click", pasteFromClipboardAndAnalyze);
  if (els.tilePasteBtn) {
    els.tilePasteBtn.addEventListener("click", pasteFromClipboardAndAnalyze);
  }
  if (els.tileActivityBtn) {
    els.tileActivityBtn.addEventListener("click", () => setActiveView("activity"));
  }
  if (els.tileFolderBtn) {
    els.tileFolderBtn.addEventListener("click", () => {
      if (isDesktopMode() && !isMobileNative() && hasDesktopBridge()) {
        pickDownloadFolder();
      } else {
        setActiveView("settings");
      }
    });
  }

  if (els.resetMediaBtn) {
    els.resetMediaBtn.addEventListener("click", resetMediaView);
  }

  els.detailsToggleBtn.addEventListener("click", () => {
    const expanded = els.detailsToggleBtn.getAttribute("aria-expanded") === "true";
    els.detailsToggleBtn.setAttribute("aria-expanded", String(!expanded));
    els.detailsPanel.classList.toggle("is-open", !expanded);
  });

  if (els.qualityMeterInfoBtn) {
    els.qualityMeterInfoBtn.addEventListener("click", () => {
      els.detailsToggleBtn.setAttribute("aria-expanded", "true");
      els.detailsPanel.classList.add("is-open");
      els.detailsToggleBtn.scrollIntoView({ behavior: "smooth", block: "center" });
    });
  }

  els.openSourceBtn.addEventListener("click", () => {
    if (!state.media) return;
    const target = state.media.webpage_url || state.media.url;
    if (!target) return;
    if (hasDesktopBridge() && typeof window.pywebview.api.open_external_url === "function") {
      window.pywebview.api.open_external_url(target).catch(() => {});
    } else if (hasAndroidBridge() && typeof window.AndroidBridge.openExternalUrl === "function") {
      window.AndroidBridge.openExternalUrl(target);
    } else if (hasIOSBridge()) {
      window.webkit.messageHandlers.iosBridge.postMessage({ action: "openExternalUrl", url: target });
    } else {
      window.open(target, "_blank", "noopener");
    }
  });

  els.tabVideo.addEventListener("click", () => {
    state.mode = "video";
    renderModeTabs();
    renderDetailedSpecs();
    renderQualityMeter();
    updateDownloadCta();
  });

  els.tabAudio.addEventListener("click", () => {
    state.mode = "audio";
    renderModeTabs();
    renderDetailedSpecs();
    renderQualityMeter();
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
      renderUpdateStatus(await resp.json());
    } catch {
      els.appUpdateText.textContent = "No se pudo consultar GitHub Releases.";
    } finally {
      els.checkAppUpdateBtn.disabled = false;
      els.checkAppUpdateBtn.textContent = "Buscar";
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
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        throw new Error(data.detail || "No se pudo descargar la actualización.");
      }
      els.appUpdateText.textContent = data.message || "Instalando actualización...";
      if (data.permission_required) {
        els.installAppUpdateBtn.disabled = false;
        els.installAppUpdateBtn.textContent = "Reintentar instalación";
      }
    } catch (err) {
      els.appUpdateText.textContent =
        err instanceof Error ? err.message : "No se pudo descargar la actualización.";
      els.installAppUpdateBtn.disabled = false;
      els.installAppUpdateBtn.textContent = "Instalar actualización";
    }
  });

  els.openSavedFileBtn.addEventListener("click", () => {});

  if (els.copySideStoreUrlBtn && els.sideStoreSourceUrl) {
    els.copySideStoreUrlBtn.addEventListener("click", async () => {
      const urlText = els.sideStoreSourceUrl.textContent.trim();
      try {
        await navigator.clipboard.writeText(urlText);
        els.copySideStoreUrlBtn.textContent = "¡Copiada!";
        setTimeout(() => { els.copySideStoreUrlBtn.textContent = "Copiar URL"; }, 1800);
      } catch {
        // Ignore clipboard fallback
      }
    });
  }

  window.addEventListener("pywebviewready", () => {
    applyTheme(getCurrentTheme(), false);
    loadAppInfo();
  });

  window.__receiveSharedUrl = function (sharedUrl) {
    const cleaned = String(sharedUrl || "").trim();
    if (!cleaned) return;
    setActiveView("download");
    els.urlInput.value = cleaned;
    updateClearButton();
    clearError();
    window.scrollTo({ top: 0, behavior: "smooth" });
    analyzeUrl(cleaned);
  };

  // Init
  setActiveView("download");
  applyTheme(getCurrentTheme(), false);
  updateClearButton();
  renderHistory();
  loadAppInfo().then(() => {
    syncServerDownloads();
    checkUpdatesSilent();
  });
})();
