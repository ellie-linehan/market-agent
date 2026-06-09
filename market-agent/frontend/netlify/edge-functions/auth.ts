// HTTP Basic Auth gate for the demo site (free-tier alternative to Netlify's
// paid password protection). Credentials default to demo/hackathon and can be
// overridden via Netlify env vars BASIC_AUTH_USER / BASIC_AUTH_PASS.
import type { Context } from '@netlify/edge-functions'

export default async (request: Request, context: Context): Promise<Response> => {
  const user = Netlify.env.get('BASIC_AUTH_USER') ?? 'demo'
  const pass = Netlify.env.get('BASIC_AUTH_PASS') ?? 'hackathon'
  const expected = 'Basic ' + btoa(`${user}:${pass}`)

  if (request.headers.get('authorization') !== expected) {
    return new Response('Authentication required.', {
      status: 401,
      headers: {
        'WWW-Authenticate': 'Basic realm="Market Intelligence (demo)", charset="UTF-8"',
      },
    })
  }
  return context.next()
}
