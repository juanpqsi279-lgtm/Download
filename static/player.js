(() => {
  "use strict";

  const PREFS_KEY = "exclaim_player_prefs_v1";
  const FAVORITES_KEY = "exclaim_player_favorites_v1";
  const EQ_FREQS = [32, 64, 125, 250, 500, 1000, 2000, 4000, 8000, 16000];
  const EQ_LABELS = ["32", "64", "125", "250", "500", "1K", "2K", "4K", "8K", "16K"];

  const EQ_PRESETS = {
    flat: { name: "Plano", preamp: 0, gains: [0, 0, 0, 0, 0, 0, 0, 0, 0, 0] },
    bass_boost: { name: "Graves Potentes", preamp: -2, gains: [6.5, 5.5, 4, 2, 0, 0, 0, 0.5, 1, 1] },
    sub_bass: { name: "Sub-Bass", preamp: -3, gains: [8, 6.5, 3.5, 1, 0, 0, 0, 0, 0.5, 0.5] },
    treble_clarity: { name: "Agudos y Claridad", preamp: -1.5, gains: [0, 0, -1, 0, 1, 2.5, 4, 5.5, 6, 5.5] },
    vocal: { name: "Vocal", preamp: -1, gains: [-2, -1.5, -0.5, 1, 3.5, 4.5, 3.5, 2, 0.5, 0] },
    pop: { name: "Pop", preamp: -1.5, gains: [-1, 1.5, 3.5, 3, 1, -0.5, 1.5, 3, 3.5, 2.5] },
    rock: { name: "Rock", preamp: -2, gains: [4.5, 3.5, 1.5, -1, -1.5, 0.5, 2.5, 4, 4.5, 4] },
    electronic: { name: "Electrónica", preamp: -2, gains: [5.5, 4.5, 1.5, -1, -1.5, 0.5, 2.5, 4, 5, 5.5] },
    acoustic: { name: "Acústico", preamp: -1, gains: [3, 2, 1, 0.5, 1.5, 1.5, 2.5, 3, 2.5, 1.5] },
    podcast: { name: "Podcast / Voz", preamp: -1, gains: [-5, -3.5, -1.5, 1, 3.5, 4.5, 4, 2.5, 0, -1] },
    late_night: { name: "Noche", preamp: 0, gains: [-3, -1.5, 0, 1.5, 2.5, 2.5, 2, 1.5, -1, -2] },
    custom: { name: "Personalizado", preamp: 0, gains: [0, 0, 0, 0, 0, 0, 0, 0, 0, 0] },
  };

  const SPEED_STEPS = [0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0];
  const SLEEP_STEPS = [0, 15, 30, 45, 60];

  const DEFAULT_PREFS = {
    eqEnabled: true,
    eqLimiter: true,
    eqPreset: "flat",
    eqPreamp: 0,
    eqGains: [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    accentColor: "#ff2d55",
    visualizerStyle: "bars",
    ambientBg: true,
    autoAdvance: true,
    miniPlayerEnabled: true,
    volume: 1,
    speed: 1,
    libraryScope: "all",
    sortBy: "recent",
  };

  function loadPrefs() {
    try {
      const raw = JSON.parse(localStorage.getItem(PREFS_KEY) || "{}");
      const merged = Object.assign({}, DEFAULT_PREFS, raw);
      if (!Array.isArray(merged.eqGains) || merged.eqGains.length !== EQ_FREQS.length) {
        merged.eqGains = DEFAULT_PREFS.eqGains.slice();
      }
      return merged;
    } catch {
      return Object.assign({}, DEFAULT_PREFS, { eqGains: DEFAULT_PREFS.eqGains.slice() });
    }
  }

  function loadFavorites() {
    try {
      const arr = JSON.parse(localStorage.getItem(FAVORITES_KEY) || "[]");
      return new Set(Array.isArray(arr) ? arr : []);
    } catch {
      return new Set();
    }
  }

  const pState = {
    prefs: loadPrefs(),
    favorites: loadFavorites(),
    library: [],
    playlists: [],
    queue: [],
    queueIndex: -1,
    currentTrack: null,
    filterKind: "all",
    libraryViewMode: "tracks", // tracks | albums | folders | favorites
    currentFolderPath: "",
    selectedAlbumKey: null,
    searchQuery: "",
    activeSubtab: "library",
    selectedPlaylistId: null,
    shuffle: false,
    repeat: "off",
    muted: false,
    seeking: false,
    loopA: null,
    loopB: null,
    sleepRemainingSec: 0,
    sleepMode: "off",
    sleepInterval: null,
    activeView: "download",
    mediaPermissionGranted: true,
    coverBustMap: new Map(),

    audioCtx: null,
    audioSource: null,
    videoSource: null,
    preampNode: null,
    eqNodes: [],
    limiterNode: null,
    analyserNode: null,
    visRaf: null,

    metaTargetItem: null,
    metaCoverBase64: null,
    metaOpenTagOnImport: false,
    addToPlTrackPath: null,
  };

  const els = {
    viewPlayer: document.getElementById("viewPlayer"),
    nativeAudioEl: document.getElementById("nativeAudioEl"),
    nativeVideoEl: document.getElementById("nativeVideoEl"),
    playerStageCard: document.getElementById("playerStageCard"),
    playerAmbientBg: document.getElementById("playerAmbientBg"),
    videoStage: document.getElementById("videoStage"),
    audioStage: document.getElementById("audioStage"),
    pipBtn: document.getElementById("pipBtn"),
    videoFullscreenBtn: document.getElementById("videoFullscreenBtn"),
    playerArtFrame: document.getElementById("playerArtFrame"),
    playerArtwork: document.getElementById("playerArtwork"),
    playerArtFallback: document.getElementById("playerArtFallback"),
    playerFormatPill: document.getElementById("playerFormatPill"),
    playerEqBadge: document.getElementById("playerEqBadge"),
    sleepTimerBadge: document.getElementById("sleepTimerBadge"),
    abLoopBadge: document.getElementById("abLoopBadge"),
    playerNowTitle: document.getElementById("playerNowTitle"),
    playerNowSub: document.getElementById("playerNowSub"),
    playerVisualizer: document.getElementById("playerVisualizer"),
    playerSeek: document.getElementById("playerSeek"),
    playerCurrentTime: document.getElementById("playerCurrentTime"),
    playerDuration: document.getElementById("playerDuration"),
    playerShuffleBtn: document.getElementById("playerShuffleBtn"),
    playerPrevBtn: document.getElementById("playerPrevBtn"),
    playerBack10Btn: document.getElementById("playerBack10Btn"),
    playerPlayBtn: document.getElementById("playerPlayBtn"),
    playerFwd10Btn: document.getElementById("playerFwd10Btn"),
    playerNextBtn: document.getElementById("playerNextBtn"),
    playerRepeatBtn: document.getElementById("playerRepeatBtn"),
    playerMuteBtn: document.getElementById("playerMuteBtn"),
    playerVolume: document.getElementById("playerVolume"),
    playerFavBtn: document.getElementById("playerFavBtn"),
    playerSpeedBtn: document.getElementById("playerSpeedBtn"),
    playerSleepBtn: document.getElementById("playerSleepBtn"),
    playerAbBtn: document.getElementById("playerAbBtn"),
    playerQueueBtn: document.getElementById("playerQueueBtn"),
    playerTagCurrentBtn: document.getElementById("playerTagCurrentBtn"),

    playerSubtabs: document.getElementById("playerSubtabs"),
    playerTabLibrary: document.getElementById("playerTabLibrary"),
    playerTabPlaylists: document.getElementById("playerTabPlaylists"),
    playerTabEq: document.getElementById("playerTabEq"),
    playerTabCustomize: document.getElementById("playerTabCustomize"),

    librarySearchInput: document.getElementById("librarySearchInput"),
    librarySortSelect: document.getElementById("librarySortSelect"),
    refreshLibraryBtn: document.getElementById("refreshLibraryBtn"),
    libraryViewPills: document.getElementById("libraryViewPills"),
    libraryScopeBtn: document.getElementById("libraryScopeBtn"),
    libraryKindPills: document.getElementById("libraryKindPills"),
    addScanFolderBtn: document.getElementById("addScanFolderBtn"),
    importMediaBtn: document.getElementById("importMediaBtn"),
    tagExternalBtn: document.getElementById("tagExternalBtn"),
    importMediaInput: document.getElementById("importMediaInput"),
    androidMediaPermBanner: document.getElementById("androidMediaPermBanner"),
    grantAndroidPermBtn: document.getElementById("grantAndroidPermBtn"),

    folderBrowserView: document.getElementById("folderBrowserView"),
    folderBreadcrumbs: document.getElementById("folderBreadcrumbs"),
    playFolderAllBtn: document.getElementById("playFolderAllBtn"),
    playFolderShuffleBtn: document.getElementById("playFolderShuffleBtn"),
    folderCardsGrid: document.getElementById("folderCardsGrid"),
    folderTracksGroup: document.getElementById("folderTracksGroup"),
    folderTracksList: document.getElementById("folderTracksList"),

    albumsBrowserView: document.getElementById("albumsBrowserView"),
    albumsCardsGrid: document.getElementById("albumsCardsGrid"),
    albumDetailView: document.getElementById("albumDetailView"),
    albumBackBtn: document.getElementById("albumBackBtn"),
    albumDetailTitle: document.getElementById("albumDetailTitle"),
    albumDetailSub: document.getElementById("albumDetailSub"),
    playAlbumAllBtn: document.getElementById("playAlbumAllBtn"),
    playAlbumShuffleBtn: document.getElementById("playAlbumShuffleBtn"),
    albumTracksGroup: document.getElementById("albumTracksGroup"),
    albumTracksList: document.getElementById("albumTracksList"),

    libraryListGroup: document.getElementById("libraryListGroup"),
    libraryList: document.getElementById("libraryList"),
    libraryEmptyState: document.getElementById("libraryEmptyState"),

    createPlaylistForm: document.getElementById("createPlaylistForm"),
    newPlaylistName: document.getElementById("newPlaylistName"),
    newPlaylistKind: document.getElementById("newPlaylistKind"),
    createPlaylistBtn: document.getElementById("createPlaylistBtn"),
    customPlaylistsSection: document.getElementById("customPlaylistsSection"),
    customPlaylistsList: document.getElementById("customPlaylistsList"),
    playlistDetailView: document.getElementById("playlistDetailView"),
    playlistDetailTitle: document.getElementById("playlistDetailTitle"),
    playPlaylistAllBtn: document.getElementById("playPlaylistAllBtn"),
    playPlaylistShuffleBtn: document.getElementById("playPlaylistShuffleBtn"),
    renamePlaylistBtn: document.getElementById("renamePlaylistBtn"),
    deletePlaylistBtn: document.getElementById("deletePlaylistBtn"),
    playlistDetailItems: document.getElementById("playlistDetailItems"),
    folderCollectionsSection: document.getElementById("folderCollectionsSection"),
    folderCollectionsList: document.getElementById("folderCollectionsList"),

    eqEnabledSwitch: document.getElementById("eqEnabledSwitch"),
    eqLimiterSwitch: document.getElementById("eqLimiterSwitch"),
    eqResetBtn: document.getElementById("eqResetBtn"),
    eqPresetsRow: document.getElementById("eqPresetsRow"),
    eqPreampSlider: document.getElementById("eqPreampSlider"),
    eqPreampVal: document.getElementById("eqPreampVal"),
    eqBandsGrid: document.getElementById("eqBandsGrid"),
    eqGuideCard: document.getElementById("eqGuideCard"),
    eqQuickTweaks: document.getElementById("eqQuickTweaks"),

    playerAccentSwatches: document.getElementById("playerAccentSwatches"),
    visualizerStylePills: document.getElementById("visualizerStylePills"),
    prefAmbientBg: document.getElementById("prefAmbientBg"),
    prefAutoAdvance: document.getElementById("prefAutoAdvance"),
    prefMiniPlayer: document.getElementById("prefMiniPlayer"),

    miniPlayer: document.getElementById("miniPlayer"),
    miniPlayerProgress: document.getElementById("miniPlayerProgress"),
    miniPlayerOpenBtn: document.getElementById("miniPlayerOpenBtn"),
    miniPlayerThumb: document.getElementById("miniPlayerThumb"),
    miniPlayerFallback: document.getElementById("miniPlayerFallback"),
    miniPlayerTitle: document.getElementById("miniPlayerTitle"),
    miniPlayerSub: document.getElementById("miniPlayerSub"),
    miniPlayerPlayBtn: document.getElementById("miniPlayerPlayBtn"),
    miniPlayerNextBtn: document.getElementById("miniPlayerNextBtn"),

    metadataModal: document.getElementById("metadataModal"),
    metaModalTitle: document.getElementById("metaModalTitle"),
    metaTargetFileName: document.getElementById("metaTargetFileName"),
    closeMetadataModalBtn: document.getElementById("closeMetadataModalBtn"),
    metaAutoQuery: document.getElementById("metaAutoQuery"),
    metaAutoSearchBtn: document.getElementById("metaAutoSearchBtn"),
    metaAutoResults: document.getElementById("metaAutoResults"),
    metaCoverPreview: document.getElementById("metaCoverPreview"),
    metaCoverEmpty: document.getElementById("metaCoverEmpty"),
    metaCoverFileInput: document.getElementById("metaCoverFileInput"),
    metaTitle: document.getElementById("metaTitle"),
    metaArtist: document.getElementById("metaArtist"),
    metaAlbum: document.getElementById("metaAlbum"),
    metaYear: document.getElementById("metaYear"),
    metaTrack: document.getElementById("metaTrack"),
    metaGenre: document.getElementById("metaGenre"),
    metaCoverUrl: document.getElementById("metaCoverUrl"),
    metaStatusMsg: document.getElementById("metaStatusMsg"),
    metaPickOtherFileBtn: document.getElementById("metaPickOtherFileBtn"),
    metaApplyBtn: document.getElementById("metaApplyBtn"),

    queueModal: document.getElementById("queueModal"),
    queueModalTitle: document.getElementById("queueModalTitle"),
    queueCountSub: document.getElementById("queueCountSub"),
    closeQueueModalBtn: document.getElementById("closeQueueModalBtn"),
    queueList: document.getElementById("queueList"),
    clearQueueBtn: document.getElementById("clearQueueBtn"),

    addToPlaylistModal: document.getElementById("addToPlaylistModal"),
    addToPlTitle: document.getElementById("addToPlTitle"),
    addToPlTrackName: document.getElementById("addToPlTrackName"),
    closeAddToPlModalBtn: document.getElementById("closeAddToPlModalBtn"),
    addToPlList: document.getElementById("addToPlList"),
    quickAddPlaylistForm: document.getElementById("quickAddPlaylistForm"),
    quickAddPlName: document.getElementById("quickAddPlName"),
  };

  function savePrefs() {
    try { localStorage.setItem(PREFS_KEY, JSON.stringify(pState.prefs)); } catch {}
  }

  function saveFavorites() {
    try { localStorage.setItem(FAVORITES_KEY, JSON.stringify(Array.from(pState.favorites))); } catch {}
  }

  function formatTime(sec) {
    if (!Number.isFinite(sec) || sec < 0) return "0:00";
    const total = Math.floor(sec);
    const hrs = Math.floor(total / 3600);
    const mins = Math.floor((total % 3600) / 60);
    const secs = total % 60;
    if (hrs > 0) return `${hrs}:${String(mins).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
    return `${mins}:${String(secs).padStart(2, "0")}`;
  }

  function activeMediaElement() {
    return (pState.currentTrack && pState.currentTrack.kind === "video") ? els.nativeVideoEl : els.nativeAudioEl;
  }

  function streamUrlFor(item) {
    return `/api/library/stream?path=${encodeURIComponent(item.path)}`;
  }

  function coverUrlFor(item, forceBust = false) {
    if (!item || !item.has_cover) return null;
    const base = `/api/library/cover?path=${encodeURIComponent(item.path)}`;
    const bustTs = pState.coverBustMap.get(item.path);
    if (forceBust) return `${base}&t=${Date.now()}`;
    if (bustTs) return `${base}&t=${bustTs}`;
    return `${base}&m=${encodeURIComponent(String(item.mtime || 0))}`;
  }

  // =========================================================================
  // Web Audio API 10-Band EQ + Preamp + Limiter + Analyser
  // =========================================================================
  function ensureAudioGraph() {
    const AudioCtx = window.AudioContext || window.webkitAudioContext;
    if (!AudioCtx) return false;
    if (!pState.audioCtx) {
      try {
        const ctx = new AudioCtx();
        const preamp = ctx.createGain();
        const nodes = EQ_FREQS.map((freq, idx) => {
          const filter = ctx.createBiquadFilter();
          filter.frequency.value = freq;
          if (idx === 0) filter.type = "lowshelf";
          else if (idx === EQ_FREQS.length - 1) filter.type = "highshelf";
          else {
            filter.type = "peaking";
            filter.Q.value = 1.4;
          }
          return filter;
        });

        const limiter = ctx.createDynamicsCompressor();
        limiter.threshold.value = -1.0;
        limiter.knee.value = 4.0;
        limiter.ratio.value = 12.0;
        limiter.attack.value = 0.003;
        limiter.release.value = 0.15;

        const analyser = ctx.createAnalyser();
        analyser.fftSize = 128;
        analyser.smoothingTimeConstant = 0.8;

        preamp.connect(nodes[0]);
        for (let i = 0; i < nodes.length - 1; i++) nodes[i].connect(nodes[i + 1]);
        nodes[nodes.length - 1].connect(limiter);
        limiter.connect(analyser);
        analyser.connect(ctx.destination);

        pState.audioCtx = ctx;
        pState.preampNode = preamp;
        pState.eqNodes = nodes;
        pState.limiterNode = limiter;
        pState.analyserNode = analyser;

        try {
          pState.audioSource = ctx.createMediaElementSource(els.nativeAudioEl);
          pState.audioSource.connect(preamp);
        } catch {}
        try {
          pState.videoSource = ctx.createMediaElementSource(els.nativeVideoEl);
          pState.videoSource.connect(preamp);
        } catch {}
      } catch {
        return false;
      }
    }
    if (pState.audioCtx && pState.audioCtx.state === "suspended") {
      pState.audioCtx.resume().catch(() => {});
    }
    syncEqAudioNodes();
    return true;
  }

  function dbToGain(db) {
    return Math.pow(10, Number(db || 0) / 20);
  }

  function syncEqAudioNodes() {
    if (els.playerEqBadge) els.playerEqBadge.hidden = !pState.prefs.eqEnabled;
    if (!pState.audioCtx || !pState.preampNode) return;
    const enabled = Boolean(pState.prefs.eqEnabled);
    pState.preampNode.gain.value = enabled ? dbToGain(pState.prefs.eqPreamp) : 1.0;
    pState.eqNodes.forEach((node, idx) => {
      node.gain.value = enabled ? Number(pState.prefs.eqGains[idx] || 0) : 0;
    });
    if (pState.limiterNode) {
      pState.limiterNode.threshold.value = enabled && pState.prefs.eqLimiter ? -1.0 : 0.0;
      pState.limiterNode.ratio.value = enabled && pState.prefs.eqLimiter ? 20.0 : 1.0;
    }
  }

  // =========================================================================
  // Canvas Visualizer
  // =========================================================================
  function startVisualizerLoop() {
    if (pState.visRaf) return;
    const draw = () => {
      const el = activeMediaElement();
      if (!el || el.paused || pState.prefs.visualizerStyle === "none" || !pState.analyserNode || pState.currentTrack?.kind === "video") {
        pState.visRaf = null;
        return;
      }
      renderVisualizerFrame();
      pState.visRaf = requestAnimationFrame(draw);
    };
    pState.visRaf = requestAnimationFrame(draw);
  }

  function renderVisualizerFrame() {
    const canvas = els.playerVisualizer;
    if (!canvas) return;
    const style = pState.prefs.visualizerStyle;
    const ctx2d = canvas.getContext("2d");
    if (!ctx2d) return;
    ctx2d.clearRect(0, 0, canvas.width, canvas.height);
    if (style === "none" || !pState.analyserNode) return;

    const accent = pState.prefs.accentColor || "#ff2d55";
    ctx2d.fillStyle = accent;
    ctx2d.strokeStyle = accent;

    const bins = pState.analyserNode.frequencyBinCount;
    const data = new Uint8Array(bins);

    if (style === "wave") {
      pState.analyserNode.getByteTimeDomainData(data);
      ctx2d.lineWidth = 2.4;
      ctx2d.beginPath();
      const slice = canvas.width / bins;
      for (let i = 0; i < bins; i++) {
        const y = (data[i] / 255) * canvas.height;
        const x = i * slice;
        if (i === 0) ctx2d.moveTo(x, y);
        else ctx2d.lineTo(x, y);
      }
      ctx2d.stroke();
      return;
    }

    pState.analyserNode.getByteFrequencyData(data);
    if (style === "pulse") {
      const bass = (data[0] + data[1] + data[2] + data[3]) / (4 * 255);
      const mid = (data[8] + data[12] + data[16]) / (3 * 255);
      const cx = canvas.width / 2;
      const cy = canvas.height / 2;
      ctx2d.globalAlpha = 0.25 + bass * 0.55;
      ctx2d.beginPath();
      ctx2d.roundRect(cx - (60 + bass * 150), cy - 8, (60 + bass * 150) * 2, 16, 8);
      ctx2d.fill();
      ctx2d.globalAlpha = 0.7 + mid * 0.3;
      ctx2d.beginPath();
      ctx2d.roundRect(cx - (25 + mid * 95), cy - 4, (25 + mid * 95) * 2, 8, 4);
      ctx2d.fill();
      ctx2d.globalAlpha = 1;
      return;
    }

    const barCount = 32;
    const gap = 4;
    const barW = (canvas.width - gap * (barCount - 1)) / barCount;
    for (let i = 0; i < barCount; i++) {
      const val = data[i] / 255;
      const h = Math.max(4, val * (canvas.height - 6));
      const x = i * (barW + gap);
      const y = canvas.height - h;
      ctx2d.globalAlpha = 0.4 + val * 0.6;
      ctx2d.beginPath();
      ctx2d.roundRect(x, y, barW, h, 3);
      ctx2d.fill();
    }
    ctx2d.globalAlpha = 1;
  }

  // =========================================================================
  // Playback Engine
  // =========================================================================
  function pauseOtherElement(activeKind) {
    if (activeKind === "video") els.nativeAudioEl.pause();
    else els.nativeVideoEl.pause();
  }

  function playTrackItem(item, queueList = null, bustCover = false) {
    if (!item || !item.path) return;
    if (Array.isArray(queueList) && queueList.length > 0) {
      pState.queue = queueList.slice();
    } else if (!pState.queue.some((q) => q.path === item.path)) {
      pState.queue = pState.library.slice();
    }
    pState.queueIndex = pState.queue.findIndex((q) => q.path === item.path);
    pState.currentTrack = item;
    pState.loopA = null;
    pState.loopB = null;
    updateAbLoopBadge();

    ensureAudioGraph();
    pauseOtherElement(item.kind);

    const isVideo = item.kind === "video";
    els.videoStage.hidden = !isVideo;
    els.audioStage.hidden = isVideo;
    els.playerTagCurrentBtn.hidden = isVideo;

    const mediaEl = activeMediaElement();
    mediaEl.src = streamUrlFor(item);
    mediaEl.volume = pState.muted ? 0 : Number(pState.prefs.volume || 1);
    mediaEl.playbackRate = Number(pState.prefs.speed || 1);

    updateNowPlayingUI(item, bustCover);
    mediaEl.play().then(() => {
      updatePlayButtons(true);
      startVisualizerLoop();
      updateMediaSession(item);
    }).catch(() => {
      updatePlayButtons(false);
    });
  }

  function updateNowPlayingUI(item, forceBust = false) {
    if (!item) return;
    els.playerNowTitle.textContent = item.title || item.filename;
    const subParts = [item.artist, item.album].filter(Boolean);
    els.playerNowSub.textContent = subParts.length ? subParts.join(" · ") : (item.folder_group || "Archivo local");
    const fmtParts = [item.ext];
    if (item.bitrate) fmtParts.push(`${item.bitrate} kbps`);
    els.playerFormatPill.textContent = fmtParts.join(" · ");

    const coverUrl = coverUrlFor(item, forceBust);
    if (coverUrl) {
      els.playerArtwork.onload = () => {
        els.playerArtwork.hidden = false;
        els.playerArtFallback.hidden = true;
      };
      els.playerArtwork.onerror = () => {
        els.playerArtwork.hidden = true;
        els.playerArtFallback.hidden = false;
      };
      els.playerArtwork.src = coverUrl;
      els.playerArtwork.hidden = false;
      els.playerArtFallback.hidden = true;

      els.playerAmbientBg.src = coverUrl;
      els.playerAmbientBg.hidden = !pState.prefs.ambientBg;
      if (els.miniPlayerThumb) {
        els.miniPlayerThumb.src = coverUrl;
        els.miniPlayerThumb.hidden = false;
        els.miniPlayerFallback.hidden = true;
      }
    } else {
      els.playerArtwork.removeAttribute("src");
      els.playerArtwork.hidden = true;
      els.playerArtFallback.hidden = false;
      els.playerAmbientBg.hidden = true;
      if (els.miniPlayerThumb) {
        els.miniPlayerThumb.hidden = true;
        els.miniPlayerFallback.textContent = item.kind === "video" ? "🎬" : "♪";
        els.miniPlayerFallback.hidden = false;
      }
    }

    els.miniPlayerTitle.textContent = item.title || item.filename;
    els.miniPlayerSub.textContent = subParts.length ? subParts.join(" · ") : `!Download · ${item.ext}`;
    updateFavoriteButton();
    syncMiniPlayerVisibility();
    renderActiveLibraryView();
  }

  function updateFavoriteButton() {
    if (!els.playerFavBtn) return;
    const isFav = Boolean(pState.currentTrack && pState.favorites.has(pState.currentTrack.path));
    els.playerFavBtn.className = isFav ? "apple-blue-pill" : "apple-secondary-pill";
    els.playerFavBtn.textContent = isFav ? "♥ Favorita" : "♡ Favorita";
  }

  function toggleFavorite(path) {
    if (!path) return;
    if (pState.favorites.has(path)) pState.favorites.delete(path);
    else pState.favorites.add(path);
    saveFavorites();
    updateFavoriteButton();
    renderActiveLibraryView();
  }

  function updatePlayButtons(forcePlaying = null) {
    const el = activeMediaElement();
    const playing = forcePlaying !== null
      ? Boolean(forcePlaying)
      : Boolean(pState.currentTrack && el && !el.paused && !el.ended);
    els.playerPlayBtn.classList.toggle("is-playing", playing);
    els.playerPlayBtn.setAttribute("aria-pressed", String(playing));
    if (els.miniPlayerPlayBtn) {
      els.miniPlayerPlayBtn.textContent = playing ? "⏸" : "▶";
    }
  }

  function syncMiniPlayerVisibility() {
    if (!els.miniPlayer) return;
    const show = Boolean(pState.currentTrack && pState.prefs.miniPlayerEnabled && pState.activeView !== "player");
    els.miniPlayer.hidden = !show;
  }

  function togglePlayPause() {
    if (!pState.currentTrack) {
      const list = filteredLibraryItems();
      if (list.length > 0) playTrackItem(list[0], list);
      else if (pState.library.length > 0) playTrackItem(pState.library[0], pState.library);
      return;
    }
    ensureAudioGraph();
    const el = activeMediaElement();
    if (el.paused || el.ended) {
      el.play().then(() => {
        updatePlayButtons(true);
        startVisualizerLoop();
      }).catch(() => updatePlayButtons(false));
    } else {
      el.pause();
      updatePlayButtons(false);
    }
  }

  function playNext(fromEnded = false) {
    if (fromEnded && pState.sleepMode === "eot") {
      pState.sleepMode = "off";
      updateSleepBadge();
      updatePlayButtons(false);
      return;
    }
    if (pState.repeat === "one" && fromEnded && pState.currentTrack) {
      const el = activeMediaElement();
      el.currentTime = 0;
      el.play().then(() => updatePlayButtons(true)).catch(() => {});
      return;
    }
    const q = pState.queue.length ? pState.queue : pState.library;
    if (!q.length) return;
    if (fromEnded && !pState.prefs.autoAdvance && pState.repeat === "off") {
      updatePlayButtons(false);
      return;
    }

    let nextIdx;
    if (pState.shuffle && q.length > 1) {
      do {
        nextIdx = Math.floor(Math.random() * q.length);
      } while (nextIdx === pState.queueIndex);
    } else {
      nextIdx = pState.queueIndex + 1;
      if (nextIdx >= q.length) {
        if (pState.repeat === "all" || !fromEnded) nextIdx = 0;
        else {
          updatePlayButtons(false);
          return;
        }
      }
    }
    playTrackItem(q[nextIdx], q);
  }

  function playPrev() {
    const el = activeMediaElement();
    if (el && el.currentTime > 4) {
      el.currentTime = 0;
      return;
    }
    const q = pState.queue.length ? pState.queue : pState.library;
    if (!q.length) return;
    let prevIdx = pState.queueIndex - 1;
    if (prevIdx < 0) prevIdx = q.length - 1;
    playTrackItem(q[prevIdx], q);
  }

  function seekDelta(deltaSec) {
    if (!pState.currentTrack) return;
    const el = activeMediaElement();
    const dur = Number.isFinite(el.duration) ? el.duration : 0;
    el.currentTime = Math.max(0, Math.min(dur || 99999, (el.currentTime || 0) + deltaSec));
  }

  function updateMediaSession(item) {
    if (!("mediaSession" in navigator) || !item) return;
    try {
      const art = coverUrlFor(item);
      navigator.mediaSession.metadata = new MediaMetadata({
        title: item.title || item.filename,
        artist: item.artist || "!Download",
        album: item.album || "Juan Corporation",
        artwork: art ? [{ src: new URL(art, window.location.origin).href, sizes: "512x512", type: "image/jpeg" }] : [],
      });
      navigator.mediaSession.setActionHandler("play", togglePlayPause);
      navigator.mediaSession.setActionHandler("pause", togglePlayPause);
      navigator.mediaSession.setActionHandler("previoustrack", playPrev);
      navigator.mediaSession.setActionHandler("nexttrack", () => playNext(false));
      navigator.mediaSession.setActionHandler("seekbackward", () => seekDelta(-10));
      navigator.mediaSession.setActionHandler("seekforward", () => seekDelta(10));
    } catch {}
  }

  function cycleSpeed() {
    const cur = Number(pState.prefs.speed || 1);
    const idx = SPEED_STEPS.findIndex((s) => Math.abs(s - cur) < 0.01);
    const next = SPEED_STEPS[(idx + 1) % SPEED_STEPS.length];
    pState.prefs.speed = next;
    savePrefs();
    els.nativeAudioEl.playbackRate = next;
    els.nativeVideoEl.playbackRate = next;
    els.playerSpeedBtn.textContent = `${next}x`;
  }

  function cycleSleepTimer() {
    if (pState.sleepInterval) {
      clearInterval(pState.sleepInterval);
      pState.sleepInterval = null;
    }
    if (pState.sleepMode === "off") {
      pState.sleepMode = "timer";
      pState.sleepRemainingSec = 15 * 60;
    } else if (pState.sleepMode === "timer") {
      const mins = Math.ceil(pState.sleepRemainingSec / 60);
      const nextStep = SLEEP_STEPS.find((m) => m > mins);
      if (nextStep) pState.sleepRemainingSec = nextStep * 60;
      else {
        pState.sleepMode = "eot";
        pState.sleepRemainingSec = 0;
      }
    } else {
      pState.sleepMode = "off";
      pState.sleepRemainingSec = 0;
    }

    if (pState.sleepMode === "timer") {
      pState.sleepInterval = setInterval(() => {
        pState.sleepRemainingSec -= 1;
        if (pState.sleepRemainingSec <= 0) {
          clearInterval(pState.sleepInterval);
          pState.sleepInterval = null;
          pState.sleepMode = "off";
          els.nativeAudioEl.pause();
          els.nativeVideoEl.pause();
          updatePlayButtons(false);
        }
        updateSleepBadge();
      }, 1000);
    }
    updateSleepBadge();
  }

  function updateSleepBadge() {
    if (pState.sleepMode === "timer") {
      const txt = `⏱ ${formatTime(pState.sleepRemainingSec)}`;
      els.sleepTimerBadge.textContent = txt;
      els.sleepTimerBadge.hidden = false;
      els.playerSleepBtn.textContent = txt;
    } else if (pState.sleepMode === "eot") {
      els.sleepTimerBadge.textContent = "⏱ Fin de pista";
      els.sleepTimerBadge.hidden = false;
      els.playerSleepBtn.textContent = "Fin de pista";
    } else {
      els.sleepTimerBadge.hidden = true;
      els.playerSleepBtn.textContent = "Temporizador";
    }
  }

  function handleAbButton() {
    if (!pState.currentTrack) return;
    const el = activeMediaElement();
    if (pState.loopA === null) {
      pState.loopA = el.currentTime || 0;
      pState.loopB = null;
    } else if (pState.loopB === null) {
      const now = el.currentTime || 0;
      if (now > pState.loopA + 0.4) pState.loopB = now;
      else pState.loopA = null;
    } else {
      pState.loopA = null;
      pState.loopB = null;
    }
    updateAbLoopBadge();
  }

  function updateAbLoopBadge() {
    if (pState.loopA !== null && pState.loopB !== null) {
      els.abLoopBadge.textContent = `A-B ${formatTime(pState.loopA)}–${formatTime(pState.loopB)}`;
      els.abLoopBadge.hidden = false;
      els.playerAbBtn.textContent = "Quitar A-B";
    } else if (pState.loopA !== null) {
      els.abLoopBadge.textContent = `A: ${formatTime(pState.loopA)} → ?`;
      els.abLoopBadge.hidden = false;
      els.playerAbBtn.textContent = "Marcar B";
    } else {
      els.abLoopBadge.hidden = true;
      els.playerAbBtn.textContent = "Bucle A-B";
    }
  }

  function bindMediaEvents(el) {
    el.addEventListener("timeupdate", () => {
      if (el !== activeMediaElement()) return;
      const dur = Number.isFinite(el.duration) ? el.duration : 0;
      const cur = el.currentTime || 0;

      if (pState.loopA !== null && pState.loopB !== null && cur >= pState.loopB) {
        el.currentTime = pState.loopA;
      }

      if (!pState.seeking && dur > 0) {
        els.playerSeek.max = String(dur);
        els.playerSeek.value = String(cur);
      }
      els.playerCurrentTime.textContent = formatTime(cur);
      els.playerDuration.textContent = dur > 0 ? formatTime(dur) : formatTime(pState.currentTrack?.duration || 0);
      if (els.miniPlayerProgress && dur > 0) {
        els.miniPlayerProgress.style.width = `${Math.min(100, (cur / dur) * 100)}%`;
      }
      if (!el.paused && !els.playerPlayBtn.classList.contains("is-playing")) {
        updatePlayButtons(true);
      }
    });

    el.addEventListener("play", () => {
      if (el === activeMediaElement()) {
        updatePlayButtons(true);
        startVisualizerLoop();
      }
    });
    el.addEventListener("playing", () => {
      if (el === activeMediaElement()) {
        updatePlayButtons(true);
        startVisualizerLoop();
      }
    });
    el.addEventListener("pause", () => {
      if (el === activeMediaElement()) updatePlayButtons(false);
    });
    el.addEventListener("ended", () => {
      if (el === activeMediaElement()) playNext(true);
    });
  }

  // =========================================================================
  // Library, Albums, File Explorer, Device Auto-Scan & Sort
  // =========================================================================
  async function refreshLibrary() {
    try {
      const scope = pState.prefs.libraryScope === "app" ? "app" : "all";
      const [libResp, plResp] = await Promise.all([
        fetch(`/api/library/files?scope=${encodeURIComponent(scope)}`),
        fetch("/api/library/playlists"),
      ]);
      if (libResp.ok) {
        const libData = await libResp.json();
        pState.library = Array.isArray(libData.items) ? libData.items : [];
        pState.mediaPermissionGranted = libData.media_permission_granted !== false;
        if (pState.currentTrack) {
          const fresh = pState.library.find((i) => i.path === pState.currentTrack.path);
          if (fresh) {
            pState.currentTrack = fresh;
          }
        }
      }
      if (plResp.ok) {
        const plData = await plResp.json();
        pState.playlists = Array.isArray(plData.playlists) ? plData.playlists : [];
      }
      updateLibraryToolbarControls();
      renderActiveLibraryView();
      renderPlaylistsTab();
    } catch {}
  }

  function updateLibraryToolbarControls() {
    const hasDesktopFolderBtn = Boolean(window.pywebview && window.pywebview.api && window.pywebview.api.select_download_folder);
    els.addScanFolderBtn.hidden = !hasDesktopFolderBtn;
    els.androidMediaPermBanner.hidden = pState.mediaPermissionGranted || pState.prefs.libraryScope === "app";
    els.libraryScopeBtn.textContent = pState.prefs.libraryScope === "app" ? "Solo !Download" : "Todo el dispositivo";
    els.libraryScopeBtn.className = pState.prefs.libraryScope === "app" ? "apple-secondary-pill" : "apple-blue-pill";
    els.librarySortSelect.value = pState.prefs.sortBy || "recent";
  }

  function sortItems(items) {
    const mode = pState.prefs.sortBy || "recent";
    const arr = items.slice();
    if (mode === "title") {
      arr.sort((a, b) => (a.title || a.filename).localeCompare(b.title || b.filename));
    } else if (mode === "artist") {
      arr.sort((a, b) => (a.artist || "zzz").localeCompare(b.artist || "zzz") || (a.title || "").localeCompare(b.title || ""));
    } else if (mode === "album") {
      arr.sort((a, b) => (a.album || a.folder_group || "zzz").localeCompare(b.album || b.folder_group || "zzz"));
    } else if (mode === "duration") {
      arr.sort((a, b) => Number(b.duration || 0) - Number(a.duration || 0));
    } else {
      arr.sort((a, b) => Number(b.mtime || 0) - Number(a.mtime || 0));
    }
    return arr;
  }

  function filteredLibraryItems(onlyFavorites = false) {
    const q = pState.searchQuery.trim().toLowerCase();
    const filtered = pState.library.filter((item) => {
      if (onlyFavorites && !pState.favorites.has(item.path)) return false;
      if (pState.filterKind !== "all" && item.kind !== pState.filterKind) return false;
      if (!q) return true;
      const hay = `${item.title} ${item.artist} ${item.album} ${item.filename} ${item.folder_path || ""} ${item.folder_group || ""}`.toLowerCase();
      return hay.includes(q);
    });
    return sortItems(filtered);
  }

  function renderTrackRow(item, queueList) {
    const row = document.createElement("div");
    row.className = "inset-row library-row";
    if (pState.currentTrack && pState.currentTrack.path === item.path) {
      row.classList.add("is-selected");
    }

    const artWrap = document.createElement("button");
    artWrap.type = "button";
    artWrap.className = `library-thumb-sq ${item.kind === "video" ? "sf-blue" : "sf-pink"}`;
    const covUrl = coverUrlFor(item);
    if (covUrl) {
      const img = document.createElement("img");
      img.src = covUrl;
      img.alt = "";
      img.loading = "lazy";
      img.onerror = () => { img.remove(); artWrap.textContent = item.kind === "video" ? "🎬" : "♪"; };
      artWrap.appendChild(img);
    } else {
      artWrap.textContent = item.kind === "video" ? "🎬" : "♪";
    }
    artWrap.addEventListener("click", () => playTrackItem(item, queueList));

    const main = document.createElement("button");
    main.type = "button";
    main.className = "inset-row-main library-row-main-btn";
    const title = document.createElement("span");
    title.className = "inset-row-title";
    title.textContent = item.title || item.filename;
    const sub = document.createElement("span");
    sub.className = "inset-row-sub";
    const subParts = [];
    if (item.artist) subParts.push(item.artist);
    if (item.duration) subParts.push(formatTime(item.duration));
    subParts.push(item.ext);
    if (item.folder_group) subParts.push(item.folder_group);
    else if (item.source === "imported") subParts.push("Importada");
    sub.textContent = subParts.join(" · ");
    main.append(title, sub);
    main.addEventListener("click", () => playTrackItem(item, queueList));

    const actions = document.createElement("div");
    actions.className = "library-row-actions";

    const favBtn = document.createElement("button");
    favBtn.type = "button";
    const isFav = pState.favorites.has(item.path);
    favBtn.className = `fav-heart-btn ${isFav ? "is-fav" : ""}`;
    favBtn.textContent = isFav ? "♥" : "♡";
    favBtn.title = "Favorito";
    favBtn.addEventListener("click", () => toggleFavorite(item.path));
    actions.appendChild(favBtn);

    const addPlBtn = document.createElement("button");
    addPlBtn.type = "button";
    addPlBtn.className = "apple-secondary-pill";
    addPlBtn.textContent = "+ Lista";
    addPlBtn.addEventListener("click", () => openAddToPlaylistModal(item));
    actions.appendChild(addPlBtn);

    if (item.kind === "audio") {
      const metaBtn = document.createElement("button");
      metaBtn.type = "button";
      metaBtn.className = "apple-secondary-pill";
      metaBtn.textContent = "Metadatos";
      metaBtn.addEventListener("click", () => openMetadataModal(item));
      actions.appendChild(metaBtn);
    }

    row.append(artWrap, main, actions);
    return row;
  }

  function renderActiveLibraryView() {
    const mode = pState.libraryViewMode;
    els.libraryViewPills.querySelectorAll("[data-lib-view]").forEach((btn) => {
      btn.className = btn.getAttribute("data-lib-view") === mode ? "apple-blue-pill" : "apple-secondary-pill";
    });

    els.folderBrowserView.hidden = mode !== "folders";
    els.albumsBrowserView.hidden = mode !== "albums";
    els.libraryListGroup.hidden = true;
    els.libraryEmptyState.hidden = true;

    if (mode === "folders") {
      renderFolderExplorer();
    } else if (mode === "albums") {
      renderAlbumsView();
    } else {
      const items = filteredLibraryItems(mode === "favorites");
      els.libraryListGroup.hidden = items.length === 0;
      els.libraryEmptyState.hidden = items.length > 0;
      els.libraryList.innerHTML = "";
      items.forEach((item) => els.libraryList.appendChild(renderTrackRow(item, items)));
    }
  }

  function renderFolderExplorer() {
    const baseItems = filteredLibraryItems(false);
    if (!baseItems.length) {
      els.folderBrowserView.hidden = true;
      els.libraryEmptyState.hidden = false;
      return;
    }

    const prefix = pState.currentFolderPath;
    const prefixSegs = prefix ? prefix.split("/").filter(Boolean) : [];

    // Breadcrumbs
    els.folderBreadcrumbs.innerHTML = "";
    const homeCrumb = document.createElement("button");
    homeCrumb.type = "button";
    homeCrumb.className = `crumb-btn ${prefixSegs.length === 0 ? "is-current" : ""}`;
    homeCrumb.textContent = "Inicio";
    homeCrumb.addEventListener("click", () => {
      pState.currentFolderPath = "";
      renderFolderExplorer();
    });
    els.folderBreadcrumbs.appendChild(homeCrumb);

    let accPath = "";
    prefixSegs.forEach((seg, i) => {
      const sep = document.createElement("span");
      sep.className = "crumb-sep";
      sep.textContent = "›";
      els.folderBreadcrumbs.appendChild(sep);

      accPath = accPath ? `${accPath}/${seg}` : seg;
      const target = accPath;
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = `crumb-btn ${i === prefixSegs.length - 1 ? "is-current" : ""}`;
      btn.textContent = seg;
      btn.addEventListener("click", () => {
        pState.currentFolderPath = target;
        renderFolderExplorer();
      });
      els.folderBreadcrumbs.appendChild(btn);
    });

    const childFolders = new Map();
    const directFiles = [];
    const recursiveFiles = [];

    baseItems.forEach((item) => {
      const rawFp = String(item.folder_path || item.folder_group || "!Download").replace(/\\/g, "/");
      const segs = rawFp.split("/").filter(Boolean);
      const matchesPrefix = prefixSegs.every((s, idx) => segs[idx] === s);
      if (!matchesPrefix) return;

      recursiveFiles.push(item);
      if (segs.length === prefixSegs.length) {
        directFiles.push(item);
      } else {
        const nextFolderName = segs[prefixSegs.length];
        const nextPath = [...prefixSegs, nextFolderName].join("/");
        if (!childFolders.has(nextPath)) {
          childFolders.set(nextPath, { name: nextFolderName, path: nextPath, items: [] });
        }
        childFolders.get(nextPath).items.push(item);
      }
    });

    els.playFolderAllBtn.hidden = recursiveFiles.length === 0;
    els.playFolderShuffleBtn.hidden = recursiveFiles.length === 0;
    els.playFolderAllBtn.onclick = () => playTrackItem(recursiveFiles[0], recursiveFiles);
    els.playFolderShuffleBtn.onclick = () => {
      pState.shuffle = true;
      els.playerShuffleBtn.classList.add("is-active");
      playTrackItem(recursiveFiles[Math.floor(Math.random() * recursiveFiles.length)], recursiveFiles);
    };

    els.folderCardsGrid.innerHTML = "";
    const sortedFolders = Array.from(childFolders.values()).sort((a, b) => a.name.localeCompare(b.name));
    sortedFolders.forEach((folder) => {
      const card = document.createElement("button");
      card.type = "button";
      card.className = "folder-card";

      const thumb = document.createElement("div");
      thumb.className = "folder-card-thumb";
      const covItem = folder.items.find((it) => it.has_cover);
      if (covItem) {
        const img = document.createElement("img");
        img.src = coverUrlFor(covItem);
        img.alt = "";
        img.loading = "lazy";
        thumb.appendChild(img);
      } else {
        thumb.textContent = "📁";
      }

      const copy = document.createElement("div");
      copy.className = "folder-card-copy";
      const title = document.createElement("strong");
      title.textContent = folder.name;
      const sub = document.createElement("span");
      sub.textContent = `${folder.items.length} elemento${folder.items.length === 1 ? "" : "s"}`;
      copy.append(title, sub);

      card.append(thumb, copy);
      card.addEventListener("click", () => {
        pState.currentFolderPath = folder.path;
        renderFolderExplorer();
      });
      els.folderCardsGrid.appendChild(card);
    });

    els.folderTracksGroup.hidden = directFiles.length === 0;
    els.folderTracksList.innerHTML = "";
    directFiles.forEach((item) => els.folderTracksList.appendChild(renderTrackRow(item, recursiveFiles)));
  }

  function renderAlbumsView() {
    const items = filteredLibraryItems(false);
    if (!items.length) {
      els.albumsBrowserView.hidden = true;
      els.libraryEmptyState.hidden = false;
      return;
    }

    const albums = new Map();
    items.forEach((item) => {
      if (item.kind !== "audio" && !item.album) return;
      const key = item.album || item.folder_group || "Sencillos";
      if (!albums.has(key)) {
        albums.set(key, {
          key,
          title: key,
          artist: item.artist || "",
          items: [],
        });
      }
      const grp = albums.get(key);
      grp.items.push(item);
      if (!grp.artist && item.artist) grp.artist = item.artist;
    });

    if (pState.selectedAlbumKey && albums.has(pState.selectedAlbumKey)) {
      const alb = albums.get(pState.selectedAlbumKey);
      els.albumsCardsGrid.hidden = true;
      els.albumDetailView.hidden = false;
      els.albumDetailTitle.textContent = alb.title;
      els.albumDetailSub.textContent = `${alb.artist || "Varios artistas"} · ${alb.items.length} pistas`;
      els.albumTracksList.innerHTML = "";
      alb.items.forEach((t) => els.albumTracksList.appendChild(renderTrackRow(t, alb.items)));
      els.playAlbumAllBtn.onclick = () => playTrackItem(alb.items[0], alb.items);
      els.playAlbumShuffleBtn.onclick = () => {
        pState.shuffle = true;
        els.playerShuffleBtn.classList.add("is-active");
        playTrackItem(alb.items[Math.floor(Math.random() * alb.items.length)], alb.items);
      };
      return;
    }

    pState.selectedAlbumKey = null;
    els.albumDetailView.hidden = true;
    els.albumsCardsGrid.hidden = false;
    els.albumsCardsGrid.innerHTML = "";

    Array.from(albums.values())
      .sort((a, b) => a.title.localeCompare(b.title))
      .forEach((alb) => {
        const card = document.createElement("button");
        card.type = "button";
        card.className = "album-card";

        const art = document.createElement("div");
        art.className = "album-card-art";
        const covItem = alb.items.find((it) => it.has_cover);
        if (covItem) {
          const img = document.createElement("img");
          img.src = coverUrlFor(covItem);
          img.alt = "";
          img.loading = "lazy";
          art.appendChild(img);
        } else {
          art.textContent = "♫";
        }

        const t = document.createElement("strong");
        t.textContent = alb.title;
        const s = document.createElement("span");
        s.textContent = `${alb.artist || "Álbum"} · ${alb.items.length}`;
        card.append(art, t, s);
        card.addEventListener("click", () => {
          pState.selectedAlbumKey = alb.key;
          renderAlbumsView();
        });
        els.albumsCardsGrid.appendChild(card);
      });
  }

  async function importExternalFiles(openTaggerAfter = false) {
    if (window.pywebview && window.pywebview.api && typeof window.pywebview.api.select_media_files === "function") {
      try {
        const chosen = await window.pywebview.api.select_media_files();
        if (!Array.isArray(chosen) || chosen.length === 0) return;
        const resp = await fetch("/api/library/register", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ paths: chosen }),
        });
        const data = await resp.json().catch(() => ({}));
        await refreshLibrary();
        const added = Array.isArray(data.added) ? data.added : [];
        if (openTaggerAfter && added.length > 0) {
          const firstAudio = added.find((a) => a.kind === "audio");
          if (firstAudio) openMetadataModal(firstAudio);
        }
      } catch {}
      return;
    }
    pState.metaOpenTagOnImport = openTaggerAfter;
    els.importMediaInput.value = "";
    els.importMediaInput.click();
  }

  async function handleFileInputUpload(fileList) {
    const files = Array.from(fileList || []);
    if (!files.length) return;
    let firstAudio = null;
    for (const file of files) {
      try {
        const resp = await fetch("/api/library/upload", {
          method: "POST",
          headers: {
            "X-Filename": encodeURIComponent(file.name),
            "Content-Type": file.type || "application/octet-stream",
          },
          body: file,
        });
        const data = await resp.json().catch(() => ({}));
        if (resp.ok && data.item && data.item.kind === "audio" && !firstAudio) {
          firstAudio = data.item;
        }
      } catch {}
    }
    await refreshLibrary();
    if (pState.metaOpenTagOnImport && firstAudio) {
      pState.metaOpenTagOnImport = false;
      openMetadataModal(firstAudio);
    }
    pState.metaOpenTagOnImport = false;
  }

  // =========================================================================
  // Playlists & Queue Sheet
  // =========================================================================
  function renderPlaylistsTab() {
    els.customPlaylistsList.innerHTML = "";
    if (!pState.playlists.length) {
      const emptyRow = document.createElement("div");
      emptyRow.className = "inset-row";
      emptyRow.innerHTML = '<div class="inset-row-main"><span class="inset-row-title">Aún no tienes listas personalizadas</span><span class="inset-row-sub">Crea una lista de Audio, Video o Mixta arriba, o usa "+ Lista" en Biblioteca.</span></div>';
      els.customPlaylistsList.appendChild(emptyRow);
    } else {
      pState.playlists.forEach((pl) => {
        const row = document.createElement("button");
        row.type = "button";
        row.className = "inset-row";
        if (pl.id === pState.selectedPlaylistId) row.classList.add("is-selected");

        const icon = document.createElement("span");
        icon.className = `sf-squircle sf-sm ${pl.kind === "video" ? "sf-blue" : pl.kind === "audio" ? "sf-pink" : "sf-indigo"}`;
        icon.textContent = pl.kind === "video" ? "🎬" : "♫";

        const main = document.createElement("div");
        main.className = "inset-row-main";
        const t = document.createElement("span");
        t.className = "inset-row-title";
        t.textContent = pl.name;
        const s = document.createElement("span");
        s.className = "inset-row-sub";
        const kindLabel = pl.kind === "video" ? "Video" : pl.kind === "audio" ? "Audio" : "Mixta";
        s.textContent = `${kindLabel} · ${(pl.items || []).length} elementos`;
        main.append(t, s);

        row.append(icon, main);
        row.addEventListener("click", () => {
          pState.selectedPlaylistId = pl.id;
          renderPlaylistsTab();
        });
        els.customPlaylistsList.appendChild(row);
      });
    }

    const activePl = pState.playlists.find((p) => p.id === pState.selectedPlaylistId) || null;
    els.playlistDetailView.hidden = !activePl;
    if (activePl) renderPlaylistDetail(activePl);

    const groups = new Map();
    pState.library.forEach((item) => {
      if (item.source === "downloaded" && item.folder_group) {
        if (!groups.has(item.folder_group)) groups.set(item.folder_group, []);
        groups.get(item.folder_group).push(item);
      }
    });
    els.folderCollectionsSection.hidden = groups.size === 0;
    els.folderCollectionsList.innerHTML = "";
    groups.forEach((groupItems, groupName) => {
      const sorted = groupItems.slice().sort((a, b) => a.filename.localeCompare(b.filename));
      const row = document.createElement("div");
      row.className = "inset-row";
      const main = document.createElement("div");
      main.className = "inset-row-main";
      const t = document.createElement("span");
      t.className = "inset-row-title";
      t.textContent = groupName;
      const s = document.createElement("span");
      s.className = "inset-row-sub";
      s.textContent = `${sorted.length} elementos guardados en carpeta`;
      main.append(t, s);

      const playBtn = document.createElement("button");
      playBtn.type = "button";
      playBtn.className = "apple-blue-pill";
      playBtn.textContent = "Reproducir";
      playBtn.addEventListener("click", () => playTrackItem(sorted[0], sorted));
      row.append(main, playBtn);
      els.folderCollectionsList.appendChild(row);
    });
  }

  function resolvePlaylistTracks(pl) {
    const byPath = new Map(pState.library.map((i) => [i.path, i]));
    return (pl.items || []).map((p) => byPath.get(p)).filter(Boolean);
  }

  function renderPlaylistDetail(pl) {
    els.playlistDetailTitle.textContent = `${pl.name} (${(pl.items || []).length})`;
    els.playlistDetailItems.innerHTML = "";
    const tracks = resolvePlaylistTracks(pl);

    if (!tracks.length) {
      const empty = document.createElement("div");
      empty.className = "inset-row";
      empty.innerHTML = '<div class="inset-row-main"><span class="inset-row-title">Lista vacía</span><span class="inset-row-sub">Ve a Biblioteca y pulsa "+ Lista" en las pistas que quieras agregar.</span></div>';
      els.playlistDetailItems.appendChild(empty);
      return;
    }

    tracks.forEach((item, idx) => {
      const row = document.createElement("div");
      row.className = "inset-row";
      const idxPill = document.createElement("span");
      idxPill.className = "playlist-index-pill";
      idxPill.textContent = String(idx + 1);

      const main = document.createElement("button");
      main.type = "button";
      main.className = "inset-row-main library-row-main-btn";
      const t = document.createElement("span");
      t.className = "inset-row-title";
      t.textContent = item.title || item.filename;
      const s = document.createElement("span");
      s.className = "inset-row-sub";
      s.textContent = [item.artist, item.ext, item.duration ? formatTime(item.duration) : ""].filter(Boolean).join(" · ");
      main.append(t, s);
      main.addEventListener("click", () => playTrackItem(item, tracks));

      const acts = document.createElement("div");
      acts.className = "library-row-actions";
      if (idx > 0) {
        const up = document.createElement("button");
        up.type = "button";
        up.className = "circle-action-outline";
        up.textContent = "↑";
        up.addEventListener("click", () => reorderPlaylistItem(pl, idx, idx - 1));
        acts.appendChild(up);
      }
      if (idx < tracks.length - 1) {
        const down = document.createElement("button");
        down.type = "button";
        down.className = "circle-action-outline";
        down.textContent = "↓";
        down.addEventListener("click", () => reorderPlaylistItem(pl, idx, idx + 1));
        acts.appendChild(down);
      }
      const rem = document.createElement("button");
      rem.type = "button";
      rem.className = "circle-action-outline";
      rem.textContent = "✕";
      rem.addEventListener("click", () => removePlaylistItem(pl, idx));
      acts.appendChild(rem);

      row.append(idxPill, main, acts);
      els.playlistDetailItems.appendChild(row);
    });
  }

  async function reorderPlaylistItem(pl, fromIdx, toIdx) {
    const next = (pl.items || []).slice();
    const [moved] = next.splice(fromIdx, 1);
    next.splice(toIdx, 0, moved);
    await updatePlaylistRemote(pl.id, { items: next });
  }

  async function removePlaylistItem(pl, idx) {
    const next = (pl.items || []).slice();
    next.splice(idx, 1);
    await updatePlaylistRemote(pl.id, { items: next });
  }

  async function updatePlaylistRemote(id, patch) {
    const resp = await fetch(`/api/library/playlists/${encodeURIComponent(id)}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(patch),
    });
    if (resp.ok) await refreshLibrary();
  }

  function openQueueModal() {
    els.queueList.innerHTML = "";
    const q = pState.queue.length ? pState.queue : [];
    els.queueCountSub.textContent = `${q.length} elemento${q.length === 1 ? "" : "s"} en cola`;
    if (!q.length) {
      els.queueList.innerHTML = '<div class="inset-row"><div class="inset-row-main"><span class="inset-row-title">Cola vacía</span><span class="inset-row-sub">Reproduce una pista o carpeta para llenar la cola.</span></div></div>';
    } else {
      q.forEach((item, idx) => {
        const row = document.createElement("div");
        row.className = "inset-row";
        if (idx === pState.queueIndex) row.classList.add("is-selected");
        const num = document.createElement("span");
        num.className = "playlist-index-pill";
        num.textContent = idx === pState.queueIndex ? "▶" : String(idx + 1);
        const main = document.createElement("button");
        main.type = "button";
        main.className = "inset-row-main library-row-main-btn";
        main.innerHTML = `<span class="inset-row-title">${escapeHtml(item.title || item.filename)}</span><span class="inset-row-sub">${escapeHtml([item.artist, item.ext].filter(Boolean).join(" · "))}</span>`;
        main.addEventListener("click", () => {
          playTrackItem(item, q);
          openQueueModal();
        });
        const rm = document.createElement("button");
        rm.type = "button";
        rm.className = "circle-action-outline";
        rm.textContent = "✕";
        rm.addEventListener("click", () => {
          pState.queue.splice(idx, 1);
          if (idx < pState.queueIndex) pState.queueIndex -= 1;
          openQueueModal();
        });
        row.append(num, main, rm);
        els.queueList.appendChild(row);
      });
    }
    els.queueModal.hidden = false;
  }

  function openAddToPlaylistModal(item) {
    pState.addToPlTrackPath = item.path;
    els.addToPlTrackName.textContent = `${item.title || item.filename} (${item.kind === "video" ? "Video" : "Audio"})`;
    els.addToPlList.innerHTML = "";
    pState.playlists.forEach((pl) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "inset-row";
      const already = (pl.items || []).includes(item.path);
      if (already) btn.classList.add("is-selected");
      const main = document.createElement("div");
      main.className = "inset-row-main";
      main.innerHTML = `<span class="inset-row-title">${escapeHtml(pl.name)}</span><span class="inset-row-sub">${(pl.items || []).length} elementos${already ? " · Ya agregada" : ""}</span>`;
      btn.appendChild(main);
      btn.addEventListener("click", async () => {
        if (!already) await updatePlaylistRemote(pl.id, { items: [...(pl.items || []), item.path] });
        els.addToPlaylistModal.hidden = true;
      });
      els.addToPlList.appendChild(btn);
    });
    els.addToPlaylistModal.hidden = false;
  }

  // =========================================================================
  // Equalizer UI & Presets
  // =========================================================================
  function renderEqUI() {
    els.eqEnabledSwitch.checked = Boolean(pState.prefs.eqEnabled);
    els.eqLimiterSwitch.checked = Boolean(pState.prefs.eqLimiter);
    els.eqPreampSlider.value = String(pState.prefs.eqPreamp || 0);
    els.eqPreampVal.textContent = `${Number(pState.prefs.eqPreamp || 0) > 0 ? "+" : ""}${Number(pState.prefs.eqPreamp || 0).toFixed(1)} dB`;

    els.eqPresetsRow.innerHTML = "";
    Object.entries(EQ_PRESETS).forEach(([key, preset]) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = pState.prefs.eqPreset === key ? "apple-blue-pill" : "apple-secondary-pill";
      btn.textContent = preset.name;
      btn.addEventListener("click", () => applyEqPreset(key));
      els.eqPresetsRow.appendChild(btn);
    });

    els.eqBandsGrid.innerHTML = "";
    EQ_FREQS.forEach((_, idx) => {
      const val = Number(pState.prefs.eqGains[idx] || 0);
      const col = document.createElement("div");
      col.className = "eq-band-col";

      const dbLabel = document.createElement("span");
      dbLabel.className = "eq-band-db";
      dbLabel.textContent = `${val > 0 ? "+" : ""}${val.toFixed(0)}`;

      const slider = document.createElement("input");
      slider.type = "range";
      slider.min = "-12";
      slider.max = "12";
      slider.step = "0.5";
      slider.value = String(val);
      slider.className = "eq-band-slider";
      slider.setAttribute("aria-label", `${EQ_LABELS[idx]} Hz`);
      slider.addEventListener("input", () => {
        ensureAudioGraph();
        const nextVal = Number(slider.value);
        pState.prefs.eqGains[idx] = nextVal;
        pState.prefs.eqPreset = "custom";
        dbLabel.textContent = `${nextVal > 0 ? "+" : ""}${nextVal.toFixed(0)}`;
        savePrefs();
        syncEqAudioNodes();
        highlightPresetChip("custom");
      });

      const freqLabel = document.createElement("span");
      freqLabel.className = "eq-band-freq";
      freqLabel.textContent = EQ_LABELS[idx];

      col.append(dbLabel, slider, freqLabel);
      els.eqBandsGrid.appendChild(col);
    });
  }

  function highlightPresetChip(activeKey) {
    const keys = Object.keys(EQ_PRESETS);
    Array.from(els.eqPresetsRow.children).forEach((btn, idx) => {
      btn.className = keys[idx] === activeKey ? "apple-blue-pill" : "apple-secondary-pill";
    });
  }

  function applyEqPreset(key) {
    const preset = EQ_PRESETS[key];
    if (!preset) return;
    ensureAudioGraph();
    pState.prefs.eqPreset = key;
    if (key !== "custom") {
      pState.prefs.eqPreamp = preset.preamp;
      pState.prefs.eqGains = preset.gains.slice();
    }
    pState.prefs.eqEnabled = true;
    savePrefs();
    syncEqAudioNodes();
    renderEqUI();
  }

  function applyQuickTweak(tweak) {
    if (tweak === "more_bass") applyEqPreset("bass_boost");
    else if (tweak === "more_treble") applyEqPreset("treble_clarity");
    else if (tweak === "clear_vocals") applyEqPreset("vocal");
    else if (tweak === "warm") {
      ensureAudioGraph();
      pState.prefs.eqPreset = "custom";
      pState.prefs.eqEnabled = true;
      pState.prefs.eqPreamp = -1.5;
      pState.prefs.eqGains = [3.5, 4, 3, 1.5, 0, 0, -0.5, -1, -1.5, -2];
      savePrefs();
      syncEqAudioNodes();
      renderEqUI();
    }
  }

  function applyPlayerCustomStyles() {
    const accent = pState.prefs.accentColor || "#ff2d55";
    document.documentElement.style.setProperty("--player-accent", accent);
    els.playerAccentSwatches.querySelectorAll(".accent-swatch").forEach((sw) => {
      sw.classList.toggle("is-active", sw.getAttribute("data-accent") === accent);
    });
    els.visualizerStylePills.querySelectorAll("[data-vis-style]").forEach((btn) => {
      btn.className = btn.getAttribute("data-vis-style") === pState.prefs.visualizerStyle ? "apple-blue-pill" : "apple-secondary-pill";
    });
    els.prefAmbientBg.checked = Boolean(pState.prefs.ambientBg);
    els.prefAutoAdvance.checked = Boolean(pState.prefs.autoAdvance);
    els.prefMiniPlayer.checked = Boolean(pState.prefs.miniPlayerEnabled);
    if (pState.currentTrack) {
      els.playerAmbientBg.hidden = !(pState.prefs.ambientBg && pState.currentTrack.has_cover);
    }
    syncMiniPlayerVisibility();
  }

  // =========================================================================
  // Metadata Tagger Modal (Manual + Auto)
  // =========================================================================
  function setMetaStatus(msg, isError = false) {
    if (!msg) {
      els.metaStatusMsg.hidden = true;
      return;
    }
    els.metaStatusMsg.textContent = msg;
    els.metaStatusMsg.className = `meta-status-msg ${isError ? "is-error" : "is-ok"}`;
    els.metaStatusMsg.hidden = false;
  }

  function setCoverPreviewSrc(src) {
    if (src) {
      els.metaCoverPreview.src = src;
      els.metaCoverPreview.hidden = false;
      els.metaCoverEmpty.hidden = true;
    } else {
      els.metaCoverPreview.hidden = true;
      els.metaCoverEmpty.hidden = false;
    }
  }

  function openMetadataModal(item) {
    pState.metaTargetItem = item;
    pState.metaCoverBase64 = null;
    els.metaTargetFileName.textContent = item.filename || item.path;
    els.metaTitle.value = item.title || "";
    els.metaArtist.value = item.artist || "";
    els.metaAlbum.value = item.album || "";
    els.metaYear.value = item.year || "";
    els.metaTrack.value = item.track || "";
    els.metaGenre.value = item.genre || "";
    els.metaCoverUrl.value = "";
    els.metaAutoQuery.value = [item.artist, item.title || item.filename].filter(Boolean).join(" ").trim();
    els.metaAutoResults.innerHTML = "";
    els.metaAutoResults.hidden = true;
    setMetaStatus("");
    setCoverPreviewSrc(coverUrlFor(item, true));
    els.metadataModal.hidden = false;
  }

  async function searchMetadataAuto() {
    const q = els.metaAutoQuery.value.trim();
    if (!q) {
      setMetaStatus("Escribe un título o artista para buscar.", true);
      return;
    }
    setMetaStatus("");
    els.metaAutoSearchBtn.disabled = true;
    els.metaAutoSearchBtn.textContent = "Buscando...";
    try {
      const resp = await fetch("/api/library/metadata/auto", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: q, limit: 6 }),
      });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) throw new Error(data.detail || "No se pudo completar la búsqueda.");
      const results = Array.isArray(data.results) ? data.results : [];
      els.metaAutoResults.innerHTML = "";
      if (!results.length) {
        els.metaAutoResults.hidden = true;
        setMetaStatus("Sin coincidencias automáticas. Ajusta la búsqueda o edita manualmente.", true);
        return;
      }
      results.forEach((cand) => {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "meta-cand-row";
        const img = document.createElement("img");
        img.src = cand.cover_url ? `/api/thumbnail?url=${encodeURIComponent(cand.cover_url)}` : "/static/icon.png";
        img.alt = "";
        const copy = document.createElement("div");
        copy.className = "meta-cand-copy";
        copy.innerHTML = `<strong>${escapeHtml(cand.title)}</strong><span>${escapeHtml([cand.artist, cand.album, cand.year].filter(Boolean).join(" · "))}</span>`;
        btn.append(img, copy);
        btn.addEventListener("click", () => {
          els.metaTitle.value = cand.title || "";
          els.metaArtist.value = cand.artist || "";
          els.metaAlbum.value = cand.album || "";
          els.metaYear.value = cand.year || "";
          els.metaGenre.value = cand.genre || "";
          els.metaTrack.value = cand.track || "";
          els.metaCoverUrl.value = cand.cover_url || "";
          pState.metaCoverBase64 = null;
          if (cand.cover_url) setCoverPreviewSrc(`/api/thumbnail?url=${encodeURIComponent(cand.cover_url)}`);
          setMetaStatus("Campos rellenados automáticamente. Pulsa \"Aplicar metadatos al archivo\" para guardar.", false);
        });
        els.metaAutoResults.appendChild(btn);
      });
      els.metaAutoResults.hidden = false;
    } catch (err) {
      setMetaStatus(err instanceof Error ? err.message : "Error de red al buscar metadatos.", true);
    } finally {
      els.metaAutoSearchBtn.disabled = false;
      els.metaAutoSearchBtn.textContent = "Buscar auto";
    }
  }

  async function applyMetadataChanges() {
    if (!pState.metaTargetItem) return;
    els.metaApplyBtn.disabled = true;
    els.metaApplyBtn.textContent = "Guardando etiquetas...";
    setMetaStatus("");
    try {
      const hasCoverInput = Boolean(els.metaCoverUrl.value.trim() || pState.metaCoverBase64);
      const resp = await fetch("/api/library/metadata/apply", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          path: pState.metaTargetItem.path,
          title: els.metaTitle.value,
          artist: els.metaArtist.value,
          album: els.metaAlbum.value,
          year: els.metaYear.value,
          genre: els.metaGenre.value,
          track: els.metaTrack.value,
          cover_url: els.metaCoverUrl.value.trim() || null,
          cover_base64: pState.metaCoverBase64,
        }),
      });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) throw new Error(data.detail || "No se pudieron aplicar los metadatos.");
      const updated = data.item;
      const oldPath = pState.metaTargetItem.path;
      if (updated) {
        if (hasCoverInput || updated.has_cover) {
          updated.has_cover = true;
          pState.coverBustMap.set(updated.path, Date.now());
        }
        pState.metaTargetItem = updated;
        if (pState.currentTrack && (pState.currentTrack.path === oldPath || pState.currentTrack.path === updated.path)) {
          pState.currentTrack = updated;
          updateNowPlayingUI(updated, true);
          updateMediaSession(updated);
        }
        setCoverPreviewSrc(coverUrlFor(updated, true));
      }
      await refreshLibrary();
      setMetaStatus("✓ Metadatos y carátula guardados correctamente.", false);
    } catch (err) {
      setMetaStatus(err instanceof Error ? err.message : "Error al guardar metadatos.", true);
    } finally {
      els.metaApplyBtn.disabled = false;
      els.metaApplyBtn.textContent = "Aplicar metadatos al archivo";
    }
  }

  function escapeHtml(str) {
    return String(str || "").replace(/[&<>"']/g, (ch) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;",
    }[ch]));
  }

  function switchSubtab(tab) {
    pState.activeSubtab = tab;
    els.playerSubtabs.querySelectorAll("[data-player-tab]").forEach((btn) => {
      btn.classList.toggle("is-active", btn.getAttribute("data-player-tab") === tab);
    });
    document.querySelectorAll("[data-player-panel]").forEach((panel) => {
      panel.hidden = panel.getAttribute("data-player-panel") !== tab;
    });
  }

  // =========================================================================
  // Event Listeners
  // =========================================================================
  bindMediaEvents(els.nativeAudioEl);
  bindMediaEvents(els.nativeVideoEl);

  els.playerPlayBtn.addEventListener("click", togglePlayPause);
  els.miniPlayerPlayBtn.addEventListener("click", togglePlayPause);
  els.playerPrevBtn.addEventListener("click", playPrev);
  els.playerNextBtn.addEventListener("click", () => playNext(false));
  els.miniPlayerNextBtn.addEventListener("click", () => playNext(false));
  els.playerBack10Btn.addEventListener("click", () => seekDelta(-10));
  els.playerFwd10Btn.addEventListener("click", () => seekDelta(10));

  els.playerShuffleBtn.addEventListener("click", () => {
    pState.shuffle = !pState.shuffle;
    els.playerShuffleBtn.classList.toggle("is-active", pState.shuffle);
  });

  els.playerRepeatBtn.addEventListener("click", () => {
    const order = ["off", "all", "one"];
    pState.repeat = order[(order.indexOf(pState.repeat) + 1) % order.length];
    els.playerRepeatBtn.classList.toggle("is-active", pState.repeat !== "off");
    els.playerRepeatBtn.title = pState.repeat === "one" ? "Repetir pista (1)" : pState.repeat === "all" ? "Repetir lista" : "No repetir";
  });

  els.playerSeek.addEventListener("input", () => {
    pState.seeking = true;
    els.playerCurrentTime.textContent = formatTime(Number(els.playerSeek.value));
  });
  els.playerSeek.addEventListener("change", () => {
    if (pState.currentTrack) activeMediaElement().currentTime = Number(els.playerSeek.value);
    pState.seeking = false;
  });

  els.playerVolume.value = String(pState.prefs.volume ?? 1);
  els.playerVolume.addEventListener("input", () => {
    const val = Number(els.playerVolume.value);
    pState.prefs.volume = val;
    pState.muted = val === 0;
    savePrefs();
    els.nativeAudioEl.volume = val;
    els.nativeVideoEl.volume = val;
  });
  els.playerMuteBtn.addEventListener("click", () => {
    pState.muted = !pState.muted;
    const v = pState.muted ? 0 : Number(pState.prefs.volume || 1);
    els.nativeAudioEl.volume = v;
    els.nativeVideoEl.volume = v;
    els.playerMuteBtn.classList.toggle("is-active", pState.muted);
  });

  els.playerFavBtn.addEventListener("click", () => {
    if (pState.currentTrack) toggleFavorite(pState.currentTrack.path);
  });
  els.playerSpeedBtn.textContent = `${pState.prefs.speed || 1}x`;
  els.playerSpeedBtn.addEventListener("click", cycleSpeed);
  els.playerSleepBtn.addEventListener("click", cycleSleepTimer);
  els.playerAbBtn.addEventListener("click", handleAbButton);
  els.playerQueueBtn.addEventListener("click", openQueueModal);
  els.closeQueueModalBtn.addEventListener("click", () => { els.queueModal.hidden = true; });
  els.clearQueueBtn.addEventListener("click", () => {
    pState.queue = pState.currentTrack ? [pState.currentTrack] : [];
    pState.queueIndex = pState.currentTrack ? 0 : -1;
    openQueueModal();
  });

  els.playerTagCurrentBtn.addEventListener("click", () => {
    if (pState.currentTrack && pState.currentTrack.kind === "audio") openMetadataModal(pState.currentTrack);
  });

  if (els.pipBtn) {
    els.pipBtn.addEventListener("click", async () => {
      try {
        if (document.pictureInPictureElement) await document.exitPictureInPicture();
        else if (els.nativeVideoEl.requestPictureInPicture) await els.nativeVideoEl.requestPictureInPicture();
      } catch {}
    });
  }
  if (els.videoFullscreenBtn) {
    els.videoFullscreenBtn.addEventListener("click", () => {
      if (els.nativeVideoEl.requestFullscreen) els.nativeVideoEl.requestFullscreen().catch(() => {});
      else if (els.nativeVideoEl.webkitEnterFullscreen) els.nativeVideoEl.webkitEnterFullscreen();
    });
  }

  els.miniPlayerOpenBtn.addEventListener("click", () => {
    if (typeof window.__setActiveView === "function") window.__setActiveView("player");
  });

  els.playerSubtabs.querySelectorAll("[data-player-tab]").forEach((btn) => {
    btn.addEventListener("click", () => switchSubtab(btn.getAttribute("data-player-tab")));
  });

  els.librarySearchInput.addEventListener("input", () => {
    pState.searchQuery = els.librarySearchInput.value;
    renderActiveLibraryView();
  });
  els.librarySortSelect.addEventListener("change", () => {
    pState.prefs.sortBy = els.librarySortSelect.value;
    savePrefs();
    renderActiveLibraryView();
  });
  els.refreshLibraryBtn.addEventListener("click", refreshLibrary);
  els.libraryViewPills.querySelectorAll("[data-lib-view]").forEach((btn) => {
    btn.addEventListener("click", () => {
      pState.libraryViewMode = btn.getAttribute("data-lib-view") || "tracks";
      if (pState.libraryViewMode !== "albums") pState.selectedAlbumKey = null;
      renderActiveLibraryView();
    });
  });
  els.libraryScopeBtn.addEventListener("click", () => {
    pState.prefs.libraryScope = pState.prefs.libraryScope === "app" ? "all" : "app";
    savePrefs();
    pState.currentFolderPath = "";
    pState.selectedAlbumKey = null;
    refreshLibrary();
  });
  els.libraryKindPills.querySelectorAll("[data-lib-filter]").forEach((btn) => {
    btn.addEventListener("click", () => {
      pState.filterKind = btn.getAttribute("data-lib-filter") || "all";
      els.libraryKindPills.querySelectorAll("[data-lib-filter]").forEach((b) => {
        b.className = b === btn ? "apple-blue-pill" : "apple-secondary-pill";
      });
      renderActiveLibraryView();
    });
  });
  els.albumBackBtn.addEventListener("click", () => {
    pState.selectedAlbumKey = null;
    renderAlbumsView();
  });

  if (els.grantAndroidPermBtn) {
    els.grantAndroidPermBtn.addEventListener("click", () => {
      if (window.AndroidBridge && typeof window.AndroidBridge.requestMediaPermission === "function") {
        window.AndroidBridge.requestMediaPermission();
      }
    });
  }

  if (els.addScanFolderBtn) {
    els.addScanFolderBtn.addEventListener("click", async () => {
      if (!window.pywebview || !window.pywebview.api || typeof window.pywebview.api.select_download_folder !== "function") return;
      try {
        const chosen = await window.pywebview.api.select_download_folder();
        if (!chosen) return;
        await fetch("/api/library/folders", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ path: chosen }),
        });
        pState.libraryViewMode = "folders";
        await refreshLibrary();
      } catch {}
    });
  }

  els.importMediaBtn.addEventListener("click", () => importExternalFiles(false));
  els.tagExternalBtn.addEventListener("click", () => importExternalFiles(true));
  els.metaPickOtherFileBtn.addEventListener("click", () => importExternalFiles(true));
  els.importMediaInput.addEventListener("change", () => handleFileInputUpload(els.importMediaInput.files));

  els.createPlaylistForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const name = els.newPlaylistName.value.trim();
    if (!name) return;
    const resp = await fetch("/api/library/playlists", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, kind: els.newPlaylistKind.value, items: [] }),
    });
    if (resp.ok) {
      const data = await resp.json();
      els.newPlaylistName.value = "";
      pState.selectedPlaylistId = data.playlist?.id || null;
      await refreshLibrary();
    }
  });

  els.playPlaylistAllBtn.addEventListener("click", () => {
    const pl = pState.playlists.find((p) => p.id === pState.selectedPlaylistId);
    const tracks = pl ? resolvePlaylistTracks(pl) : [];
    if (tracks.length) playTrackItem(tracks[0], tracks);
  });
  els.playPlaylistShuffleBtn.addEventListener("click", () => {
    const pl = pState.playlists.find((p) => p.id === pState.selectedPlaylistId);
    const tracks = pl ? resolvePlaylistTracks(pl) : [];
    if (tracks.length) {
      pState.shuffle = true;
      els.playerShuffleBtn.classList.add("is-active");
      playTrackItem(tracks[Math.floor(Math.random() * tracks.length)], tracks);
    }
  });
  els.renamePlaylistBtn.addEventListener("click", async () => {
    const pl = pState.playlists.find((p) => p.id === pState.selectedPlaylistId);
    if (!pl) return;
    const next = window.prompt("Nuevo nombre de la lista:", pl.name);
    if (next && next.trim()) await updatePlaylistRemote(pl.id, { name: next.trim() });
  });
  els.deletePlaylistBtn.addEventListener("click", async () => {
    const pl = pState.playlists.find((p) => p.id === pState.selectedPlaylistId);
    if (!pl) return;
    const resp = await fetch(`/api/library/playlists/${encodeURIComponent(pl.id)}`, { method: "DELETE" });
    if (resp.ok) {
      pState.selectedPlaylistId = null;
      await refreshLibrary();
    }
  });

  els.eqEnabledSwitch.addEventListener("change", () => {
    ensureAudioGraph();
    pState.prefs.eqEnabled = els.eqEnabledSwitch.checked;
    savePrefs();
    syncEqAudioNodes();
  });
  els.eqLimiterSwitch.addEventListener("change", () => {
    ensureAudioGraph();
    pState.prefs.eqLimiter = els.eqLimiterSwitch.checked;
    savePrefs();
    syncEqAudioNodes();
  });
  els.eqResetBtn.addEventListener("click", () => applyEqPreset("flat"));
  els.eqPreampSlider.addEventListener("input", () => {
    ensureAudioGraph();
    const val = Number(els.eqPreampSlider.value);
    pState.prefs.eqPreamp = val;
    els.eqPreampVal.textContent = `${val > 0 ? "+" : ""}${val.toFixed(1)} dB`;
    savePrefs();
    syncEqAudioNodes();
  });
  els.eqQuickTweaks.querySelectorAll("[data-eq-tweak]").forEach((btn) => {
    btn.addEventListener("click", () => applyQuickTweak(btn.getAttribute("data-eq-tweak")));
  });

  els.playerAccentSwatches.querySelectorAll(".accent-swatch").forEach((sw) => {
    sw.addEventListener("click", () => {
      pState.prefs.accentColor = sw.getAttribute("data-accent") || "#ff2d55";
      savePrefs();
      applyPlayerCustomStyles();
    });
  });
  els.visualizerStylePills.querySelectorAll("[data-vis-style]").forEach((btn) => {
    btn.addEventListener("click", () => {
      pState.prefs.visualizerStyle = btn.getAttribute("data-vis-style") || "bars";
      savePrefs();
      applyPlayerCustomStyles();
      renderVisualizerFrame();
    });
  });
  els.prefAmbientBg.addEventListener("change", () => {
    pState.prefs.ambientBg = els.prefAmbientBg.checked;
    savePrefs();
    applyPlayerCustomStyles();
  });
  els.prefAutoAdvance.addEventListener("change", () => {
    pState.prefs.autoAdvance = els.prefAutoAdvance.checked;
    savePrefs();
  });
  els.prefMiniPlayer.addEventListener("change", () => {
    pState.prefs.miniPlayerEnabled = els.prefMiniPlayer.checked;
    savePrefs();
    syncMiniPlayerVisibility();
  });

  els.closeMetadataModalBtn.addEventListener("click", () => { els.metadataModal.hidden = true; });
  els.metaAutoSearchBtn.addEventListener("click", searchMetadataAuto);
  els.metaApplyBtn.addEventListener("click", applyMetadataChanges);
  els.metaCoverUrl.addEventListener("input", () => {
    const u = els.metaCoverUrl.value.trim();
    pState.metaCoverBase64 = null;
    if (u) setCoverPreviewSrc(`/api/thumbnail?url=${encodeURIComponent(u)}`);
  });
  els.metaCoverFileInput.addEventListener("change", () => {
    const file = els.metaCoverFileInput.files && els.metaCoverFileInput.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      pState.metaCoverBase64 = String(reader.result || "");
      els.metaCoverUrl.value = "";
      setCoverPreviewSrc(pState.metaCoverBase64);
    };
    reader.readAsDataURL(file);
  });

  els.closeAddToPlModalBtn.addEventListener("click", () => { els.addToPlaylistModal.hidden = true; });
  els.quickAddPlaylistForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const name = els.quickAddPlName.value.trim();
    if (!name || !pState.addToPlTrackPath) return;
    const item = pState.library.find((i) => i.path === pState.addToPlTrackPath);
    const kind = item?.kind === "video" ? "video" : "audio";
    const resp = await fetch("/api/library/playlists", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, kind, items: [pState.addToPlTrackPath] }),
    });
    if (resp.ok) {
      els.quickAddPlName.value = "";
      els.addToPlaylistModal.hidden = true;
      await refreshLibrary();
    }
  });

  document.addEventListener("keydown", (e) => {
    if (pState.activeView !== "player" || !els.metadataModal.hidden || !els.addToPlaylistModal.hidden || !els.queueModal.hidden) return;
    const tag = (e.target && e.target.tagName) || "";
    if (["INPUT", "TEXTAREA", "SELECT"].includes(tag)) return;
    if (e.code === "Space") {
      e.preventDefault();
      togglePlayPause();
    } else if (e.code === "ArrowRight") {
      seekDelta(10);
    } else if (e.code === "ArrowLeft") {
      seekDelta(-10);
    } else if (e.key && e.key.toLowerCase() === "m") {
      els.playerMuteBtn.click();
    }
  });

  renderEqUI();
  applyPlayerCustomStyles();

  window.ExclaimPlayer = {
    refreshLibrary,
    onViewActivated() {
      refreshLibrary();
      syncMiniPlayerVisibility();
    },
    onViewChanged(view) {
      pState.activeView = view;
      syncMiniPlayerVisibility();
    },
    async playPath(targetPath) {
      await refreshLibrary();
      const found = pState.library.find((i) => i.path === targetPath);
      if (found) {
        if (typeof window.__setActiveView === "function") window.__setActiveView("player");
        playTrackItem(found, pState.library);
      }
    },
  };
})();
