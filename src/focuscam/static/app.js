const state = {
  videos: [],
  selectedVideo: null,
  analysis: null,
  anchors: [],
  showTracks: true,
  showCrop: true,
  selectionMode: false,
  activeJob: null,
};

const $ = (selector) => document.querySelector(selector);
const elements = {
  videoSelect: $("#video-select"), videoMeta: $("#video-meta"), analyze: $("#analyze-button"),
  video: $("#video"), stage: $("#video-stage"), empty: $("#empty-stage"), canvas: $("#overlay"),
  hint: $("#stage-hint"), selectStep: $("#select-step"), exportStep: $("#export-step"),
  pick: $("#pick-button"), absent: $("#absent-button"),
  selectionLabel: $("#selection-label"), selectionState: $(".selection-state"),
  showTracks: $("#show-tracks"), showCrop: $("#show-crop"),
  anchors: $("#anchors"), aspect: $("#aspect-select"),
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
  elements.absent.disabled = true;
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
  restoreTimeline();
  state.selectedVideo.analyzed = true;
  elements.analyze.disabled = false;
  elements.analyze.querySelector("span").textContent = "Analysis ready";
  elements.selectStep.classList.remove("disabled");
  elements.pick.disabled = false;
  elements.absent.disabled = false;
  setSelectionMode(false);
  elements.trackSection.classList.remove("hidden");
  renderSelection();
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

function timelineKey() {
  return state.analysis ? `focuscam:timeline:${state.analysis.analysis_id}` : null;
}

function persistTimeline() {
  const key = timelineKey();
  if (key) localStorage.setItem(key, JSON.stringify(state.anchors));
}

function restoreTimeline() {
  state.anchors = [];
  const key = timelineKey();
  if (!key) return;
  try {
    const saved = JSON.parse(localStorage.getItem(key) || "[]");
    if (!Array.isArray(saved)) return;
    state.anchors = saved
      .filter((anchor) => Number.isInteger(anchor.frame) && anchor.frame >= 0 && anchor.frame < state.analysis.frames.length)
      .map((anchor) => anchor.mode === "absent" || anchor.track_id === null
        ? { frame: anchor.frame, track_id: null, mode: "absent" }
        : { frame: anchor.frame, track_id: Number(anchor.track_id) })
      .filter((anchor) => anchor.track_id === null || Number.isInteger(anchor.track_id))
      .sort((left, right) => left.frame - right.frame);
  } catch (error) {
    console.warn("Could not restore the saved focus-cam timeline", error);
  }
}

function activeSegmentAt(frame) {
  if (!state.anchors.length) return null;
  let active = state.anchors[0];
  for (const anchor of state.anchors) {
    if (anchor.frame > frame) break;
    active = anchor;
  }
  return active;
}

function activeTrackAt(frame) {
  return activeSegmentAt(frame)?.track_id ?? null;
}

function chooseTrack(trackId, frame = currentFrame()) {
  if (!state.anchors.length) frame = 0;
  state.anchors = state.anchors.filter((anchor) => anchor.frame !== frame);
  state.anchors.push({ frame, track_id: Number(trackId) });
  state.anchors.sort((left, right) => left.frame - right.frame);
  persistTimeline();
  setSelectionMode(false);
  renderSelection();
  drawOverlay();
}

function markAbsent(frame = currentFrame()) {
  if (!state.analysis) return;
  if (!state.anchors.length) frame = 0;
  state.anchors = state.anchors.filter((anchor) => anchor.frame !== frame);
  state.anchors.push({ frame, track_id: null, mode: "absent" });
  state.anchors.sort((left, right) => left.frame - right.frame);
  persistTimeline();
  setSelectionMode(false);
  renderSelection();
  drawOverlay();
}

function setSelectionMode(enabled) {
  state.selectionMode = Boolean(enabled && state.analysis);
  elements.stage.classList.toggle("picking", state.selectionMode);
  elements.pick.setAttribute("aria-pressed", String(state.selectionMode));
  elements.pick.textContent = state.selectionMode ? "Cancel selection" : "Select performer";
  elements.hint.classList.toggle("hidden", !state.selectionMode);
  if (state.selectionMode) elements.video.pause();
}

function renderSelection() {
  const hasTimeline = state.anchors.length > 0;
  const hasTarget = state.anchors.some((anchor) => anchor.track_id !== null);
  elements.selectionState.classList.toggle("chosen", hasTimeline);
  elements.exportStep.classList.toggle("disabled", !hasTarget);
  elements.render.disabled = !hasTarget;
  elements.anchors.replaceChildren();
  state.anchors.forEach((anchor, index) => {
    const row = document.createElement("div");
    const absent = anchor.track_id === null;
    row.className = `anchor${absent ? " absent" : ""}`;
    const time = anchor.frame / state.analysis.source.fps;
    const target = absent ? "Performer off-screen" : `Track ${anchor.track_id}`;
    row.innerHTML = `<span>${index === 0 ? "Start" : formatTime(time)} · ${target}</span><button type="button" aria-label="Remove correction">×</button>`;
    row.querySelector("span").addEventListener("click", () => { elements.video.currentTime = time; });
    row.querySelector("button").addEventListener("click", () => {
      state.anchors.splice(index, 1); persistTimeline(); renderSelection(); drawOverlay(); renderTrackGallery();
    });
    elements.anchors.append(row);
  });
  renderTrackGallery();
  updateActiveLabels();
}

function updateActiveLabels() {
  const segment = activeSegmentAt(currentFrame());
  const active = segment?.track_id ?? null;
  elements.selectionLabel.textContent = !segment
    ? "No performer selected"
    : active === null ? "Performer marked off-screen" : `Following track ${active}`;
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

function clamp(value, minimum, maximum) {
  return Math.min(maximum, Math.max(minimum, value));
}

function outputAspect() {
  const [width, height] = elements.aspect.value.split(":").map(Number);
  return width / height;
}

function previewBoxAt(frameIndex, trackId) {
  if (trackId === null) return null;
  const find = (index) => state.analysis.frames[index]?.detections
    .find((detection) => detection.track_id === trackId)?.bbox || null;
  const exact = find(frameIndex);
  if (exact) return exact;

  const maxGap = Math.max(1, Math.round(state.analysis.source.fps * 1.2));
  let before = null;
  let after = null;
  for (let offset = 1; offset <= maxGap && (!before || !after); offset += 1) {
    const earlier = frameIndex - offset;
    const later = frameIndex + offset;
    if (!before && earlier >= 0 && activeTrackAt(earlier) === trackId) {
      const bbox = find(earlier);
      if (bbox) before = { index: earlier, bbox };
    }
    if (!after && later < state.analysis.frames.length && activeTrackAt(later) === trackId) {
      const bbox = find(later);
      if (bbox) after = { index: later, bbox };
    }
  }
  if (before && after) {
    const fraction = (frameIndex - before.index) / (after.index - before.index);
    return before.bbox.map((value, index) => value + (after.bbox[index] - value) * fraction);
  }
  return before?.bbox || after?.bbox || null;
}

function previewCrop(bbox) {
  const sourceWidth = state.analysis.source.width;
  const sourceHeight = state.analysis.source.height;
  const aspect = outputAspect();
  const padding = Number(elements.padding.value);
  const maximumHeight = Math.min(sourceHeight, sourceWidth / aspect);
  const minimumHeight = maximumHeight * .34;

  if (!bbox) {
    return {
      left: (sourceWidth - maximumHeight * aspect) / 2,
      top: (sourceHeight - maximumHeight) / 2,
      width: maximumHeight * aspect,
      height: maximumHeight,
    };
  }

  const [x1, y1, x2, y2] = bbox.map(Number);
  const personHeight = Math.max(1, y2 - y1);
  const personWidth = Math.max(1, x2 - x1);
  const safeTop = Math.max(0, y1 - personHeight * .12);
  const safeBottom = Math.min(sourceHeight, y2 + personHeight * .04);
  const safeLeft = Math.max(0, x1 - personWidth * .06);
  const safeRight = Math.min(sourceWidth, x2 + personWidth * .06);
  const requiredHeight = Math.max(safeBottom - safeTop, (safeRight - safeLeft) / aspect);
  const height = clamp(Math.max(personHeight * padding, requiredHeight), minimumHeight, maximumHeight);
  const width = height * aspect;
  let centerX = (x1 + x2) / 2;
  let centerY = (y1 + y2) / 2 - personHeight * Math.max(0, padding - 1) * .18;

  const verticalLower = safeBottom - height / 2;
  const verticalUpper = safeTop + height / 2;
  centerY = verticalLower <= verticalUpper
    ? clamp(centerY, verticalLower, verticalUpper)
    : safeTop + height / 2;
  centerX = clamp(centerX, width / 2, sourceWidth - width / 2);
  centerY = clamp(centerY, height / 2, sourceHeight - height / 2);
  return { left: centerX - width / 2, top: centerY - height / 2, width, height };
}

function drawCropFrame(context, geometry, bbox, absent) {
  const crop = previewCrop(bbox);
  const sourceWidth = state.analysis.source.width;
  const sourceHeight = state.analysis.source.height;
  const x = geometry.offsetX + crop.left * geometry.scale;
  const y = geometry.offsetY + crop.top * geometry.scale;
  const width = crop.width * geometry.scale;
  const height = crop.height * geometry.scale;

  context.save();
  context.fillStyle = "rgba(0, 0, 0, .38)";
  context.beginPath();
  context.rect(geometry.offsetX, geometry.offsetY, sourceWidth * geometry.scale, sourceHeight * geometry.scale);
  context.rect(x, y, width, height);
  context.fill("evenodd");
  context.strokeStyle = "#ff6f61";
  context.lineWidth = 2.5;
  context.setLineDash([8, 5]);
  context.strokeRect(x, y, width, height);
  context.setLineDash([]);
  context.font = "700 10px ui-monospace, monospace";
  const label = absent ? " WIDE · OFF-SCREEN " : ` OUTPUT ${elements.aspect.value} `;
  const labelWidth = context.measureText(label).width;
  context.fillStyle = "#ff6f61";
  context.fillRect(x, y, labelWidth + 7, 18);
  context.fillStyle = "#160c0a";
  context.fillText(label, x + 3, y + 13);
  context.restore();
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
  if (!state.analysis) return;

  const geometry = displayGeometry();
  const frame = state.analysis.frames[currentFrame()];
  const segment = activeSegmentAt(frame.index);
  const active = segment?.track_id ?? null;
  if (state.showCrop && segment) {
    drawCropFrame(context, geometry, previewBoxAt(frame.index, active), active === null);
  }
  if (!state.showTracks) return;
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
elements.absent.addEventListener("click", () => markAbsent());
elements.showTracks.addEventListener("change", () => { state.showTracks = elements.showTracks.checked; drawOverlay(); });
elements.showCrop.addEventListener("change", () => { state.showCrop = elements.showCrop.checked; drawOverlay(); });
elements.aspect.addEventListener("change", drawOverlay);
elements.padding.addEventListener("change", drawOverlay);
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
