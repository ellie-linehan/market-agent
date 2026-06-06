import { NextRequest, NextResponse } from 'next/server'

const FASTAPI_URL = process.env.FASTAPI_URL ?? 'http://localhost:8000'

export async function POST(req: NextRequest) {
  const body = await req.json()
  const res = await fetch(`${FASTAPI_URL}/feedback`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    const text = await res.text()
    return NextResponse.json({ error: text }, { status: res.status })
  }
  return NextResponse.json(await res.json())
}

export async function GET(req: NextRequest) {
  const url = req.nextUrl.searchParams.get('url')
  if (!url) return NextResponse.json({ error: 'url is required' }, { status: 400 })
  const res = await fetch(`${FASTAPI_URL}/feedback?url=${encodeURIComponent(url)}`)
  if (!res.ok) {
    const text = await res.text()
    return NextResponse.json({ error: text }, { status: res.status })
  }
  return NextResponse.json(await res.json())
}
