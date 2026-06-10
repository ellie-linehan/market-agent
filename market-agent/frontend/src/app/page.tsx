'use client'

import { useState, FormEvent } from 'react'

// The browser calls the backend (Cloud Run) directly — no Next.js proxy — so the
// ~60s /analyze request isn't killed by a serverless function timeout.
// Set NEXT_PUBLIC_BACKEND_URL in Netlify; defaults to localhost for dev.
const BACKEND = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000'

const CANDIDATE_CAP = 7 // Miller's Law: don't dump unbounded lists on the user.

type Status = 'kept' | 'candidate' | 'dismissed'

interface Competitor {
  name: string
  url: string
  positioning: string
  target_segment: string
  key_features: string[]
  pricing_model?: string
  item_key: string
  status: Status
  reason?: string | null
}

interface Prospect {
  company_name: string
  website: string
  match_reason: string
  employee_count?: string
  industry?: string
  tech_stack: string[]
  item_key: string
  status: Status
  reason?: string | null
}

interface Evaluation {
  score: number
  label: string
  reason: string
}

interface Workspace {
  company: string
  market_summary: string
  eval?: Evaluation | null
  competitors: Competitor[]
  icp_prospects: Prospect[]
  new_competitors: string[]
  new_prospects: string[]
}

interface Snapshot {
  id: string
  created_at: string
  company_name: string
}

function formatSnapshotTime(iso: string): string {
  const d = new Date(iso)
  return d.toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  })
}

// Quiet when grounded; only speaks up when the eval caught a problem.
function GroundingBadge({ evaluation }: { evaluation: Evaluation }) {
  if (evaluation.label === 'grounded') {
    return (
      <span title={evaluation.reason} className="text-xs text-green-700/70">
        ✓ Grounded
      </span>
    )
  }
  const tone =
    evaluation.label === 'partial'
      ? 'bg-amber-50 border-amber-300 text-amber-800'
      : 'bg-red-50 border-red-300 text-red-700'
  return (
    <span
      title={evaluation.reason}
      className={`text-xs px-2 py-0.5 rounded-full border font-medium ${tone}`}
    >
      ⚠ Low grounding ({evaluation.score.toFixed(2)}) — review
    </span>
  )
}

// Only split where punctuation is followed by whitespace + a capital letter.
function splitSentences(text: string): string[] {
  return text
    .split(/(?<=[.!?])\s+(?=[A-Z])/)
    .map(s => s.trim())
    .filter(Boolean)
}

function shortPricingLabel(model: string): string {
  const m = model.toLowerCase()
  if (m.includes('freemium') || m.includes('free tier') || m.includes('free plan')) return 'Freemium'
  if (m.includes('open source')) return 'Open Source'
  if (m.includes('usage') || m.includes('per host') || m.includes('per gb') || m.includes('consumption')) return 'Usage-based'
  if (m.includes('enterprise') && (m.includes('custom') || m.includes('only'))) return 'Enterprise'
  if (m.includes('tiered') || (m.includes('free') && m.includes('pro'))) return 'Tiered'
  if (m.includes('subscription') || m.includes('/month') || m.includes('/seat') || m.includes('/user')) return 'Subscription'
  if (m.includes('enterprise')) return 'Enterprise'
  if (m.includes('custom')) return 'Custom'
  return model.split(/[\s,]/)[0]
}

function stripInsightPreamble(text: string): string {
  return text
    .replace(/^Actionable insight:\s*/i, '')
    .replace(/^An actionable insight[^.]*?\bis to\s+/i, '')
    .replace(/^./, c => c.toUpperCase())
}

function SummaryBlock({ text }: { text: string }) {
  const insightMatch = text.match(/(.*?)((?:Actionable insight:|An actionable|Actionable|Key insight)[^.]*\.[\s\S]*)$/is)
  const body = insightMatch ? insightMatch[1].trim() : text
  const rawInsight = insightMatch ? insightMatch[2].trim() : null
  const insight = rawInsight ? stripInsightPreamble(rawInsight) : null
  const bodySentences = splitSentences(body)
  const insightSentences = insight ? splitSentences(insight) : []

  return (
    <div className="bg-white border border-cream-dark rounded-lg overflow-hidden">
      <ul className="px-5 py-4 flex flex-col gap-2.5">
        {bodySentences.map((s, i) => (
          <li key={i} className="flex gap-2.5 text-sm text-charcoal/80 leading-relaxed">
            <span className="text-tan shrink-0 mt-1">·</span>
            <span>{s}</span>
          </li>
        ))}
      </ul>
      {insightSentences.length > 0 && (
        <div className="border-t border-cream-dark bg-cream px-5 py-3 flex gap-3 items-start">
          <span className="text-tan font-semibold text-xs uppercase tracking-wide mt-0.5 shrink-0">Insight</span>
          <div className="flex flex-col gap-2">
            {insightSentences.map((s, i) => (
              <p key={i} className="text-sm text-charcoal leading-relaxed">{s}</p>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

function FeedbackButtons({
  status,
  reason: initialReason,
  onKeep,
  onDismiss,
}: {
  status: Status
  reason?: string | null
  onKeep: (reason: string) => void
  onDismiss: (reason: string) => void
}) {
  const [reason, setReason] = useState(initialReason || '')
  return (
    <div className="flex flex-col gap-1.5 w-full">
      <input
        type="text"
        value={reason}
        onChange={e => setReason(e.target.value)}
        placeholder="why? (optional — teaches the agent)"
        className="text-xs bg-white border border-cream-dark rounded px-2 py-1 text-charcoal placeholder-charcoal/30 focus:outline-none focus:border-tan transition-colors"
      />
      <div className="flex gap-1.5">
        <button
          onClick={() => onKeep(reason)}
          className={`text-xs px-2.5 py-1 rounded-md border transition-colors ${
            status === 'kept'
              ? 'bg-charcoal text-cream border-charcoal'
              : 'bg-white text-charcoal/60 border-cream-dark hover:border-tan'
          }`}
        >
          {status === 'kept' ? '✓ Kept' : '✓ Keep'}
        </button>
        <button
          onClick={() => onDismiss(reason)}
          className="text-xs px-2.5 py-1 rounded-md border bg-white text-charcoal/50 border-cream-dark hover:border-red-300 hover:text-red-600 transition-colors"
        >
          ✕ Dismiss
        </button>
      </div>
    </div>
  )
}

function CompetitorCard({
  c,
  onKeep,
  onDismiss,
}: {
  c: Competitor
  onKeep: (reason: string) => void
  onDismiss: (reason: string) => void
}) {
  return (
    <div
      className={`bg-white border rounded-lg p-5 flex flex-col gap-3 transition-all ${
        c.status === 'kept' ? 'border-tan ring-1 ring-tan' : 'border-cream-dark hover:border-tan'
      }`}
    >
      <div className="flex items-start justify-between gap-2">
        <div>
          <h3 className="font-semibold text-charcoal">{c.name}</h3>
          <a
            href={c.url.startsWith('http') ? c.url : `https://${c.url}`}
            target="_blank"
            rel="noopener noreferrer"
            className="text-xs text-tan hover:underline"
          >
            {c.url}
          </a>
        </div>
        {c.pricing_model && (
          <span className="shrink-0 text-xs bg-cream border border-cream-dark text-charcoal px-2 py-0.5 rounded-full">
            {shortPricingLabel(c.pricing_model)}
          </span>
        )}
      </div>
      <p className="text-sm text-charcoal/80 leading-relaxed">{c.positioning}</p>
      <div className="text-xs text-tan font-medium">{c.target_segment}</div>
      {c.key_features.length > 0 && (
        <ul className="flex flex-col gap-1">
          {c.key_features.slice(0, 4).map((f, i) => (
            <li key={i} className="text-xs text-charcoal/70 flex gap-1.5">
              <span className="text-tan mt-0.5">·</span>
              {f}
            </li>
          ))}
        </ul>
      )}
      <div className="pt-1 mt-auto">
        <FeedbackButtons status={c.status} reason={c.reason} onKeep={onKeep} onDismiss={onDismiss} />
      </div>
    </div>
  )
}

function ProspectRow({
  p,
  onKeep,
  onDismiss,
}: {
  p: Prospect
  onKeep: (reason: string) => void
  onDismiss: (reason: string) => void
}) {
  return (
    <div
      className={`flex flex-col sm:flex-row sm:items-start gap-3 py-4 border-b border-cream-dark last:border-0 ${
        p.status === 'kept' ? 'bg-cream/40 -mx-5 px-5' : ''
      }`}
    >
      <div className="sm:w-48 shrink-0">
        <p className="font-medium text-charcoal text-sm">{p.company_name}</p>
        <a
          href={p.website.startsWith('http') ? p.website : `https://${p.website}`}
          target="_blank"
          rel="noopener noreferrer"
          className="text-xs text-tan hover:underline break-all"
        >
          {p.website}
        </a>
      </div>
      <div className="flex-1">
        <p className="text-sm text-charcoal/80">{p.match_reason}</p>
        <div className="mt-2 flex flex-wrap gap-1.5">
          {p.industry && (
            <span className="text-xs bg-cream border border-cream-dark text-charcoal/70 px-2 py-0.5 rounded-full">
              {p.industry}
            </span>
          )}
          {p.employee_count && (
            <span className="text-xs bg-cream border border-cream-dark text-charcoal/70 px-2 py-0.5 rounded-full">
              {p.employee_count}
            </span>
          )}
          {p.tech_stack.slice(0, 3).map((t, i) => (
            <span key={i} className="text-xs bg-cream border border-cream-dark text-charcoal/70 px-2 py-0.5 rounded-full">
              {t}
            </span>
          ))}
        </div>
      </div>
      <div className="shrink-0 sm:pt-0.5 sm:w-44">
        <FeedbackButtons status={p.status} reason={p.reason} onKeep={onKeep} onDismiss={onDismiss} />
      </div>
    </div>
  )
}

function NewThisRun({ competitors, prospects }: { competitors: string[]; prospects: string[] }) {
  if (competitors.length === 0 && prospects.length === 0) return null
  return (
    <div className="bg-white border border-cream-dark rounded-lg px-5 py-4">
      <h2 className="text-xs font-semibold uppercase tracking-widest text-tan mb-3">
        New this run
        <span className="ml-2 text-charcoal/40 normal-case tracking-normal font-normal">
          entrants not seen in earlier scans
        </span>
      </h2>
      <div className="flex flex-col gap-2">
        {competitors.map((name, i) => (
          <div key={`c${i}`} className="flex gap-2.5 items-baseline text-sm">
            <span className="text-green-700 font-semibold w-3 shrink-0">+</span>
            <span className="text-charcoal/50 text-xs uppercase tracking-wide w-28 shrink-0">Competitor</span>
            <span className="text-charcoal/90">{name}</span>
          </div>
        ))}
        {prospects.map((name, i) => (
          <div key={`p${i}`} className="flex gap-2.5 items-baseline text-sm">
            <span className="text-green-700 font-semibold w-3 shrink-0">+</span>
            <span className="text-charcoal/50 text-xs uppercase tracking-wide w-28 shrink-0">Prospect</span>
            <span className="text-charcoal/90">{name}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

function Spinner() {
  return (
    <div className="flex items-center gap-3 text-tan">
      <svg className="animate-spin h-5 w-5" viewBox="0 0 24 24" fill="none">
        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
      </svg>
      <span className="text-sm text-charcoal/60">Running competitive intelligence and ICP agents…</span>
    </div>
  )
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return <h2 className="text-xs font-semibold uppercase tracking-widest text-tan mb-4">{children}</h2>
}

export default function Home() {
  const [url, setUrl] = useState('')
  const [activeUrl, setActiveUrl] = useState('')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<Workspace | null>(null)
  const [history, setHistory] = useState<Snapshot[]>([])
  const [showAllComps, setShowAllComps] = useState(false)
  const [showAllProspects, setShowAllProspects] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function loadHistory(companyUrl: string) {
    const res = await fetch(`${BACKEND}/company?url=${encodeURIComponent(companyUrl)}`)
    if (!res.ok) return
    const data = await res.json()
    setHistory((data.history ?? []) as Snapshot[])
  }

  async function reloadItems(companyUrl: string) {
    const res = await fetch(`${BACKEND}/workspace?url=${encodeURIComponent(companyUrl)}`)
    if (!res.ok) return
    const data = await res.json()
    setResult(prev =>
      prev ? { ...prev, competitors: data.competitors, icp_prospects: data.icp_prospects } : prev
    )
  }

  async function sendCompetitorFeedback(c: Competitor, decision: 'keep' | 'dismiss', reason: string) {
    const d = decision === 'keep' && c.status === 'kept' ? 'none' : decision
    await fetch(`${BACKEND}/feedback`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        company_url: activeUrl,
        item_type: 'competitor',
        item_key: c.item_key,
        item_label: c.name,
        decision: d,
        reason: reason || null,
      }),
    })
    await reloadItems(activeUrl)
  }

  async function sendProspectFeedback(p: Prospect, decision: 'keep' | 'dismiss', reason: string) {
    const d = decision === 'keep' && p.status === 'kept' ? 'none' : decision
    await fetch(`${BACKEND}/feedback`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        company_url: activeUrl,
        item_type: 'prospect',
        item_key: p.item_key,
        item_label: p.company_name,
        decision: d,
        reason: reason || null,
      }),
    })
    await reloadItems(activeUrl)
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    if (!url.trim()) return
    setLoading(true)
    setResult(null)
    setHistory([])
    setShowAllComps(false)
    setShowAllProspects(false)
    setError(null)

    try {
      const res = await fetch(`${BACKEND}/analyze`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ company_url: url.trim() }),
      })
      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        throw new Error(data.detail ?? data.error ?? 'Analysis failed')
      }
      setActiveUrl(url.trim())
      setResult((await res.json()) as Workspace)
      await loadHistory(url.trim())
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Something went wrong')
    } finally {
      setLoading(false)
    }
  }

  const keptComps = result ? result.competitors.filter(c => c.status === 'kept') : []
  const candComps = result ? result.competitors.filter(c => c.status !== 'kept') : []
  const keptProspects = result ? result.icp_prospects.filter(p => p.status === 'kept') : []
  const candProspects = result ? result.icp_prospects.filter(p => p.status !== 'kept') : []
  const visibleComps = showAllComps ? candComps : candComps.slice(0, CANDIDATE_CAP)
  const visibleProspects = showAllProspects ? candProspects : candProspects.slice(0, CANDIDATE_CAP)

  return (
    <div className="min-h-screen flex flex-col">
      <header className="bg-charcoal px-6 py-5">
        <div className="max-w-5xl mx-auto flex items-baseline gap-3">
          <h1 className="text-cream text-xl font-semibold tracking-tight">Market Intelligence</h1>
          <span className="text-tan text-sm">B2B competitive landscape &amp; ICP analysis</span>
        </div>
      </header>

      <main className="flex-1 px-6 py-12">
        <div className="max-w-5xl mx-auto flex flex-col gap-10">
          <form onSubmit={handleSubmit} className="flex flex-col sm:flex-row gap-3 max-w-2xl">
            <input
              type="text"
              value={url}
              onChange={e => setUrl(e.target.value)}
              placeholder="https://yourcompany.com"
              className="flex-1 bg-white border border-cream-dark rounded-lg px-4 py-3 text-charcoal placeholder-charcoal/30 focus:outline-none focus:border-tan transition-colors text-sm"
            />
            <button
              type="submit"
              disabled={loading || !url.trim()}
              className="bg-charcoal text-cream px-6 py-3 rounded-lg text-sm font-medium hover:bg-tan disabled:opacity-40 disabled:cursor-not-allowed transition-colors whitespace-nowrap"
            >
              Analyze
            </button>
          </form>

          {loading && <Spinner />}

          {error && (
            <div className="border border-red-200 bg-red-50 text-red-700 rounded-lg px-4 py-3 text-sm">
              {error}
            </div>
          )}

          {result && (
            <div className="flex flex-col gap-10">
              <NewThisRun competitors={result.new_competitors} prospects={result.new_prospects} />

              {history.length > 0 && (
                <section>
                  <h2 className="text-xs font-semibold uppercase tracking-widest text-tan mb-3">
                    Workspace history
                    <span className="ml-2 text-charcoal/40 normal-case tracking-normal font-normal">
                      {history.length} {history.length === 1 ? 'run' : 'runs'} · curated set accumulates across them
                    </span>
                  </h2>
                  <div className="flex flex-wrap gap-2">
                    {history.map((snap, i) => (
                      <span
                        key={snap.id}
                        className={`text-xs px-3 py-1.5 rounded-full border ${
                          i === 0
                            ? 'bg-charcoal text-cream border-charcoal'
                            : 'bg-white text-charcoal/60 border-cream-dark'
                        }`}
                      >
                        {formatSnapshotTime(snap.created_at)}
                        {i === 0 && <span className="ml-1.5 opacity-60">· latest</span>}
                      </span>
                    ))}
                  </div>
                </section>
              )}

              <section>
                <div className="flex items-center gap-3 mb-3 flex-wrap">
                  <h2 className="text-xs font-semibold uppercase tracking-widest text-tan">
                    Market Summary — {result.company}
                  </h2>
                  {result.eval && <GroundingBadge evaluation={result.eval} />}
                </div>
                <SummaryBlock text={result.market_summary} />
              </section>

              {(keptComps.length > 0 || candComps.length > 0) && (
                <section>
                  <SectionLabel>Competitive Landscape</SectionLabel>

                  {keptComps.length > 0 && (
                    <div className="mb-5">
                      <p className="text-xs text-charcoal/50 mb-2 font-medium">★ Your shortlist</p>
                      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                        {keptComps.map(c => (
                          <CompetitorCard
                            key={c.item_key}
                            c={c}
                            onKeep={reason => sendCompetitorFeedback(c, 'keep', reason)}
                            onDismiss={reason => sendCompetitorFeedback(c, 'dismiss', reason)}
                          />
                        ))}
                      </div>
                    </div>
                  )}

                  <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                    {visibleComps.map(c => (
                      <CompetitorCard
                        key={c.item_key}
                        c={c}
                        onKeep={reason => sendCompetitorFeedback(c, 'keep', reason)}
                        onDismiss={reason => sendCompetitorFeedback(c, 'dismiss', reason)}
                      />
                    ))}
                  </div>
                  {candComps.length > CANDIDATE_CAP && (
                    <button
                      onClick={() => setShowAllComps(v => !v)}
                      className="mt-3 text-xs text-tan hover:underline"
                    >
                      {showAllComps ? 'Show fewer' : `Show ${candComps.length - CANDIDATE_CAP} more`}
                    </button>
                  )}
                </section>
              )}

              {(keptProspects.length > 0 || candProspects.length > 0) && (
                <section>
                  <SectionLabel>ICP Prospects</SectionLabel>

                  {keptProspects.length > 0 && (
                    <div className="mb-4">
                      <p className="text-xs text-charcoal/50 mb-2 font-medium">★ Your shortlist</p>
                      <div className="bg-white border border-tan ring-1 ring-tan rounded-lg px-5 divide-y divide-cream-dark">
                        {keptProspects.map(p => (
                          <ProspectRow
                            key={p.item_key}
                            p={p}
                            onKeep={reason => sendProspectFeedback(p, 'keep', reason)}
                            onDismiss={reason => sendProspectFeedback(p, 'dismiss', reason)}
                          />
                        ))}
                      </div>
                    </div>
                  )}

                  <div className="bg-white border border-cream-dark rounded-lg px-5 divide-y divide-cream-dark">
                    {visibleProspects.map(p => (
                      <ProspectRow
                        key={p.item_key}
                        p={p}
                        onKeep={reason => sendProspectFeedback(p, 'keep', reason)}
                        onDismiss={reason => sendProspectFeedback(p, 'dismiss', reason)}
                      />
                    ))}
                  </div>
                  {candProspects.length > CANDIDATE_CAP && (
                    <button
                      onClick={() => setShowAllProspects(v => !v)}
                      className="mt-3 text-xs text-tan hover:underline"
                    >
                      {showAllProspects ? 'Show fewer' : `Show ${candProspects.length - CANDIDATE_CAP} more`}
                    </button>
                  )}
                </section>
              )}
            </div>
          )}
        </div>
      </main>
    </div>
  )
}
