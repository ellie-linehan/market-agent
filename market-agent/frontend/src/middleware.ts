import { NextRequest, NextResponse } from 'next/server'

// HTTP Basic Auth gate for the demo (demo/hackathon). Override via Netlify env
// vars BASIC_AUTH_USER / BASIC_AUTH_PASS. Runs on the edge ahead of every page.
export function middleware(req: NextRequest) {
  const user = process.env.BASIC_AUTH_USER || 'demo'
  const pass = process.env.BASIC_AUTH_PASS || 'hackathon'
  const expected = 'Basic ' + btoa(`${user}:${pass}`)

  if (req.headers.get('authorization') !== expected) {
    return new NextResponse('Authentication required.', {
      status: 401,
      headers: {
        'WWW-Authenticate': 'Basic realm="Market Intelligence (demo)", charset="UTF-8"',
      },
    })
  }
  return NextResponse.next()
}

export const config = {
  // Gate everything except Next's static assets.
  matcher: ['/((?!_next/static|_next/image|favicon.ico).*)'],
}
