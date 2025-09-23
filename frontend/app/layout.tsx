import './globals.css'
import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'Trading Simulator',
  description: 'A comprehensive trading simulator application',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en">
      <body>
        <div id="root">
          {children}
        </div>
      </body>
    </html>
  )
}