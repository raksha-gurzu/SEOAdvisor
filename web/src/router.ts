import { useEffect, useState } from 'react'

// Tiny hash router. Briefs: "#/" (new) and "#/runs/<id>". Keyword gap: "#/gap" (new) and "#/gaps/<id>".
// Site snapshot: "#/snapshot" (new) and "#/snapshots/<id>".
export type Route =
  | { page: 'new' }
  | { page: 'run'; id: string }
  | { page: 'gap-new'; site?: string; competitors?: string[] }
  | { page: 'gap'; id: string }
  | { page: 'snap-new' }
  | { page: 'snap'; id: string }

export type Tool = 'briefs' | 'gap' | 'snapshot'

function parse(hash: string): Route {
  const run = hash.match(/^#\/runs\/([a-z0-9]+)$/i)
  if (run) return { page: 'run', id: run[1] }
  const gap = hash.match(/^#\/gaps\/([a-z0-9]+)$/i)
  if (gap) return { page: 'gap', id: gap[1] }
  const snap = hash.match(/^#\/snapshots\/([a-z0-9]+)$/i)
  if (snap) return { page: 'snap', id: snap[1] }
  if (hash === '#/snapshot') return { page: 'snap-new' }
  if (hash === '#/gap' || hash.startsWith('#/gap?')) {
    // "#/gap?site=a.com&with=b.com,c.com" opens the form filled in (from "Compare with these").
    const params = new URLSearchParams(hash.slice('#/gap'.length).replace(/^\?/, ''))
    const site = params.get('site') ?? undefined
    const competitors = params.get('with')?.split(',').filter(Boolean)
    return { page: 'gap-new', site, competitors }
  }
  return { page: 'new' }
}

export function toolOf(route: Route): Tool {
  if (route.page === 'gap' || route.page === 'gap-new') return 'gap'
  if (route.page === 'snap' || route.page === 'snap-new') return 'snapshot'
  return 'briefs'
}

export function useRoute(): Route {
  const [route, setRoute] = useState(() => parse(window.location.hash))
  useEffect(() => {
    const onChange = () => setRoute(parse(window.location.hash))
    window.addEventListener('hashchange', onChange)
    return () => window.removeEventListener('hashchange', onChange)
  }, [])
  return route
}

export function go(route: Route): void {
  switch (route.page) {
    case 'run': window.location.hash = `#/runs/${route.id}`; break
    case 'gap': window.location.hash = `#/gaps/${route.id}`; break
    case 'snap': window.location.hash = `#/snapshots/${route.id}`; break
    case 'snap-new': window.location.hash = '#/snapshot'; break
    case 'gap-new': {
      const params = new URLSearchParams()
      if (route.site) params.set('site', route.site)
      if (route.competitors?.length) params.set('with', route.competitors.join(','))
      window.location.hash = params.size ? `#/gap?${params}` : '#/gap'
      break
    }
    default: window.location.hash = '#/'
  }
}
