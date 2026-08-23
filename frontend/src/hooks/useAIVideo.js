import { useCallback, useRef, useState } from 'react'
import { api } from '../lib/api.js'
import { useToast } from '../context/ToastContext.jsx'

// ---------------------------------------------------------------------------
// The AI video pipeline, as the client drives it.
//
//   brief → script → scenes → visuals → voice → subtitles → build → editor
//
// **Progress is counted, not animated.** The expensive stages are one request
// per scene, so this hook knows exactly how many are done and says so — "5 of
// 8 visuals". A bar that moves on a timer while eight images generate is a bar
// that lies, and the one time it matters is when a stage has silently failed.
//
// **A failed scene does not fail the run.** Visuals and narration are
// generated per scene and the failures are collected; the pipeline finishes
// the rest and reports what did not work, because seven scenes with pictures
// and one to retry is a far better place to be than nothing.
//
// **Every stage writes to the real project.** There is no local draft that has
// to be committed at the end — after `start` the project exists, and each
// stage is durable on its own. Closing the tab half way through leaves a real
// project with a script and scenes, not a lost session.
// ---------------------------------------------------------------------------

export const STAGES = [
  { key: 'script', label: 'Writing the script' },
  { key: 'scenes', label: 'Building the storyboard' },
  { key: 'visuals', label: 'Finding the visuals' },
  { key: 'voice', label: 'Recording the narration' },
  { key: 'subtitles', label: 'Timing the captions' },
  { key: 'build', label: 'Assembling the timeline' },
]

export default function useAIVideo() {
  const toast = useToast()

  const [project, setProject] = useState(null)
  const [script, setScript] = useState(null)
  const [scenes, setScenes] = useState([])
  const [summary, setSummary] = useState(null)

  const [stage, setStage] = useState(null)
  const [progress, setProgress] = useState({ done: 0, total: 0 })
  const [problems, setProblems] = useState([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [built, setBuilt] = useState(false)

  // Set when the user asks to stop. Checked between scenes rather than
  // aborting a request in flight: a half-generated image that never gets
  // stored is a wasted call nobody can retry.
  const cancelRef = useRef(false)

  const reset = useCallback(() => {
    cancelRef.current = false
    setProblems([])
    setError(null)
  }, [])

  // ---- Stage 1-2: the project, its script and its storyboard -------------

  const start = useCallback(
    async (brief) => {
      reset()
      setBusy(true)
      setStage('script')
      setProgress({ done: 0, total: 0 })
      try {
        const created = await api.createAIVideoProject(brief)
        setProject(created.project)
        setScript(created.script)
        setScenes(created.scenes || [])
        setSummary(created.summary)
        setBuilt(false)
        setStage('scenes')
        return created
      } catch (err) {
        setError(err?.message || 'The script could not be generated.')
        setStage(null)
        return null
      } finally {
        setBusy(false)
      }
    },
    [reset],
  )

  const saveScript = useCallback(
    async (next) => {
      if (!project) return null
      setBusy(true)
      try {
        const saved = await api.saveVideoScript(project.id, next)
        setScript(saved)
        return saved
      } catch (err) {
        toast.error(err?.message || 'Could not save the script.')
        return null
      } finally {
        setBusy(false)
      }
    },
    [project, toast],
  )

  // Writes the script again from the brief the project was created with.
  // Deliberately leaves the scenes alone: rebuilding the storyboard here would
  // throw away every visual the user had already chosen, so that stays the
  // separate, explicit step it is on the server.
  const regenerateScript = useCallback(async () => {
    if (!project) return null
    setBusy(true)
    setStage('script')
    try {
      const written = await api.regenerateVideoScript(project.id)
      setScript(written)
      return written
    } catch (err) {
      toast.error(err?.message || 'Could not write the script again.')
      return null
    } finally {
      setBusy(false)
    }
  }, [project, toast])

  const rebuildScenes = useCallback(
    async ({ describeVisuals = true } = {}) => {
      if (!project) return null
      setBusy(true)
      setStage('scenes')
      try {
        const board = await api.generateScenes(project.id, {
          describe_visuals: describeVisuals,
        })
        setScenes(board.scenes || [])
        setSummary(board.summary)
        // The timeline no longer matches the storyboard it was built from.
        setBuilt(false)
        return board
      } catch (err) {
        toast.error(err?.message || 'Could not rebuild the storyboard.')
        return null
      } finally {
        setBusy(false)
      }
    },
    [project, toast],
  )

  const updateScene = useCallback(
    async (sceneId, patch) => {
      if (!project) return null
      try {
        const updated = await api.updateScene(project.id, sceneId, patch)
        // Re-read the board: changing one scene's length moves every scene
        // after it, so patching just this row locally would show wrong times.
        const board = await api.getStoryboard(project.id)
        setScenes(board.scenes || [])
        setSummary(board.summary)
        setBuilt(false)
        return updated
      } catch (err) {
        toast.error(err?.message || 'Could not update that scene.')
        return null
      }
    },
    [project, toast],
  )

  const removeScene = useCallback(
    async (sceneId) => {
      if (!project) return
      try {
        await api.deleteScene(project.id, sceneId)
        const board = await api.getStoryboard(project.id)
        setScenes(board.scenes || [])
        setSummary(board.summary)
        setBuilt(false)
      } catch (err) {
        toast.error(err?.message || 'Could not delete that scene.')
      }
    },
    [project, toast],
  )

  // ---- Stage 3-4: per-scene work -----------------------------------------

  /** Run one per-scene call across a set of scenes, counting as it goes.
   *
   *  Sequential rather than parallel: these are model calls and uploads, and
   *  eight at once is how a free-tier provider starts returning 429s. */
  const runPerScene = useCallback(
    async (stageKey, rows, call) => {
      cancelRef.current = false
      setStage(stageKey)
      setBusy(true)
      setProgress({ done: 0, total: rows.length })

      const failures = []
      const updated = new Map()

      for (const [index, row] of rows.entries()) {
        if (cancelRef.current) break
        try {
          updated.set(row.id, await call(row))
        } catch (err) {
          failures.push({
            sceneId: row.id,
            title: row.title,
            message: err?.message || 'failed',
          })
        }
        setProgress({ done: index + 1, total: rows.length })
      }

      if (updated.size) {
        setScenes((current) =>
          current.map((row) => updated.get(row.id) || row),
        )
      }
      if (failures.length) {
        setProblems((current) => [...current, ...failures])
      }

      setBusy(false)
      return { failures, cancelled: cancelRef.current }
    },
    [],
  )

  const generateVisuals = useCallback(
    async ({ only = null, strategy = null } = {}) => {
      if (!project) return null
      const rows = only
        ? scenes.filter((row) => only.includes(row.id))
        : scenes.filter((row) => !row.asset_id)
      if (!rows.length) return { failures: [], cancelled: false }

      const result = await runPerScene('visuals', rows, (row) =>
        api.generateSceneVisual(project.id, row.id, strategy ? { strategy } : {}),
      )
      setBuilt(false)
      return result
    },
    [project, scenes, runPerScene],
  )

  const generateVoice = useCallback(
    async ({ only = null, voiceId = null } = {}) => {
      if (!project) return null
      const rows = only
        ? scenes.filter((row) => only.includes(row.id))
        : scenes.filter((row) => !row.voice_asset_id && (row.text || '').trim())
      if (!rows.length) return { failures: [], cancelled: false }

      const result = await runPerScene('voice', rows, (row) =>
        api.generateSceneVoice(project.id, row.id, voiceId ? { voice_id: voiceId } : {}),
      )

      // Narration can stretch a scene, which moves every scene after it.
      const board = await api.getStoryboard(project.id)
      setScenes(board.scenes || [])
      setSummary(board.summary)
      setBuilt(false)
      return result
    },
    [project, scenes, runPerScene],
  )

  // ---- Stage 5-6: captions, then the timeline -----------------------------

  const buildSubtitles = useCallback(async () => {
    if (!project) return null
    setStage('subtitles')
    setBusy(true)
    try {
      return await api.buildAISubtitles(project.id, {})
    } catch (err) {
      // Not fatal: a video without captions is still a video.
      setProblems((current) => [
        ...current,
        { message: err?.message || 'Captions could not be timed.' },
      ])
      return null
    } finally {
      setBusy(false)
    }
  }, [project])

  const build = useCallback(async () => {
    if (!project) return null
    setStage('build')
    setBusy(true)
    try {
      const result = await api.buildAITimeline(project.id, {})
      setBuilt(true)
      setStage(null)
      return result
    } catch (err) {
      setError(err?.message || 'The timeline could not be assembled.')
      return null
    } finally {
      setBusy(false)
    }
  }, [project])

  /** Everything after the storyboard, in order. What "Generate everything"
   *  does — each stage still writes as it goes, so stopping half way leaves a
   *  usable project rather than nothing. */
  const runRemaining = useCallback(async () => {
    await generateVisuals()
    if (cancelRef.current) return null
    await generateVoice()
    if (cancelRef.current) return null
    await buildSubtitles()
    if (cancelRef.current) return null
    return build()
  }, [generateVisuals, generateVoice, buildSubtitles, build])

  const cancel = useCallback(() => {
    cancelRef.current = true
  }, [])

  return {
    project,
    script,
    scenes,
    summary,
    stage,
    progress,
    problems,
    busy,
    error,
    built,

    start,
    saveScript,
    regenerateScript,
    rebuildScenes,
    updateScene,
    removeScene,
    generateVisuals,
    generateVoice,
    buildSubtitles,
    build,
    runRemaining,
    cancel,
    clearProblems: () => setProblems([]),
  }
}
