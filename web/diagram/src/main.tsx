import { createRoot } from 'react-dom/client'
import { StrictMode } from 'react'
import WorkflowDiagram from './WorkflowDiagram'
import './tailwind.css'

const root = document.getElementById('root')
if (root) {
  createRoot(root).render(
    <StrictMode>
      <WorkflowDiagram />
    </StrictMode>,
  )

  if (window.parent !== window) {
    const post = () => {
      const height = Math.max(
        document.documentElement.scrollHeight,
        document.body.scrollHeight,
      )
      window.parent.postMessage(
        { type: 'sf-pulse-diagram-resize', height },
        '*',
      )
    }
    const ro = new ResizeObserver(post)
    ro.observe(document.documentElement)
    ro.observe(document.body)
    window.addEventListener('load', post)
    post()
  }
}
