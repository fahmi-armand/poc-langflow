import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'Langflow Integration',
  description: 'Integration with Langflow API',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  )
}