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
}
