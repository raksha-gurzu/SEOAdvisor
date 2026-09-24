import { useState, type ReactNode } from 'react'
import type { Tone } from '../format'

export function Pill({ tone = 'neutral', children }: { tone?: Tone | 'brand'; children: ReactNode }) {
  return <span className={`pill ${tone === 'neutral' ? '' : tone}`}>{children}</span>
}

/** Copies on click; says so when the browser refuses clipboard access. */
export function CopyButton({ text, label = 'Copy', className = 'btn ghost' }: { text: string; label?: string; className?: string }) {
  const [state, setState] = useState<'idle' | 'copied' | 'failed'>('idle')
  return (
    <button
      type="button"
      className={className}
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(text)
          setState('copied')
        } catch {
          setState('failed')
        }
        setTimeout(() => setState('idle'), 1600)
      }}
    >
      {state === 'copied' ? 'Copied' : state === 'failed' ? 'Copy blocked' : label}
    </button>
  )
}

export function Disclosure({ summary, children }: { summary: ReactNode; children: ReactNode }) {
  return (
    <details className="disclosure">
      <summary>{summary}</summary>
      <div className="disclosure-body">{children}</div>
    </details>
  )
}

export function Alert({ tone, children }: { tone: 'good' | 'warn' | 'bad'; children: ReactNode }) {
  return (
    <div className={`alert ${tone}`} role={tone === 'bad' ? 'alert' : undefined}>
      <span className="alert-icon" aria-hidden="true">{tone === 'good' ? '✓' : '!'}</span>
      <div>{children}</div>
    </div>
  )
}

export function GlobeIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
      <circle cx="12" cy="12" r="9" />
      <path d="M3 12h18M12 3c2.5 2.7 3.8 5.7 3.8 9s-1.3 6.3-3.8 9c-2.5-2.7-3.8-5.7-3.8-9S9.5 5.7 12 3z" />
    </svg>
  )
}

export function TextIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" aria-hidden="true">
      <rect x="4" y="3" width="16" height="18" rx="2.5" />
      <path d="M8 8h8M8 12h8M8 16h5" />
    </svg>
  )
}
