// Records an isolated, synthetic-only browser session. No personal Chrome profile is used.
const { chromium } = require("playwright");
const fs = require("node:fs");
const path = require("node:path");
const { performance } = require("node:perf_hooks");

const quick = process.argv.includes("--quick");
const out = path.resolve(process.env.DEMO_OUTPUT || "artifacts/medagent-demo");
const url = process.env.DEMO_URL || "http://localhost:8501";
const api = process.env.DEMO_API_URL || "http://localhost:8000";
fs.mkdirSync(out, { recursive: true });
const scenes = [
  { at: 0, name: "intro", speech: "This is MedAgent, an inspectable healthcare evidence review prototype. This demonstration uses synthetic cases and an offline extractive reasoner. It is an engineering demo, not a diagnostic tool or a source of patient-specific medical advice." },
  { at: 15, name: "evidence", speech: "We select a respiratory assessment example and run the pipeline. The retriever ranks curated evidence, and the reasoner creates citation-bound review points. On the right, each source exposes its excerpt, review point, and original reference. A text match does not establish clinical applicability." },
  { at: 36, name: "outputs", speech: "Agent Outputs makes the execution inspectable. Each component records its status, measured duration, and structured result. These are four modular pipeline roles, not four autonomous language models. The displayed timings come from the completed run." },
  { at: 53, name: "conflicts", speech: "Next, the playground deliberately injects two errors into an offline example. One matches a known counterexample; the other cites a source that does not exist. Conflict Analysis flags both for human review. This demonstrates the detection workflow, not a measurement of naturally occurring model hallucinations." },
  { at: 80, name: "evaluation", speech: "The evaluation tab runs six synthetic smoke cases. We report retrieval recall, expected citation precision, rule text matches, and pipeline latency. Perfect scores here are expected for the curated extractive baseline. They are not clinical accuracy. Results can be exported for reproducibility." },
  { at: 102, name: "history", speech: "Cases retains recent run snapshots within the session, including flagged examples. Each record can be exported as JSON for inspection and comparison." },
  { at: 113, name: "limits", speech: "Next: validate a real model, expand independent evaluation, and measure semantic errors and cost." },
];

(async () => {
  const health = await fetch(api + "/health").then(r => r.json());
  if (health.reasoner_mode !== "extractive") throw new Error("Recording requires offline extractive mode.");
  const browser = await chromium.launch({ channel: "chrome", headless: true });
  const context = await browser.newContext({
    viewport: { width: 1600, height: 1000 },
    deviceScaleFactor: 1,
    colorScheme: "light",
    ...(quick ? {} : { recordVideo: { dir: out, size: { width: 1600, height: 1000 } } }),
  });
  const pageCreated = performance.now();
  const page = await context.newPage();
  page.setDefaultTimeout(15000);
  const errors = [];
  page.on("pageerror", error => errors.push(error.message));
  const tab = name => page.getByRole("tab", { name, exact: true });
  const shot = async name => {
    await page.waitForTimeout(450); // Let native expander/tab transitions finish.
    await page.screenshot({ path: path.join(out, name + ".png") });
  };
  const mainScroll = page.locator('[data-testid="stMain"]');
  const top = async () => {
    await mainScroll.evaluate(el => { el.scrollTop = 0; });
  };
  try {
    await page.goto(url);
    await page.getByRole("button", { name: "Run Agents", exact: true }).waitFor();
    await page.getByText("Backend connected", { exact: false }).waitFor();
    const dismiss = page.getByRole("button", { name: "Don't show again", exact: true });
    await dismiss.waitFor({ timeout: 3000 }).then(() => dismiss.click()).catch(() => {});
    await page.screenshot({ path: path.join(out, "ready.png") });
    const begin = performance.now();
    const leadInSeconds = (begin - pageCreated) / 1000;
    const stage = async index => {
      const scene = scenes[index];
      if (!quick) {
        const wait = scene.at * 1000 - (performance.now() - begin);
        if (wait > 0) await page.waitForTimeout(wait);
      }
      console.log("SCENE " + scene.name);
    };
    await stage(0);
    await shot("intro");
    await stage(1);
    await page.getByRole("button", { name: "Run Agents", exact: true }).click();
    await page.getByText("Text checks passed", { exact: false }).waitFor();
    await page.locator(".st-key-sources_panel summary").first().click();
    await shot("evidence");
    if (!quick) await page.waitForTimeout(6000);
    await page.getByRole("heading", { name: "Evidence review points", exact: true }).evaluate(el => el.scrollIntoView({ block: "start" }));
    await shot("answer");
    await stage(2);
    await tab("Agent Outputs").click();
    await page.locator('summary').filter({ hasText: /retriever · completed/ }).click();
    await page.getByText("Recorded component outputs", { exact: false }).evaluate(el => el.scrollIntoView({ block: "start" }));
    await shot("outputs");
    await stage(3);
    await tab("Playground").click();
    await top();
    await page.getByRole("button", { name: "Run Conflict Demo", exact: true }).click();
    await page.getByText("Human review required · 2 flagged statements").last().waitFor();
    await tab("Ask").click();
    await tab("Conflict Analysis").click();
    await page.getByRole("heading", { name: "Claim-level review flags", exact: true }).evaluate(el => el.scrollIntoView({ block: "start" }));
    await page.getByText("Known counterexample matched", { exact: true }).last().waitFor();
    await shot("conflicts");
    await stage(4);
    await tab("Evaluate").click();
    await top();
    await page.getByRole("button", { name: "Run Evaluation", exact: true }).click();
    await page.getByRole("button", { name: "Download evaluation JSON", exact: true }).waitFor();
    await shot("evaluation");
    await stage(5);
    await tab("Cases").click();
    await top();
    await shot("history");
    await stage(6);
    await tab("About").click();
    await top();
    await shot("limits");
    if (!quick) {
      const remaining = 120000 - (performance.now() - begin);
      if (remaining > 0) await page.waitForTimeout(remaining);
    }
    if (errors.length) throw new Error(errors.join("\n"));
    const video = page.video();
    await context.close();
    fs.writeFileSync(path.join(out, "recording.json"), JSON.stringify({
      recorded_at: new Date().toISOString(), mode: "extractive", quick,
      source: "real browser interaction recording; synthetic cases only",
      viewport: { width: 1600, height: 1000 }, leadInSeconds, scenes,
      rawVideo: video ? await video.path() : null,
      browserErrors: errors,
    }, null, 2));
    console.log("COMPLETE " + out);
  } catch (error) {
    await page.screenshot({ path: path.join(out, "failure.png") }).catch(() => {});
    throw error;
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exit(1); });
