# Market Intelligence Agent — Devpost Submission

**Tagline:** A living competitive-intelligence workspace that grounds its analysis, learns from your judgment, and improves itself through Arize Phoenix.

## 💡 Inspiration
Founders and GTM leaders burn hours manually researching competitors and prospects — and the output is a stale one-shot report. We wanted an agent that does the research *and* gets better the more you use it, with the rigor to prove it isn't hallucinating. The hard part of "self-improving" agents isn't the prompt — it's evaluation. That's where Arize Phoenix became the centerpiece, not an add-on.

## 🔭 What it does
Give it a B2B company URL and it maps the competitive landscape and surfaces ICP-matched prospects in one pass. Then it becomes a **living workspace**:
- **Grounded, not guessed** — a profiler agent reads the actual site first, so `ptg-usa.com` is correctly identified as *Pension Technology Group* (pension software), not inferred from the domain.
- **Accumulate-and-curate** — re-scans *merge* into a persistent, deduped set. **Keep** pins an item to your shortlist; **Dismiss** hides it; untouched items stay candidates. Nothing silently vanishes.
- **Learns your judgment** — your Keep/Dismiss shapes future scans, and that signal is read back **from Phoenix**.
- **Trustworthy** — every analysis gets an LLM-as-judge **groundedness** score; the badge only warns when something's off.

## 🛠️ How we built it
- **Agent:** Google **ADK** pipeline on **Gemini 3.5 Flash** — `profiler → (competitive ∥ icp) → synthesizer` with structured JSON output.
- **Backend:** FastAPI on **Cloud Run** (Python + Node for the MCP server). **MongoDB** holds the curated workspace.
- **Frontend:** Next.js on **Netlify** (Basic-Auth gated for the demo), calling the backend directly.
- **Arize Phoenix — the evaluation & improvement engine:**
  1. **Tracing:** OpenInference auto-instrumentation streams every agent/LLM/tool span to Phoenix Cloud.
  2. **Evals:** a **groundedness** LLM-judge on every run + a **usefulness** (keep-rate) eval from human feedback — both tenant-tagged.
  3. **MCP:** the agent introspects its *own* traces/evals at runtime via the **Phoenix MCP server**.
  4. **Closed loop:** the next scan reads the tenant's graded keep/dismiss history **back from Phoenix** to improve — the agent learns from its own evaluation record.

## 🧗 Challenges we ran into
- **Domain-name hallucination** — the original agent guessed companies from the URL; we fixed it with a grounding profiler step (and an eval that *proves* it's fixed).
- **MCP-over-stdio reliability** on Windows — solved with boot-time pre-warming and timeouts; far more stable on Cloud Run/Linux.
- **"Self-improving" done honestly** — we separated the *fast* loop (Mongo, fresh) from the *learning/measurement* engine (Phoenix), and leaned into time-separated re-scans so reading the signal from Phoenix is both correct and meaningful.

## 🏆 Accomplishments
A genuinely **measured** self-improvement loop: the agent is scored on truth (groundedness) and usefulness (keep-rate), learns from its own Phoenix record, and you can watch the metrics in the dashboard — not a vibe, a number.

## 📚 What we learned
Evaluation *is* the product for agentic systems. Arize/Phoenix turned "trust me, it learns" into an observable, gradeable loop — and forced an honest architecture (product memory vs. evaluation engine).

## 🚀 What's next
Multi-tenant auth (the tenant dimension is already wired throughout), monitoring G2/Reddit signals, scheduled re-scans, an investor multi-company view, and Phoenix experiments + fine-tuning on the accumulated graded dataset.

---

**Built with:** Gemini 3.5 Flash · Google ADK · Arize Phoenix (tracing + evals + MCP) · FastAPI / Cloud Run · MongoDB · Next.js / Netlify

**Try it:** `<your Netlify URL>` — login `demo` / `hackathon`
**Code:** https://github.com/ellie-linehan/market-agent
