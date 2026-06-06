'use client'

import { useState, FormEvent } from 'react'

interface Competitor {
  name: string
  url: string
  positioning: string
  target_segment: string
  key_features: string[]
  pricing_model?: string
}

interface Prospect {
  company_name: string
  website: string
  match_reason: string
  employee_count?: string
  industry?: string
  tech_stack: string[]
}

interface MarketAnalysis {
  company: string
  competitors: Competitor[]
  icp_prospects: Prospect[]
  market_summary: string
}

interface Snapshot {
  id: string
  created_at: string
  company_name: string
  analysis: MarketAnalysis
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

// Only split where punctuation is followed by whitespace + a capital letter.
// This naturally handles .com, URLs, e.g., i.e., etc. without special casing.
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
  // Fall back to first two words max
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

type Decision = 'keep' | 'dismiss'

function FeedbackButtons({
  decision,
  onKeep,
  onDismiss,
}: {
  decision?: Decision
  onKeep: () => void
  onDismiss: () => void
}) {
  return (
    <div className="flex gap-1.5">
      <button
        onClick={onKeep}
        className={`text-xs px-2.5 py-1 rounded-md border transition-colors ${
          decision === 'keep'
            ? 'bg-charcoal text-cream border-charcoal'
            : 'bg-white text-charcoal/60 border-cream-dark hover:border-tan'
        }`}
      >
        ✓ Keep
      </button>
      <button
        onClick={onDismiss}
        className={`text-xs px-2.5 py-1 rounded-md border transition-colors ${
          decision === 'dismiss'
            ? 'bg-charcoal text-cream border-charcoal'
            : 'bg-white text-charcoal/60 border-cream-dark hover:border-tan'
        }`}
      >
        ✕ Dismiss
      </button>
    </div>
  )
}

function CompetitorCard({
  c,
  decision,
  onKeep,
  onDismiss,
}: {
  c: Competitor
  decision?: Decision
  onKeep: () => void
  onDismiss: () => void
}) {
  return (
    <div
      className={`bg-white border rounded-lg p-5 flex flex-col gap-3 transition-all ${
        decision === 'dismiss'
          ? 'border-cream-dark opacity-50'
          : decision === 'keep'
          ? 'border-tan ring-1 ring-tan'
          : 'border-cream-dark hover:border-tan'
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
        <FeedbackButtons decision={decision} onKeep={onKeep} onDismiss={onDismiss} />
      </div>
    </div>
  )
}

function ProspectRow({
  p,
  decision,
  onKeep,
  onDismiss,
}: {
  p: Prospect
  decision?: Decision
  onKeep: () => void
  onDismiss: () => void
}) {
  return (
    <div
      className={`flex flex-col sm:flex-row sm:items-start gap-3 py-4 border-b border-cream-dark last:border-0 transition-opacity ${
        decision === 'dismiss' ? 'opacity-50' : ''
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
            <span
              key={i}
              className="text-xs bg-cream border border-cream-dark text-charcoal/70 px-2 py-0.5 rounded-full"
            >
              {t}
            </span>
          ))}
        </div>
      </div>
      <div className="shrink-0 sm:pt-0.5">
        <FeedbackButtons decision={decision} onKeep={onKeep} onDismiss={onDismiss} />
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

export default function Home() {
  const [url, setUrl] = useState('')
  const [activeUrl, setActiveUrl] = useState('')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<MarketAnalysis | null>(null)
  const [history, setHistory] = useState<Snapshot[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [feedback, setFeedback] = useState<Record<string, Decision>>({})
  const [error, setError] = useState<string | null>(null)

  const competitorKey = (c: Competitor) => `competitor:${c.url || c.name}`
  const prospectKey = (p: Prospect) => `prospect:${p.website || p.company_name}`
  const keptCount = Object.values(feedback).filter(d => d === 'keep').length
  const dismissedCount = Object.values(feedback).filter(d => d === 'dismiss').length

  async function loadHistory(companyUrl: string): Promise<Snapshot[]> {
    const res = await fetch(`/api/company?url=${encodeURIComponent(companyUrl)}`)
    if (!res.ok) return []
    const data = await res.json()
    return (data.history ?? []) as Snapshot[]
  }

  async function loadFeedback(companyUrl: string) {
    const res = await fetch(`/api/feedback?url=${encodeURIComponent(companyUrl)}`)
    if (!res.ok) return
    const data = await res.json()
    const map: Record<string, Decision> = {}
    for (const r of data.feedback ?? []) {
      map[`${r.item_type}:${r.item_key}`] = r.decision
    }
    setFeedback(map)
  }

  async function sendFeedback(
    itemType: 'competitor' | 'prospect',
    itemKey: string,
    itemLabel: string,
    decision: Decision,
  ) {
    const mapKey = `${itemType}:${itemKey}`
    // Toggle off if the same decision is clicked again.
    const next: Decision | undefined = feedback[mapKey] === decision ? undefined : decision
    setFeedback(prev => {
      const copy = { ...prev }
      if (next) copy[mapKey] = next
      else delete copy[mapKey]
      return copy
    })
    await fetch('/api/feedback', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        company_url: activeUrl,
        item_type: itemType,
        item_key: itemKey,
        item_label: itemLabel,
        decision: next ?? 'none',
      }),
    })
  }

  function selectSnapshot(snap: Snapshot) {
    setSelectedId(snap.id)
    setResult(snap.analysis)
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    if (!url.trim()) return
    setLoading(true)
    setResult(null)
    setHistory([])
    setSelectedId(null)
    setError(null)

    try {
      const res = await fetch('/api/analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: url.trim() }),
      })
      if (!res.ok) {
        const data = await res.json()
        throw new Error(data.error ?? 'Analysis failed')
      }
      setActiveUrl(url.trim())
      setResult(await res.json())

      // The snapshot was just saved server-side — load the company's full
      // timeline and any prior keep/dismiss feedback for this workspace.
      const [snaps] = await Promise.all([
        loadHistory(url.trim()),
        loadFeedback(url.trim()),
      ])
      setHistory(snaps)
      if (snaps.length > 0) setSelectedId(snaps[0].id)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Something went wrong')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex flex-col">
      {/* Header */}
      <header className="bg-charcoal px-6 py-5">
        <div className="max-w-5xl mx-auto flex items-baseline gap-3">
          <h1 className="text-cream text-xl font-semibold tracking-tight">Market Intelligence</h1>
          <span className="text-tan text-sm">B2B competitive landscape & ICP analysis</span>
        </div>
      </header>

      {/* Main */}
      <main className="flex-1 px-6 py-12">
        <div className="max-w-5xl mx-auto flex flex-col gap-10">

          {/* Input */}
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

              {/* Workspace history timeline */}
              {history.length > 0 && (
                <section>
                  <h2 className="text-xs font-semibold uppercase tracking-widest text-tan mb-3">
                    Workspace history
                    <span className="ml-2 text-charcoal/40 normal-case tracking-normal font-normal">
                      {history.length} {history.length === 1 ? 'snapshot' : 'snapshots'} saved
                    </span>
                  </h2>
                  <div className="flex flex-wrap gap-2">
                    {history.map((snap, i) => (
                      <button
                        key={snap.id}
                        onClick={() => selectSnapshot(snap)}
                        className={`text-xs px-3 py-1.5 rounded-full border transition-colors ${
                          snap.id === selectedId
                            ? 'bg-charcoal text-cream border-charcoal'
                            : 'bg-white text-charcoal/70 border-cream-dark hover:border-tan'
                        }`}
                      >
                        {formatSnapshotTime(snap.created_at)}
                        {i === 0 && (
                          <span className="ml-1.5 opacity-60">· latest</span>
                        )}
                      </button>
                    ))}
                  </div>
                </section>
              )}

              {/* Feedback signal banner */}
              {(keptCount > 0 || dismissedCount > 0) && (
                <div className="bg-cream border border-cream-dark rounded-lg px-4 py-3 flex items-center gap-3 text-sm">
                  <span className="text-tan font-semibold text-xs uppercase tracking-wide shrink-0">
                    Learning
                  </span>
                  <span className="text-charcoal/80">
                    This workspace has <strong>{keptCount} kept</strong> and{' '}
                    <strong>{dismissedCount} dismissed</strong>. Re-run Analyze to refine
                    competitors and prospects toward your judgment.
                  </span>
                </div>
              )}

              {/* Summary */}
              <section>
                <h2 className="text-xs font-semibold uppercase tracking-widest text-tan mb-3">
                  Market Summary — {result.company}
                </h2>
                <SummaryBlock text={result.market_summary} />
              </section>

              {/* Competitive Landscape */}
              {result.competitors.length > 0 && (
                <section>
                  <h2 className="text-xs font-semibold uppercase tracking-widest text-tan mb-4">
                    Competitive Landscape
                  </h2>
                  <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                    {result.competitors.map((c, i) => (
                      <CompetitorCard
                        key={i}
                        c={c}
                        decision={feedback[competitorKey(c)]}
                        onKeep={() => sendFeedback('competitor', c.url || c.name, c.name, 'keep')}
                        onDismiss={() => sendFeedback('competitor', c.url || c.name, c.name, 'dismiss')}
                      />
                    ))}
                  </div>
                </section>
              )}

              {/* ICP Prospects */}
              {result.icp_prospects.length > 0 && (
                <section>
                  <h2 className="text-xs font-semibold uppercase tracking-widest text-tan mb-4">
                    ICP Prospects
                  </h2>
                  <div className="bg-white border border-cream-dark rounded-lg px-5 divide-y divide-cream-dark">
                    {result.icp_prospects.map((p, i) => (
                      <ProspectRow
                        key={i}
                        p={p}
                        decision={feedback[prospectKey(p)]}
                        onKeep={() => sendFeedback('prospect', p.website || p.company_name, p.company_name, 'keep')}
                        onDismiss={() => sendFeedback('prospect', p.website || p.company_name, p.company_name, 'dismiss')}
                      />
                    ))}
                  </div>
                </section>
              )}

            </div>
          )}
        </div>
      </main>
    </div>
  )
}
