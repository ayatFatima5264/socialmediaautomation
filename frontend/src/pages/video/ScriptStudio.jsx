import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../../lib/api.js'
import { useToast } from '../../context/ToastContext.jsx'
import VideoPageHeader from '../../components/video/VideoPageHeader.jsx'
import VideoIcon from '../../components/video/VideoIcon.jsx'
import Spinner from '../../components/Spinner.jsx'
import ScriptBriefForm from '../../components/video/ScriptBriefForm.jsx'
import ScriptEditor from '../../components/video/ScriptEditor.jsx'

// ---------------------------------------------------------------------------
// Script Studio — a script, without a video.
//
// **Nothing is created until the user asks for it.** The generate call is the
// projectless one, so a person can try six topics, keep one, and leave without
// a projects list full of abandoned attempts. A project appears only when they
// press the button that says it will make one — and then the script they
// edited is carried across as-is rather than being written again.
//
// Everything else — the fields, the per-section rewrite, copy and download —
// is the same component the AI video flow uses, so the two cannot drift.
// ---------------------------------------------------------------------------

export default function ScriptStudio() {
  const toast = useToast()
  const navigate = useNavigate()

  const [options, setOptions] = useState(null)
  const [script, setScript] = useState(null)
  const [busy, setBusy] = useState(false)
  const [creating, setCreating] = useState(false)

  useEffect(() => {
    let cancelled = false
    api
      .aiVideoOptions()
      .then((data) => {
        if (!cancelled) setOptions(data)
      })
      .catch(() => {
        if (!cancelled) setOptions(null)
      })
    return () => {
      cancelled = true
    }
  }, [])

  async function write(brief) {
    setBusy(true)
    try {
      const written = await api.writeVideoScript(brief)
      setScript(written)
    } catch (err) {
      toast.error(err?.message || 'Could not write the script.')
    } finally {
      setBusy(false)
    }
  }

  async function rewriteSection(section, pointId) {
    try {
      const updated = await api.rewriteScriptSection(script, section, pointId)
      setScript(updated)
    } catch (err) {
      toast.error(err?.message || 'Could not rewrite that part.')
    }
  }

  async function writeAgain() {
    const brief = script?.brief
    if (!brief?.topic) return
    await write({
      topic: brief.topic,
      language: brief.language,
      tone: brief.tone,
      audience: brief.audience,
      duration_seconds: brief.duration_seconds,
      platform: brief.platform,
      content_type: brief.content_type,
      instructions: brief.instructions || '',
      visual_mode: brief.visual_mode || 'natural',
    })
  }

  // The one place this page creates anything. The edited script goes with the
  // request, so the storyboard is cut from what the user approved.
  async function createProject() {
    const brief = script?.brief
    if (!brief?.topic) return
    setCreating(true)
    try {
      const result = await api.createAIVideoProject({
        topic: brief.topic,
        language: brief.language,
        tone: brief.tone,
        audience: brief.audience,
        duration_seconds: brief.duration_seconds,
        platform: brief.platform,
        content_type: brief.content_type,
        instructions: brief.instructions || '',
        visual_mode: brief.visual_mode || 'natural',
        name: script.title || brief.topic,
        script,
      })
      toast.success('Project created from your script.')
      navigate(`/video/projects/${result.project_id}`)
    } catch (err) {
      toast.error(err?.message || 'Could not create the project.')
    } finally {
      setCreating(false)
    }
  }

  const unavailable = options && options.text_available === false

  // A script can be far longer than the video pipeline will carry — a scene, a
  // visual and a voice-over per beat is a different cost from a page of text.
  // Past the ceiling the button is disabled with the reason, rather than
  // sending a request the server answers with a validation error.
  const projectCap = Number(options?.project_max_seconds) || 600
  const scriptSeconds = Number(script?.brief?.duration_seconds) || 0
  const tooLongForVideo = scriptSeconds > projectCap

  return (
    <div className="mx-auto w-full max-w-3xl">
      <VideoPageHeader
        title="Script Studio"
        subtitle="Write a script on its own. Turn it into a video only if you want to."
        back="/video"
        backLabel="Back to Video Studio"
        actions={
          script && (
            <button
              className="btn btn-secondary btn-sm"
              onClick={() => setScript(null)}
              disabled={busy || creating}
            >
              Start over
            </button>
          )
        }
      />

      {unavailable && (
        <div className="card mb-4 p-4">
          <p className="text-sm text-body">
            No text provider is configured, so scripts cannot be generated yet.
          </p>
        </div>
      )}

      {!script && (
        <ScriptBriefForm
          options={options}
          onSubmit={write}
          busy={busy}
          submitLabel="Write the script"
          busyLabel="Writing the script…"
        />
      )}

      {script && (
        <div className="flex flex-col gap-4">
          <ScriptEditor
            script={script}
            onChange={setScript}
            onRewrite={rewriteSection}
            busy={busy || creating}
            subtitle={
              tooLongForVideo
                ? 'Nothing has been saved yet. Copy it or download it.'
                : 'Nothing has been saved yet. Copy it, download it, or turn it into a video.'
            }
            footer={
              <>
                <button
                  className="btn btn-primary"
                  onClick={createProject}
                  disabled={busy || creating || tooLongForVideo}
                >
                  {creating ? <Spinner /> : <VideoIcon name="film" className="h-4 w-4" />}
                  {creating ? 'Creating the project…' : 'Create a video project'}
                </button>
                <button
                  className="btn btn-secondary"
                  onClick={writeAgain}
                  disabled={busy || creating}
                >
                  {busy && <Spinner />}
                  Write it again
                </button>
              </>
            }
          />

          <p className="text-xs text-muted">
            {tooLongForVideo
              ? `A script this long cannot be built into a video yet — that stops
                 at ${Math.round(projectCap / 60)} minutes. The script itself is
                 yours: edit it, copy it, download it.`
              : `Creating a project writes this script to it and cuts it into
                 scenes. Your edits are kept — it is not generated again.`}
          </p>
        </div>
      )}
    </div>
  )
}
