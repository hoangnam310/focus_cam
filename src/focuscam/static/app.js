const state = {
  videos: [],
  selectedVideo: null,
  analysis: null,
  anchors: [],
  showTracks: true,
  selectionMode: false,
  activeJob: null,
};

const $ = (selector) => document.querySelector(selector);
const elements = {
  videoSelect: $("#video-select"), videoMeta: $("#video-meta"), analyze: $("#analyze-button"),
  video: $("#video"), stage: $("#video-stage"), empty: $("#empty-stage"), canvas: $("#overlay"),
  hint: $("#stage-hint"), selectStep: $("#select-step"), exportStep: $("#export-step"),
  pick: $("#pick-button"),
  selectionLabel: $("#selection-label"), selectionState: $(".selection-state"),
  showTracks: $("#show-tracks"), anchors: $("#anchors"), aspect: $("#aspect-select"),
  padding: $("#padding-select"), render: $("#render-button"), download: $("#download-link"),
  progressCard: $("#progress-card"), progressTitle: $("#progress-title"),
  progressPercent: $("#progress-percent"), progressBar: $("#progress-bar"),
  progressMessage: $("#progress-message"), trackSection: $("#track-section"),
  trackGrid: $("#track-grid"), trackCount: $("#track-count"),
};

function formatTime(seconds) {
  const minutes = Math.floor(seconds / 60);
  return `${minutes}:${String(Math.floor(seconds % 60)).padStart(2, "0")}`;
}

async function requestJSON(url, options = {}) {
  const response = await fetch(url, options);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.error || `Request failed (${response.status})`);
  return payload;
}

function setProgress(title, progress, message) {
  elements.progressCard.classList.remove("hidden");
  elements.progressTitle.textContent = title;
  const percent = Math.round(progress * 100);
  elements.progressPercent.textContent = `${percent}%`;
  elements.progressBar.style.width = `${percent}%`;
  elements.progressMessage.textContent = message;
}

function hideProgress() { elements.progressCard.classList.add("hidden"); }

async function loadVideos() {
  try {
    const payload = await requestJSON("/api/videos");
    state.videos = payload.videos;
    elements.videoSelect.replaceChildren();
    if (!state.videos.length) {
      elements.videoSelect.append(new Option("Add an MP4 to this project", ""));
      return;
    }
    state.videos.forEach((video) => {
      const suffix = video.analyzed ? " · analyzed" : "";
      elements.videoSelect.append(new Option(`${video.path}${suffix}`, video.path));
    });
    selectVideo(state.videos[0].path);
  } catch (error) {
    elements.videoSelect.replaceChildren(new Option(error.message, ""));
  }
}

function selectVideo(name) {
  state.selectedVideo = state.videos.find((video) => video.path === name) || null;
  state.analysis = null;
  state.anchors = [];
  elements.download.classList.add("hidden");
  renderSelection();
  if (!state.selectedVideo) return;

  const video = state.selectedVideo;
  elements.video.src = `/media/${encodeURIComponent(video.path)}`;
  elements.stage.classList.add("ready");
  setSelectionMode(false);
  elements.pick.disabled = true;
  elements.empty.classList.add("hidden");
  elements.analyze.disabled = false;
  elements.analyze.querySelector("span").textContent = video.analyzed ? "Open analysis" : "Analyze performers";
  elements.videoMeta.innerHTML = `<span>${video.width}×${video.height}</span><span>${video.fps.toFixed(1)} FPS</span><span>${formatTime(video.duration)}</span>`;
  elements.selectStep.classList.add("disabled");
  elements.exportStep.classList.add("disabled");
  elements.trackSection.classList.add("hidden");
  drawOverlay();
}

async function analyzeSelectedVideo() {
  if (!state.selectedVideo) return;
  elements.analyze.disabled = true;
  try {
    const payload = await requestJSON("/api/analyze", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ video: state.selectedVideo.path }),
    });
    if (payload.status === "completed") {
      await loadAnalysis(payload.analysis_id);
      return;
    }
    await watchJob(payload.job_id, "Analyzing performance");
  } catch (error) {
    setProgress("Analysis failed", 0, error.message);
    elements.analyze.disabled = false;
  }
}

async function watchJob(jobId, title) {
  state.activeJob = jobId;
  while (state.activeJob === jobId) {
    const job = await requestJSON(`/api/jobs/${jobId}`);
    setProgress(title, job.progress, job.message);
    if (job.status === "completed") {
      state.activeJob = null;
      if (job.kind === "analysis") await loadAnalysis(job.result.analysis_id);
      else finishRender(job.result);
      return;
    }
    if (job.status === "failed") {
      state.activeJob = null;
      throw new Error(job.error || "The job failed");
    }
    await new Promise((resolve) => setTimeout(resolve, 800));
  }
}

async function loadAnalysis(identifier) {
  setProgress("Opening analysis", 1, "Loading tracks…");
  state.analysis = await requestJSON(`/api/analyses/${identifier}`);
  state.selectedVideo.analyzed = true;
  elements.analyze.disabled = false;
  elements.analyze.querySelector("span").textContent = "Analysis ready";
  elements.selectStep.classList.remove("disabled");
  elements.pick.disabled = false;
  setSelectionMode(false);
  elements.trackSection.classList.remove("hidden");
  renderTrackGallery();
  hideProgress();
  drawOverlay();
}

function currentFrame() {
  if (!state.analysis) return 0;
  return Math.max(0, Math.min(
    state.analysis.frames.length - 1,
    Math.round(elements.video.currentTime * state.analysis.source.fps),
  ));
}

function activeTrackAt(frame) {
  if (!state.anchors.length) return null;
  let active = state.anchors[0].track_id;
  for (const anchor of state.anchors) {
    if (anchor.frame > frame) break;
    active = anchor.track_id;
  }
  return active;
}

function chooseTrack(trackId, frame = currentFrame()) {
  if (!state.anchors.length) frame = 0;
  state.anchors = state.anchors.filter((anchor) => anchor.frame !== frame);
  state.anchors.push({ frame, track_id: Number(trackId) });
  state.anchors.sort((left, right) => left.frame - right.frame);
  setSelectionMode(false);
  renderSelection();
  drawOverlay();
}

function setSelectionMode(enabled) {
  state.selectionMode = Boolean(enabled && state.analysis);
  elements.stage.classList.toggle("picking", state.selectionMode);
  elements.pick.setAttribute("aria-pressed", String(state.selectionMode));
  elements.pick.textContent = state.selectionMode ? "Cancel selection" : "Select performer on video";
  elements.hint.classList.toggle("hidden", !state.selectionMode);
  if (state.selectionMode) elements.video.pause();
}

function renderSelection() {
  const hasSelection = state.anchors.length > 0;
  elements.selectionState.classList.toggle("chosen", hasSelection);
  elements.exportStep.classList.toggle("disabled", !hasSelection);
  elements.render.disabled = !hasSelection;
  elements.anchors.replaceChildren();
  state.anchors.forEach((anchor, index) => {
    const row = document.createElement("div");
    row.className = "anchor";
    const time = anchor.frame / state.analysis.source.fps;
    row.innerHTML = `<span>${index === 0 ? "Start" : formatTime(time)} · Track ${anchor.track_id}</span><button type="button" aria-label="Remove correction">×</button>`;
    row.querySelector("span").addEventListener("click", () => { elements.video.currentTime = time; });
    row.querySelector("button").addEventListener("click", () => {
      state.anchors.splice(index, 1); renderSelection(); drawOverlay(); renderTrackGallery();
    });
    elements.anchors.append(row);
  });
  renderTrackGallery();
  updateActiveLabels();
}

function updateActiveLabels() {
  const active = activeTrackAt(currentFrame());
  elements.selectionLabel.textContent = state.anchors.length ? `Following track ${active}` : "No performer selected";
  document.querySelectorAll(".track-card").forEach((card) => {
    card.classList.toggle("selected", Number(card.dataset.trackId) === active);
  });
}

function renderTrackGallery() {
  if (!state.analysis) return;
  const active = activeTrackAt(currentFrame());
  const galleryTracks = state.analysis.tracks
    .filter((track) => track.gallery !== false)
    .sort((left, right) => right.observations - left.observations);
  elements.trackCount.textContent = `${galleryTracks.length} track${galleryTracks.length === 1 ? "" : "s"}`;
  elements.trackGrid.replaceChildren();
  galleryTracks.forEach((track) => {
    const card = document.createElement("button");
    card.type = "button";
    card.dataset.trackId = track.track_id;
    card.className = `track-card${active === track.track_id ? " selected" : ""}`;
    const image = track.thumbnail ? `/api/analyses/${state.analysis.analysis_id}/assets/${track.thumbnail}` : "";
    card.innerHTML = `${image ? `<img src="${image}" alt="Track ${track.track_id} sample">` : ""}<div><strong>Track ${track.track_id}</strong><span>${formatTime(track.observations / state.analysis.source.fps)}</span></div>`;
    card.addEventListener("click", () => {
      elements.video.currentTime = track.thumbnail_frame / state.analysis.source.fps;
      elements.video.pause();
      chooseTrack(track.track_id, currentFrame());
    });
    elements.trackGrid.append(card);
  });
}

function displayGeometry() {
  const rect = elements.canvas.getBoundingClientRect();
  const sourceWidth = state.analysis?.source.width || elements.video.videoWidth || 1;
  const sourceHeight = state.analysis?.source.height || elements.video.videoHeight || 1;
  const scale = Math.min(rect.width / sourceWidth, rect.height / sourceHeight);
  return {
    width: rect.width, height: rect.height, scale,
    offsetX: (rect.width - sourceWidth * scale) / 2,
    offsetY: (rect.height - sourceHeight * scale) / 2,
  };
}

function colorFor(trackId, alpha = 1) {
  const hue = (Number(trackId) * 67 + 48) % 360;
  return `hsla(${hue}, 88%, 68%, ${alpha})`;
}

function drawOverlay() {
  const rect = elements.canvas.getBoundingClientRect();
  const ratio = window.devicePixelRatio || 1;
  if (elements.canvas.width !== Math.round(rect.width * ratio) || elements.canvas.height !== Math.round(rect.height * ratio)) {
    elements.canvas.width = Math.round(rect.width * ratio);
    elements.canvas.height = Math.round(rect.height * ratio);
  }
  const context = elements.canvas.getContext("2d");
  context.setTransform(ratio, 0, 0, ratio, 0, 0);
  context.clearRect(0, 0, rect.width, rect.height);
  if (!state.analysis || !state.showTracks) return;

  const geometry = displayGeometry();
  const frame = state.analysis.frames[currentFrame()];
  const active = activeTrackAt(frame.index);
  frame.detections.forEach((detection) => {
    const [x1, y1, x2, y2] = detection.bbox;
    const x = geometry.offsetX + x1 * geometry.scale;
    const y = geometry.offsetY + y1 * geometry.scale;
    const width = (x2 - x1) * geometry.scale;
    const height = (y2 - y1) * geometry.scale;
    const selected = detection.track_id === active;
    context.strokeStyle = selected ? "#d8ff56" : colorFor(detection.track_id, .88);
    context.lineWidth = selected ? 3 : 1.5;
    context.strokeRect(x, y, width, height);
    context.font = "700 11px ui-monospace, monospace";
    const label = ` ${detection.track_id} `;
    const labelWidth = context.measureText(label).width;
    context.fillStyle = selected ? "#d8ff56" : colorFor(detection.track_id, .92);
    context.fillRect(x, Math.max(0, y - 19), labelWidth + 8, 19);
    context.fillStyle = "#0b0c10";
    context.fillText(label, x + 4, Math.max(13, y - 5));
  });
}

function handleCanvasClick(event) {
  if (!state.analysis || !state.selectionMode) return;
  const rect = elements.canvas.getBoundingClientRect();
  const geometry = displayGeometry();
  const sourceX = (event.clientX - rect.left - geometry.offsetX) / geometry.scale;
  const sourceY = (event.clientY - rect.top - geometry.offsetY) / geometry.scale;
  const frame = state.analysis.frames[currentFrame()];
  const matches = frame.detections.filter(({ bbox }) => sourceX >= bbox[0] && sourceX <= bbox[2] && sourceY >= bbox[1] && sourceY <= bbox[3]);
  matches.sort((a, b) => (a.bbox[2] - a.bbox[0]) * (a.bbox[3] - a.bbox[1]) - (b.bbox[2] - b.bbox[0]) * (b.bbox[3] - b.bbox[1]));
  if (matches.length) chooseTrack(matches[0].track_id);
}

async function renderVideo() {
  elements.render.disabled = true;
  elements.download.classList.add("hidden");
  try {
    const payload = await requestJSON("/api/render", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        analysis_id: state.analysis.analysis_id, anchors: state.anchors,
        aspect: elements.aspect.value, padding: Number(elements.padding.value),
      }),
    });
    await watchJob(payload.job_id, "Rendering focus cam");
  } catch (error) {
    setProgress("Render failed", 0, error.message);
    elements.render.disabled = false;
  }
}

function finishRender(result) {
  setProgress("Focus cam ready", 1, result.filename);
  elements.render.disabled = false;
  elements.download.href = result.url;
  elements.download.classList.remove("hidden");
}

elements.videoSelect.addEventListener("change", (event) => selectVideo(event.target.value));
elements.analyze.addEventListener("click", analyzeSelectedVideo);
elements.pick.addEventListener("click", () => setSelectionMode(!state.selectionMode));
elements.showTracks.addEventListener("change", () => { state.showTracks = elements.showTracks.checked; drawOverlay(); });
elements.render.addEventListener("click", renderVideo);
elements.canvas.addEventListener("click", handleCanvasClick);
elements.video.addEventListener("timeupdate", () => { drawOverlay(); updateActiveLabels(); });
elements.video.addEventListener("play", () => setSelectionMode(false));
elements.video.addEventListener("seeked", drawOverlay);
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") setSelectionMode(false);
});
window.addEventListener("resize", drawOverlay);

loadVideos();
