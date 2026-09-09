// macOS narration + MP4 packaging. All media is generated locally from the real UI recording.
const fs = require("node:fs");
const path = require("node:path");
const { execFileSync } = require("node:child_process");
const out = path.resolve(process.env.DEMO_OUTPUT || "artifacts/medagent-demo");
const recording = JSON.parse(fs.readFileSync(path.join(out, "recording.json"), "utf8"));
if (recording.quick || !recording.rawVideo) throw new Error("A full recording is required.");
const inputs = [];
const filters = [];
const subtitle = [];
const time = sec => new Date(sec * 1000).toISOString().slice(11, 23).replace(".", ",");
for (let i = 0; i < recording.scenes.length; i++) {
  const scene = recording.scenes[i];
  const file = path.join(out, scene.name + ".aiff");
  execFileSync("say", ["-v", "Samantha", "-r", "180", "-o", file, scene.speech]);
  const length = Number(execFileSync("ffprobe", ["-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", file], { encoding: "utf8" }));
  const next = recording.scenes[i + 1]?.at || 120;
  const start = scene.at + 0.4;
  if (start + length > next) throw new Error("Narration exceeds scene: " + scene.name);
  inputs.push("-i", file);
  filters.push(`[${i}:a]adelay=${start * 1000}:all=1[a${i}]`);
  // Separate downloadable subtitles; not burned into or presented as application UI.
  const sentences = scene.speech.match(/[^.!?]+[.!?]+/g) || [scene.speech];
  let cursor = start;
  const weight = sentences.reduce((sum, s) => sum + s.length, 0);
  for (const sentence of sentences) {
    const end = cursor + length * sentence.length / weight;
    subtitle.push(`${subtitle.length + 1}\n${time(cursor)} --> ${time(end)}\n${sentence.trim()}\n`);
    cursor = end;
  }
}
filters.push(recording.scenes.map((_, i) => `[a${i}]`).join("") + `amix=inputs=${recording.scenes.length}:normalize=0,apad=whole_dur=120[mix]`);
const audio = path.join(out, "narration.wav");
execFileSync("ffmpeg", ["-hide_banner", "-loglevel", "error", "-y", ...inputs, "-filter_complex", filters.join(";"), "-map", "[mix]", "-t", "120", audio]);
const srt = path.join(out, "medagent-demo.srt");
fs.writeFileSync(srt, subtitle.join("\n"));
execFileSync("ffmpeg", ["-hide_banner", "-loglevel", "error", "-y",
  "-ss", String(recording.leadInSeconds), "-i", recording.rawVideo,
  "-i", audio, "-i", srt,
  "-map", "0:v:0", "-map", "1:a:0", "-map", "2:s:0",
  "-vf", "tpad=stop_mode=clone:stop_duration=2", "-t", "120",
  "-c:v", "libx264", "-preset", "fast", "-crf", "20", "-pix_fmt", "yuv420p",
  "-c:a", "aac", "-b:a", "128k", "-c:s", "mov_text",
  "-metadata:s:s:0", "language=eng", "-movflags", "+faststart",
  path.join(out, "medagent-demo.mp4")]);
console.log(path.join(out, "medagent-demo.mp4"));
