import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.jsx'
import VideoReview from './VideoReview.jsx'
import RenderJob from './RenderJob.jsx'
import Dashboard from './Dashboard.jsx'
import EditScript from './EditScript.jsx'
import Voices from './Voices.jsx'

const params = new URLSearchParams(window.location.search)
const videoJobId = params.get('video_job_id')
const renderJobId = params.get('render_job_id')
const editScriptId = params.get('edit_script_id')
const view = params.get('view')

function Router() {
  if (videoJobId) return <VideoReview videoJobId={videoJobId} />
  if (renderJobId) return <RenderJob renderJobId={renderJobId} />
  if (editScriptId) return <EditScript scriptId={editScriptId} />
  if (view === 'upload') return <App />
  if (view === 'voices') return <Voices />
  return <Dashboard />
}

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <Router />
  </StrictMode>,
)
