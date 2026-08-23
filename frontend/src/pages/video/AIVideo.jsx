import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../../lib/api.js'
import { useToast } from '../../context/ToastContext.jsx'
import useAIVideo, { STAGES } from '../../hooks/useAIVideo.js'
import VideoPageHeader from '../../components/video/VideoPageHeader.jsx'
import VideoIcon from '../../components/video/VideoIcon.jsx'
import Spinner from '../../components/Spinner.jsx'
import ScenePicker from '../../components/video/ScenePicker.jsx'
import ScriptEditor from '../../components/video/ScriptEditor.jsx'
import ScriptBriefForm from '../../components/video/ScriptBriefForm.jsx'
import { formatDuration } from '../../lib/video/format.js'

// ---------------------------------------------------------------------------
// AI Video — the pipeline, as three screens the user moves through.
//
//   1. Brief    the eight inputs the script is written from
//   2. Script   what the model wrote, every part editable
//   3. Scenes   the storyboard, editable, with generation and progress
//
// **Every generated thing is a form field.** The script's hook is a textarea,
// not a rendered paragraph; a scene's narration, visual prompt, length and
// on-screen text are all inputs. That is the requirement — "the user must be
// able to modify every generated component" — expressed as UI rather than
// promised in a tooltip.
//
// **It ends in the real editor.** The last step assembles the scenes into the
// project's timeline and hands over to /video/projects/:id/edit. There is no
// separate AI preview and no separate AI export: from that point on it is an
// ordinary project.
// ---------------------------------------------------------------------------


// ---------------------------------------------------------------------------
// 3. The storyboard
// ---------------------------------------------------------------------------

function SceneCard({ scene, index, onUpdate, onDelete, onRegenerateVisual, onPickOwn, busy }) {
  const [draft, setDraft] = useState(scene)
  useEffect(() => setDraft(scene), [scene])

  const commit = (patch) => onUpdate(scene.id, patch)

  return (
    <li className="panel flex flex-col gap-3 p-3 sm:flex-row">
      <div className="flex w-full shrink-0 flex-col gap-2 sm:w-40">
        <div className="relative grid aspect-[9/16] max-h-40 place-items-center overflow-hidden rounded-lg bg-inset">
          {scene.asset_url ? (
            <img
              src={scene.asset_url}
              alt=""
              className="h-full w-full object-cover"
            />
          ) : (
            <span className="text-xs text-muted">No visual yet</span>
          )}
          <span className="absolute left-1 top-1 rounded bg-black/60 px-1.5 py-0.5 text-[10px] font-semibold text-white">
            {index + 1}
          </span>
        </div>
        <div className="flex gap-1">
          <button
            className="btn btn-secondary btn-sm flex-1"
            onClick={() => onRegenerateVisual(scene.id)}
            disabled={busy}
            title="Generate a visual for this scene"
          >
            <VideoIcon name="image" className="h-3.5 w-3.5" />
            Generate
          </button>
          {/* The fourth visual source: the user's own file. */}
          <button
            className="btn btn-secondary btn-sm"
            onClick={() => onPickOwn(scene)}
            disabled={busy}
            title="Use one of your own images or clips"
          >
            Mine
          </button>
          <button
            className="btn btn-ghost btn-sm px-2"
            onClick={() => onDelete(scene.id)}
            disabled={busy}
            aria-label="Delete this scene"
          >
            <VideoIcon name="trash" className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>

      <div className="flex min-w-0 flex-1 flex-col gap-2">
        <div className="flex items-center gap-2">
          <input
            className="input flex-1 font-medium"
            value={draft.title || ''}
            onChange={(event) => setDraft({ ...draft, title: event.target.value })}
            onBlur={() =>
              draft.title !== scene.title && commit({ title: draft.title })
            }
          />
          <span className="shrink-0 text-xs tabular-nums text-muted">
            {formatDuration(scene.start_seconds)}
          </span>
        </div>

        <textarea
          className="input min-h-[64px] resize-y text-sm"
          value={draft.text || ''}
          placeholder="What is said over this scene"
          onChange={(event) => setDraft({ ...draft, text: event.target.value })}
          onBlur={() => draft.text !== scene.text && commit({ text: draft.text })}
        />

        <input
          className="input text-sm"
          value={draft.visual_prompt || ''}
          placeholder="What should be on screen"
          onChange={(event) => setDraft({ ...draft, visual_prompt: event.target.value })}
          onBlur={() =>
            draft.visual_prompt !== scene.visual_prompt &&
            commit({ visual_prompt: draft.visual_prompt })
          }
        />

        <div className="flex flex-wrap items-center gap-2">
          <input
            className="input w-24 text-sm"
            type="number"
            step="0.5"
            min="0.5"
            max="30"
            value={draft.duration_seconds}
            onChange={(event) =>
              setDraft({ ...draft, duration_seconds: Number(event.target.value) })
            }
            onBlur={() =>
              draft.duration_seconds !== scene.duration_seconds &&
              commit({ duration_seconds: draft.duration_seconds })
            }
            aria-label="Length in seconds"
          />
          <select
            className="select w-32 text-sm"
            value={scene.transition}
            onChange={(event) => commit({ transition: event.target.value })}
            aria-label="Transition"
          >
            {['cut', 'fade', 'slide', 'zoom', 'wipe', 'dissolve'].map((value) => (
              <option key={value} value={value}>
                {value[0].toUpperCase() + value.slice(1)}
              </option>
            ))}
          </select>
          <input
            className="input min-w-0 flex-1 text-sm"
            value={draft.settings?.overlay_text ?? ''}
            placeholder="On-screen text (optional)"
            onChange={(event) =>
              setDraft({
                ...draft,
                settings: { ...draft.settings, overlay_text: event.target.value },
              })
            }
            onBlur={() =>
              draft.settings?.overlay_text !== scene.settings?.overlay_text &&
              commit({ overlay_text: draft.settings?.overlay_text || '' })
            }
          />
          {scene.voice_asset_id && (
            <span className="badge badge-accent shrink-0">
              <VideoIcon name="mic" className="h-3 w-3" />
              Voiced
            </span>
          )}
        </div>
      </div>
    </li>
  )
}

// ---------------------------------------------------------------------------

export default function AIVideo() {
  const navigate = useNavigate()
  const toast = useToast()
  const ai = useAIVideo()

  const [options, setOptions] = useState(null)
  const [step, setStep] = useState('brief')
  const [draftScript, setDraftScript] = useState(null)
  const [picking, setPicking] = useState(null)

  useEffect(() => {
    api
      .aiVideoOptions()
      .then(setOptions)
      .catch(() => {})
  }, [])

  async function begin(brief) {
    const created = await ai.start(brief)
    if (created) {
      setDraftScript(created.script)
      setStep('script')
    }
  }

  async function acceptScript() {
    const saved = await ai.saveScript(draftScript)
    if (!saved) return
    await ai.rebuildScenes({ describeVisuals: true })
    setStep('scenes')
  }

  // Rewrites one part and keeps the user on the script step. The document that
  // comes back is the whole script, so it replaces the draft outright.
  async function rewriteSection(section, pointId) {
    try {
      const updated = await api.rewriteScriptSection(draftScript, section, pointId)
      setDraftScript(updated)
    } catch (err) {
      toast.error(err?.message || 'Could not rewrite that part.')
    }
  }

  // Genuinely writes the script again, from the brief the project was created
  // with, and stays on the script step so the result can be read before it is
  // committed to a storyboard.
  async function writeItAgain() {
    const again = await ai.regenerateScript()
    if (again) setDraftScript(again)
  }

  async function openInEditor() {
    const result = await ai.build()
    if (!result) return
    toast.success('Your video is on the timeline.')
    navigate(result.editor_path)
  }

  const stageLabel = STAGES.find((entry) => entry.key === ai.stage)?.label

  return (
    <div className="mx-auto w-full max-w-4xl">
      <VideoPageHeader
        title="AI Video"
        subtitle="Describe the video. Edit what it writes. Open it in the editor."
        back="/video/create"
        backLabel="Back to Create Video"
        actions={
          ai.project && (
            <Link
              to={`/video/projects/${ai.project.id}`}
              className="btn btn-ghost btn-sm"
            >
              Open the project
            </Link>
          )
        }
      />

      {/* ---- Steps ---- */}
      <ol className="mb-5 flex flex-wrap items-center gap-2 text-sm">
        {[
          ['brief', 'Brief'],
          ['script', 'Script'],
          ['scenes', 'Storyboard'],
        ].map(([key, label], index) => (
          <li key={key} className="flex items-center gap-2">
            {index > 0 && <span className="text-muted">→</span>}
            <span
              className={`badge ${
                step === key
                  ? 'badge-accent'
                  : 'border border-line bg-inset text-muted'
              }`}
            >
              {label}
            </span>
          </li>
        ))}
      </ol>

      {ai.error && (
        <div className="mb-4 flex items-start justify-between gap-3 rounded-[10px] border border-rose-300 bg-rose-50 px-3 py-2">
          <p className="text-sm text-rose-700">{ai.error}</p>
        </div>
      )}

      {step === 'brief' && (
        <ScriptBriefForm
          options={options}
          onSubmit={begin}
          busy={ai.busy}
          submitLabel="Write the script"
        />
      )}

      {step === 'script' && draftScript && (
        <ScriptEditor
          script={draftScript}
          onChange={setDraftScript}
          onRewrite={rewriteSection}
          busy={ai.busy}
          footer={
            <>
              <button className="btn btn-primary" onClick={acceptScript} disabled={ai.busy}>
                {ai.busy && <Spinner />}
                Save and build the storyboard
              </button>
              <button
                className="btn btn-secondary"
                onClick={writeItAgain}
                disabled={ai.busy}
              >
                {ai.busy && <Spinner />}
                Write it again
              </button>
            </>
          }
        />
      )}

      {step === 'scenes' && (
        <div className="flex flex-col gap-4">
          <div className="card flex flex-wrap items-center justify-between gap-3 p-4">
            <div>
              <h2 className="font-semibold text-body">Storyboard</h2>
              <p className="text-sm text-muted">
                {ai.summary?.scene_count || 0} scenes ·{' '}
                {formatDuration(ai.summary?.duration_seconds || 0)} ·{' '}
                {ai.summary?.with_visual || 0} with a visual ·{' '}
                {ai.summary?.with_voice || 0} voiced
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              <button
                className="btn btn-secondary btn-sm"
                onClick={() => setStep('script')}
                disabled={ai.busy}
              >
                Edit the script
              </button>
              <button
                className="btn btn-secondary btn-sm"
                onClick={() => ai.generateVisuals()}
                disabled={ai.busy}
              >
                <VideoIcon name="image" className="h-4 w-4" />
                Visuals
              </button>
              <button
                className="btn btn-secondary btn-sm"
                onClick={() => ai.generateVoice()}
                disabled={ai.busy}
              >
                <VideoIcon name="mic" className="h-4 w-4" />
                Narration
              </button>
              <button
                className="btn btn-primary btn-sm"
                onClick={async () => {
                  await ai.runRemaining()
                  if (!ai.error) {
                    toast.success('Your video is on the timeline.')
                    navigate(`/video/projects/${ai.project.id}/edit`)
                  }
                }}
                disabled={ai.busy}
              >
                <VideoIcon name="sparkle" className="h-4 w-4" />
                Generate everything
              </button>
            </div>
          </div>

          {ai.busy && ai.stage && (
            <div className="card flex items-center gap-3 p-4">
              <Spinner />
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium text-body">{stageLabel}</p>
                {ai.progress.total > 0 && (
                  <>
                    <p className="text-xs text-muted">
                      {ai.progress.done} of {ai.progress.total}
                    </p>
                    <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-inset">
                      <div
                        className="h-full rounded-full bg-accent transition-[width]"
                        style={{
                          width: `${
                            (ai.progress.done / Math.max(ai.progress.total, 1)) * 100
                          }%`,
                        }}
                      />
                    </div>
                  </>
                )}
              </div>
              <button className="btn btn-ghost btn-sm" onClick={ai.cancel}>
                Stop
              </button>
            </div>
          )}

          {ai.problems.length > 0 && (
            <div className="card border-amber-300 bg-amber-50 p-4">
              <p className="text-sm font-medium text-amber-900">
                {ai.problems.length} scene
                {ai.problems.length === 1 ? '' : 's'} could not be generated. The
                rest are done — you can retry these individually.
              </p>
              <ul className="mt-2 list-disc pl-5 text-xs text-amber-800">
                {ai.problems.slice(0, 5).map((problem, index) => (
                  <li key={index}>
                    {problem.title ? `${problem.title}: ` : ''}
                    {problem.message}
                  </li>
                ))}
              </ul>
              <button
                className="btn btn-ghost btn-sm mt-2"
                onClick={ai.clearProblems}
              >
                Dismiss
              </button>
            </div>
          )}

          <ul className="flex flex-col gap-3">
            {ai.scenes.map((scene, index) => (
              <SceneCard
                key={scene.id}
                scene={scene}
                index={index}
                busy={ai.busy}
                onUpdate={ai.updateScene}
                onDelete={ai.removeScene}
                onRegenerateVisual={(id) => ai.generateVisuals({ only: [id] })}
                onPickOwn={setPicking}
              />
            ))}
          </ul>

          <div className="card flex flex-wrap items-center justify-between gap-3 p-4">
            <p className="text-sm text-muted">
              When you are happy, this becomes a normal timeline you can edit
              and export.
            </p>
            <button
              className="btn btn-primary"
              onClick={openInEditor}
              disabled={ai.busy || !ai.scenes.length}
            >
              {ai.busy && <Spinner />}
              <VideoIcon name="timeline" className="h-4 w-4" />
              Open in the editor
            </button>
          </div>
        </div>
      )}

      <ScenePicker
        open={picking !== null}
        scene={picking}
        onClose={() => setPicking(null)}
        onPick={(item) => ai.updateScene(picking.id, { asset_id: item.id })}
      />
    </div>
  )
}
