import { useEffect, useState } from 'react'

// Tiny hash router: "#/" is the new-brief form, "#/runs/<id>" shows a run.
export type Route = { page: 'new' } | { page: 'run'; id: string }

function parse(hash: string): Route {
  const match = hash.match(/^#\/runs\/([a-z0-9]+)$/i)
  return match ? { page: 'run', id: match[1] } : { page: 'new' }
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
  window.location.hash = route.page === 'run' ? `#/runs/${route.id}` : '#/'
}
